# -*- coding: utf-8 -*-
"""
把人物模型（FBX）导入共生岛场景，替换占位人物。
在已打开 gongshengdao_scene.blend（或运行过 gongshengdao_scene.py）的 Blender 里运行。

做的事情：
  1. 如果 FBX 是分卷（.part_00, .part_01 …）就先合并
  2. 删除旧的占位人物，导入 FBX 放进 “CHAR_人物” 集合，删掉绑定控件形状（cs_*）
  3. 按贴图重建材质：卡通着色（复用场景的 ToonCore 节点组）+ 透明通道 + 描边材质
  4. 缩放到身高 CHAR_TARGET_HEIGHT，放在门廊台阶前，面朝镜头
  5. 新建近景相机 CAM_closeup（85mm 胸像）
控制台：
  gsd_char.render_closeup()          渲染近景测试图
"""
import bpy
import os
import math
import hashlib
from mathutils import Vector

CHAR_DIR = "/Users/macbook/Desktop/共生岛/blender/characters/elaina"
FBX_NAME = "YLN_GYRemakeF3.fbx"
FBX_MD5 = "2397966c4927de44101da895633e3113"
CHAR_TARGET_HEIGHT = 1.55      # 不含帽子的身高（场景单位≈米）
CHAR_POS = getattr(__import__("builtins"), "GSD_CHAR_POS", (-2.7, -0.9, 0.45))  # 门廊台阶前（v4 场景会改写）
CAM_AZIMUTH = getattr(__import__("builtins"), "GSD_CAM_AZ", 35.0)

TEX = {  # 材质名 → 贴图
    "body": "body_F_Sketchfab.png",
    "cloth": "cloth_F_Sketchfab.png",
    "cloth_B": "cloth_B_Sketchfab.png",
    "eye": "eye_F_Sketchfab.png",
    "eyebrow": "eyebrow_F_Sketchfab.png",
    "hair": "hair_F_Sketchfab.png",
}
ALPHA_MATS = {"hair", "eyebrow", "eye", "cloth", "cloth_B"}
LINE_COLOR = (0.08, 0.05, 0.06)


def ensure_fbx():
    path = os.path.join(CHAR_DIR, FBX_NAME)
    if not os.path.exists(path):
        parts = sorted(f for f in os.listdir(CHAR_DIR) if f.startswith("YLN.fbx.part_"))
        if not parts:
            raise FileNotFoundError("找不到 FBX 或分卷文件：" + CHAR_DIR)
        with open(path, "wb") as out:
            for p in parts:
                with open(os.path.join(CHAR_DIR, p), "rb") as f:
                    out.write(f.read())
    md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
    if md5 != FBX_MD5:
        raise RuntimeError(f"FBX 校验失败：{md5}")
    return path


def remove_old_character(coll):
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for child in list(coll.children):
        for ob in list(child.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(child)


def find_layer_collection(lc, name):
    if lc.collection.name == name:
        return lc
    for c in lc.children:
        r = find_layer_collection(c, name)
        if r:
            return r
    return None


def lin(rgb):
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


def build_material(mat, toon_group):
    base = mat.name.split(".")[0]
    nt = mat.node_tree
    if base.endswith("_Line"):
        # 反向外壳描边：只渲染背面，纯深色
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*lin(LINE_COLOR), 1)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        mat.use_backface_culling = True
        return
    if base not in TEX:
        return
    nt.nodes.clear()
    img_path = os.path.join(CHAR_DIR, "textures", TEX[base])
    img = bpy.data.images.load(img_path, check_existing=True)
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.location = (-500, 0)
    g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = toon_group; g.location = (-200, 0)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(tex.outputs["Color"], g.inputs["Color"])
    if base in ALPHA_MATS:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent"); tr.location = (-200, -150)
        mix = nt.nodes.new("ShaderNodeMixShader"); mix.location = (100, 0)
        nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
        nt.links.new(g.outputs["Shader"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            mat.blend_method = "HASHED"
    else:
        nt.links.new(g.outputs["Shader"], out.inputs["Surface"])


def world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    for ob in objs:
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def eval_bbox(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
        ev.to_mesh_clear()
    return lo, hi


def place():
    """按“摆好姿势后的实际网格”缩放到目标身高，脚底落地，人物中心对准 CHAR_POS，再转向镜头"""
    coll = bpy.data.collections["CHAR_人物"]
    fit = bpy.data.objects["CHAR_fit"]
    pivot = bpy.data.objects["CHAR_root"]
    meshes = [o for o in coll.all_objects if o.type == "MESH"]
    body = [o for o in meshes if o.name.split(".")[0] == "body"] or meshes
    pivot.rotation_euler = (0, 0, 0)
    pivot.location = CHAR_POS
    fit.scale = (1, 1, 1)
    fit.location = (0, 0, 0)
    bpy.context.view_layer.update()
    lo, hi = eval_bbox(body)
    s = CHAR_TARGET_HEIGHT / max(hi.z - lo.z, 1e-6)
    fit.scale = (s, s, s)
    bpy.context.view_layer.update()
    lo, hi = eval_bbox(meshes)
    blo, bhi = eval_bbox(body)
    target = Vector(CHAR_POS)
    delta = Vector(((target.x - (blo.x + bhi.x) / 2), (target.y - (blo.y + bhi.y) / 2), target.z - lo.z))
    # delta 在世界坐标里，换算到 pivot 局部（此时 pivot 未旋转、未缩放）
    fit.location = fit.location + delta
    pivot.rotation_euler = (0, 0, math.radians(CAM_AZIMUTH))
    bpy.context.view_layer.update()
    lo, hi = eval_bbox(body)
    print(f"[共生岛] 人物身高 {hi.z-lo.z:.3f}，脚底 z={lo.z:.3f}，中心 ({(lo.x+hi.x)/2:.2f}, {(lo.y+hi.y)/2:.2f})")
    return s


def import_character():
    sc = bpy.context.scene
    path = ensure_fbx()
    coll = bpy.data.collections.get("CHAR_人物")
    if coll is None:
        coll = bpy.data.collections.new("CHAR_人物")
        sc.collection.children.link(coll)
    remove_old_character(coll)
    vl = sc.view_layers["BG"] if "BG" in sc.view_layers else bpy.context.view_layer
    if bpy.context.window:
        bpy.context.window.view_layer = vl
    lc = find_layer_collection(vl.layer_collection, coll.name)
    lc.exclude = False
    vl.active_layer_collection = lc

    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=False, ignore_leaf_bones=True,
                             automatic_bone_orientation=False, use_image_search=False)
    new = [o for o in bpy.data.objects if o not in before]
    # 删除绑定控件形状和无用辅助物
    for o in list(new):
        if o.name.startswith(("cs_", "WGT", "Cube", "Mesh.")) and o.type == "MESH" and not o.modifiers:
            new.remove(o)
            bpy.data.objects.remove(o, do_unlink=True)
    for o in new:
        if o.name not in coll.objects:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
    # 材质
    toon = bpy.data.node_groups.get("ToonCore")
    mats = {s.material for o in new if o.type == "MESH" for s in o.material_slots if s.material}
    for m in mats:
        build_material(m, toon)
    # 根节点：缩放 + 定位 + 朝向
    root = bpy.data.objects.new("CHAR_fit", None)
    root.empty_display_type = "ARROWS"
    coll.objects.link(root)
    tops = [o for o in new if o.parent is None]
    for o in tops:
        o.parent = root
    bpy.context.view_layer.update()
    pivot = bpy.data.objects.new("CHAR_root", None)
    pivot.empty_display_type = "PLAIN_AXES"
    coll.objects.link(pivot)
    pivot.location = CHAR_POS
    root.parent = pivot
    bpy.context.view_layer.update()
    s = place()
    # 描边：人物自带描边材质，Freestyle 线条对人物会显得太粗——这里保留 Freestyle，后续可单独关
    print(f"[共生岛] 已导入人物：{len(new)} 个物体，缩放 {s:.4f}，材质 {len(mats)} 个")
    return new


def build_closeup_camera():
    sc = bpy.context.scene
    cam = bpy.data.objects.get("CAM_closeup")
    if cam is None:
        cd = bpy.data.cameras.new("CAM_closeup")
        cam = bpy.data.objects.new("CAM_closeup", cd)
        sc.collection.objects.link(cam)
    cam.data.type = "PERSP"
    cam.data.lens = 85
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = 2.0
    x, y, z = CHAR_POS
    az = math.radians(CAM_AZIMUTH)
    head_z = z + CHAR_TARGET_HEIGHT * 0.86
    d = 2.6
    cam.location = (x + d * math.sin(az) - 0.15, y - d * math.cos(az), head_z + 0.05)
    tgt = bpy.data.objects.get("CAM_closeup_target") or bpy.data.objects.new("CAM_closeup_target", None)
    if tgt.name not in sc.collection.objects:
        sc.collection.objects.link(tgt)
    tgt.location = (x, y, head_z - 0.12)
    cam.data.dof.focus_object = tgt
    con = cam.constraints.get("Track To") or cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam


def render_closeup(name="closeup_test.png", time=None):
    sc = bpy.context.scene
    if time:
        import builtins
        builtins.gsd.apply_time(time)
    main_cam = sc.camera
    cam = build_closeup_camera()
    sc.camera = cam
    old_pct = sc.render.resolution_percentage
    sc.render.resolution_percentage = 50
    sc.render.film_transparent = False
    sc.render.use_compositing = True
    base = bpy.path.abspath("//") if bpy.data.filepath else "/tmp"
    sc.render.filepath = os.path.join(base, "render", name)
    try:
        bpy.ops.render.render(write_still=True, layer="BG")
    finally:
        sc.camera = main_cam
        sc.render.resolution_percentage = old_pct
    print("[共生岛] 近景已输出", sc.render.filepath)


class _API:
    import_character = staticmethod(import_character)
    render_closeup = staticmethod(render_closeup)
    place = staticmethod(place)
    build_closeup_camera = staticmethod(build_closeup_camera)


import builtins
builtins.gsd_char = _API

import_character()
build_closeup_camera()
