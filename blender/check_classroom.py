"""独立验收已保存的教室；不执行生成器，不信任缓存统计，不保存场景。

运行：blender -b magic_classroom.blend --python-exit-code 1 -P check_classroom.py
仅临时切换帧及检查图层；退出前恢复。支持旧 Action 和 layered Action。
"""
import math
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

GEOMETRY = {'MESH', 'CURVE', 'FONT'}
LEFT_SAFE = .15
LOOP_END = 193
errors = []
sc = bpy.context.scene


def require(condition, message):
    if not condition:
        errors.append(message)


def curves(action):
    if hasattr(action, 'layers') and len(action.layers):
        return [fc for layer in action.layers for strip in layer.strips
                for bag in getattr(strip, 'channelbags', ()) for fc in bag.fcurves]
    return list(getattr(action, 'fcurves', ()))


def set_frame(frame):
    whole = math.floor(frame)
    sc.frame_set(whole, subframe=frame - whole)
    return bpy.context.evaluated_depsgraph_get()


def union(rects):
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def overlaps(a, b):
    return (a[0] < b[2] - 1e-6 and a[2] > b[0] + 1e-6
            and a[1] < b[3] - 1e-6 and a[3] > b[1] + 1e-6)


def snapshot(frame):
    deps = set_frame(frame)
    matrices, lights = {}, {}
    for ob in sc.objects:
        evaluated = ob.evaluated_get(deps)
        # 比较矩阵而非 Euler 数值，允许天球仪一周完整旋转 2π。
        matrices[ob.name] = tuple(v for row in evaluated.matrix_world for v in row)
        if ob.type == 'LIGHT':
            lights[ob.name] = (evaluated.data.energy,)
    return matrices, lights


def check_loop():
    h = .25
    a, b = snapshot(1), snapshot(LOOP_END)
    right1, right2 = snapshot(1 + h), snapshot(1 + 2 * h)
    left1, left2 = snapshot(LOOP_END - h), snapshot(LOOP_END - 2 * h)
    maximum = [0.0, 0.0]
    for kind, label in enumerate(('变换矩阵', '灯光能量')):
        for name, initial in a[kind].items():
            final = b[kind][name]
            delta = max(abs(x - y) for x, y in zip(initial, final))
            maximum[kind] = max(maximum[kind], delta)
            tolerance = 1e-4 if kind == 0 else 1e-4 * max(1, abs(initial[0]))
            require(delta <= tolerance, '%s未闭合 %s: %.6g' % (label, name, delta))
            # 二阶单边差分：直接比较 1 帧右导数和 193 帧左导数。
            dr = [(-3*x + 4*y - z)/(2*h) for x, y, z in
                  zip(initial, right1[kind][name], right2[kind][name])]
            dl = [(3*x - 4*y + z)/(2*h) for x, y, z in
                  zip(final, left1[kind][name], left2[kind][name])]
            derivative_error = max(abs(x-y) for x, y in zip(dr, dl))
            derivative_tolerance = .002 if kind == 0 else .0005 * max(1, abs(initial[0]))
            require(derivative_error <= derivative_tolerance,
                    '%s接缝导数不连续 %s: %.6g' % (label, name, derivative_error))
    print('CHECK_LOOP', 'matrix_max_error=%.9g light_max_error=%.9g' % tuple(maximum))


def check_scene():
    assert sc.camera and sc.camera.name == 'cls_CAM_main', '尚未构建教室主相机'
    assert sc.camera.data.type == 'ORTHO', '主相机必须正交'
    require(bpy.data.objects['CAM_persp'].data.lens == 35, '透视相机焦距不是35mm')
    require(bpy.data.objects['CAM_closeup'].data.lens == 85, '近景相机焦距不是85mm')
    require((sc.frame_start, sc.frame_end, sc.render.fps) == (1, 192, 24), '帧范围或帧率错误')
    require(set(v.name for v in sc.view_layers) == {'BG', 'FG', 'CHAR'}, '视图层不完整')
    require(sc.view_layers['CHAR'].layer_collection.children['cls_fg'].holdout,
            'CHAR层中的FG未设置holdout')
    require(not any(o.type == 'MESH' for o in bpy.data.collections['cls_CHAR'].all_objects),
            'CHAR集合含人物网格')
    for name in ('CHAR_SPOT_1', 'CHAR_SPOT_2'):
        require(bpy.data.objects[name].type == 'EMPTY', name + '不是Empty')
    require(sc.render.film_transparent and sc.render.image_settings.color_mode == 'RGBA',
            '未配置透明RGBA输出')

    check_loop()
    deps = set_frame(1)
    for action in bpy.data.actions:
        if action.users:
            for fc in curves(action):
                require(any(m.type == 'CYCLES' for m in fc.modifiers),
                        '关键帧缺少Cycles: %s %s[%s]' % (action.name, fc.data_path, fc.array_index))
    blocks = list(bpy.data.objects) + list(bpy.data.lights) + list(bpy.data.materials) + list(bpy.data.node_groups)
    blocks += [m.node_tree for m in bpy.data.materials if m.node_tree]
    for block in blocks:
        ad = block.animation_data
        if ad:
            for fc in ad.drivers:
                require(fc.is_valid, '无效驱动: %s %s' % (block.name, fc.data_path))

    # 正交投影是仿射变换；每帧只构建一次系数，避免反复求逆相机矩阵。
    def projector():
        origin = world_to_camera_view(sc, sc.camera, Vector((0, 0, 0)))
        axes = [world_to_camera_view(sc, sc.camera, Vector(v)) - origin
                for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        def point(p):
            return (origin.x + sum(axes[i].x*p[i] for i in range(3)),
                    origin.y + sum(axes[i].y*p[i] for i in range(3)))
        def points_rect(points):
            ps = [point(p) for p in points]
            return min(p[0] for p in ps), min(p[1] for p in ps), max(p[0] for p in ps), max(p[1] for p in ps)
        return points_rect

    ui = bpy.data.objects['cls_board_ui_panel']
    board = bpy.data.objects['cls_board_chalk_surface']
    ui_eval = ui.evaluated_get(deps)
    ui_mesh = ui_eval.to_mesh()
    ui_area = 0.0
    try:
        for polygon in ui_mesh.polygons:
            vs = [ui_eval.matrix_world @ ui_mesh.vertices[i].co for i in polygon.vertices]
            ui_area += sum((vs[j]-vs[0]).cross(vs[j+1]-vs[0]).length/2 for j in range(1, len(vs)-1))
            material = ui_eval.material_slots[polygon.material_index].material
            require(material and material.name == 'cls_board_ui', 'UI面使用了错误材质')
    finally:
        ui_eval.to_mesh_clear()
    # 黑板局部X/Z平面面积，排除整间房绕Z旋转带来的世界包围盒膨胀。
    bounds = board.bound_box
    width = max(v[0] for v in bounds) - min(v[0] for v in bounds)
    height = max(v[2] for v in bounds) - min(v[2] for v in bounds)
    linear = board.matrix_world.to_3x3()
    board_area = (linear @ Vector((width, 0, 0))).cross(linear @ Vector((0, 0, height))).length
    ui_ratio = ui_area / board_area
    require(abs(ui_ratio - .6) < 1e-5, '实际UI面积比例不是60%%: %.8f' % ui_ratio)

    float_roots = [o for o in sc.objects if o.get('cls_float')]
    require(len(float_roots) >= 15, '缺少悬浮道具组')
    groups = [(root.name, [o for o in root.children_recursive if o.type in GEOMETRY and not o.hide_render])
              for root in float_roots]
    singles = [o for o in sc.objects if (o.get('cls_flame') or o.get('cls_dust'))
               and o.type in GEOMETRY and not o.hide_render]
    dynamic = {o for _, parts in groups for o in parts} | set(singles)
    # 背景和雾属于非关键背景；所有其他可见实体均检查左侧图标留白。
    critical = [o for o in sc.objects if o.type in GEOMETRY and not o.hide_render
                and not o.get('cls_dust') and not o.name.startswith(('cls_backdrop', 'cls_haze'))]
    static = set(critical) - dynamic
    critical_names = {o.name for o in critical}
    overlaps_found, left_hits = {}, {}
    for frame in range(1, 193):
        deps = set_frame(frame)
        project = projector()
        def bounds_of(ob):
            evaluated = ob.evaluated_get(deps)
            return project(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
        rects = {o.name: bounds_of(o) for o in dynamic | (static if frame == 1 else set())}
        ui_rect = bounds_of(ui)
        # C1实际Empty的本地1.5×1.5×2.4米净空；随其位置/房间旋转一起求投影。
        spot = bpy.data.objects['CHAR_SPOT_1'].evaluated_get(deps)
        c1 = project(spot.matrix_world @ Vector((dx, dy, z))
                     for dx in (-.75, .75) for dy in (-.75, .75) for z in (0, 2.4))
        require(ui_rect[0] >= LEFT_SAFE - 1e-6, 'UI进入左15%%: 帧%d' % frame)
        tested = [(name, union([rects[o.name] for o in parts])) for name, parts in groups if parts]
        tested += [(o.name, rects[o.name]) for o in singles]
        for name, rectangle in tested:
            for label, protected in (('UI', ui_rect), ('C1', c1)):
                if overlaps(rectangle, protected):
                    overlaps_found.setdefault((name, label), []).append(frame)
        for name, rectangle in rects.items():
            if name in critical_names and rectangle[0] < LEFT_SAFE - 1e-6:
                left_hits.setdefault(name, []).append(frame)
    for (name, area), frames in overlaps_found.items():
        errors.append('动态投影重叠 %s / %s: %d帧，首帧%d' % (name, area, len(frames), frames[0]))
    for name, frames in left_hits.items():
        errors.append('关键物体进入左15%% %s: 首帧%d' % (name, frames[0]))

    # 重新评估修改器与链接实例；不读取cls_evaluated_triangles等缓存属性。
    deps = set_frame(1)
    triangles = 0
    for instance in deps.object_instances:
        ob = instance.object
        if ob.type in GEOMETRY:
            mesh = ob.to_mesh()
            if mesh:
                mesh.calc_loop_triangles()
                triangles += len(mesh.loop_triangles)
                ob.to_mesh_clear()
    require(triangles < 3_000_000, '评估三角面超预算: %d' % triangles)
    print('CHECK_GEOMETRY', 'frames=192 float_groups=%d animated_meshes=%d triangles=%d ui_ratio=%.8f'
          % (len(groups), len(singles), triangles, ui_ratio))
    if errors:
        for error in errors:
            print('CLASSROOM_ACCEPTANCE_FAILURE', error)
        raise AssertionError('教室独立验收失败，共%d项' % len(errors))
    print('CLASSROOM_ACCEPTANCE_PASS')


old_frame, old_subframe = sc.frame_current, sc.frame_subframe
old_layer = bpy.context.window.view_layer if bpy.context.window else None
try:
    if bpy.context.window and 'BG' in sc.view_layers:
        bpy.context.window.view_layer = sc.view_layers['BG']
    check_scene()
finally:
    sc.frame_set(old_frame, subframe=old_subframe)
    if old_layer:
        bpy.context.window.view_layer = old_layer
