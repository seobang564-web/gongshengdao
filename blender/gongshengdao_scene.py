# -*- coding: utf-8 -*-
"""
共生岛 · Blender 场景（细化版 + 光影）
=====================================
在草稿版的布局上细化了所有场景元素，并加上光影：
  · 卡通着色：三阶明暗 + 灯光颜色混入（灯笼、窗户在地面上打出暖色光斑）
  · 太阳阴影：早晨低角度长影、中午短影、夜晚月光
  · 点光源：每盏灯笼、每扇窗户外都有暖光，按时段自动开关
  · 后期光晕：合成器 Glare(Bloom)，夜晚窗户、灯笼、萤火虫会发光晕
  · 水面：浅水环带、岸边白色浪花、水面高光闪点、瀑布水雾
  · 氛围：烟囱炊烟、夜晚萤火虫、飘落的樱花瓣

用法（Blender 4.2 及以上，已在 5.2 上测试）：
  Scripting 工作区 → 打开本文件 → ▶ Run Script
  控制台：
      gsd.apply_time("morning" / "noon" / "night")   切换时段
      gsd.preview()                                   渲染三个时段的半尺寸预览
      gsd.render_all()                                导出全部分层素材
  输出在 .blend 同目录的 render/ 文件夹（未保存时在系统临时目录）。

坐标约定：Z 朝上，1 单位 ≈ 1 米；相机从右前方斜俯视（正交）。
"""

import bpy
import bmesh
import math
import os
import random
import tempfile
from mathutils import Matrix, Euler, Vector

# ============================================================
# 配置
# ============================================================
RES_X, RES_Y = 2560, 1440
CAM_AZIMUTH = 35.0      # 相机绕 Z 轴的方位角（度），0 = 正前方(-Y)
CAM_ELEVATION = 40.0    # 相机俯角（度）
CAM_ORTHO_SCALE = 32.0  # 正交缩放：越大画面装得越多
CAM_TARGET = (1.5, 1.0, 0.0)
CAM_SHIFT_X = 0.07      # 正值让岛偏左，给右上角卡片留空
CAM_SHIFT_Y = 0.08      # 正值让岛偏下，给顶部远岛留位置
USE_OUTLINE = True      # Freestyle 描边
USE_BLOOM = True        # 后期光晕
SEED = 7

ISLAND_RX, ISLAND_RY = 10.0, 8.5
ISLAND_TOP = 0.45
CHAR_HEIGHT = 1.15

random.seed(SEED)

# ============================================================
# 基础工具
# ============================================================

def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                  bpy.data.cameras, bpy.data.node_groups):
        for item in list(block):
            if item.users == 0:
                block.remove(item)
    sc = bpy.context.scene
    if hasattr(sc, "compositing_node_group") and sc.compositing_node_group is not None:
        old = sc.compositing_node_group
        sc.compositing_node_group = None
        if old.users == 0:
            bpy.data.node_groups.remove(old)
    while len(sc.view_layers) > 1:
        sc.view_layers.remove(sc.view_layers[-1])


def new_collection(name, parent=None):
    coll = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def make_mesh_object(name, bm, coll, mat=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = scale
    coll.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def _add_prim(bm, kind, matrix, seg=10, top=1.0, sub=1):
    if kind == "cube":
        r = bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
    elif kind == "cyl":
        r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                  radius1=1.0, radius2=top, depth=1.0, matrix=matrix)
    elif kind == "cone":
        r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                  radius1=1.0, radius2=0.0, depth=1.0, matrix=matrix)
    elif kind == "ico":
        r = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0, matrix=matrix)
    elif kind == "sphere":
        r = bmesh.ops.create_uvsphere(bm, u_segments=max(seg, 12), v_segments=max(seg // 2, 6), radius=1.0, matrix=matrix)
    else:
        raise ValueError(kind)
    return r["verts"]


def _jitter(verts, amount):
    if amount <= 0:
        return
    for v in verts:
        v.co += Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1))) * amount


def shape(name, kind, coll, mat, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), seg=10, top=1.0, sub=1, jitter=0.0):
    """单个基本体。cube 边长1；cyl/cone 半径1 高1；ico/sphere 半径1；均以原点为中心"""
    bm = bmesh.new()
    vs = _add_prim(bm, kind, Matrix.Identity(4), seg, top, sub)
    _jitter(vs, jitter)
    return make_mesh_object(name, bm, coll, mat, loc, rot, scale)


def batch(name, kind, coll, mat, items, seg=8, top=1.0, sub=1, jitter=0.0):
    """把很多个同材质小物件合并成一个物体（草丛、石子、花瓣……），渲染和操作都更快。
    items: [(loc, scale, rot), ...]；jitter 按各自尺寸的比例随机扰动顶点"""
    if not items:
        return None
    bm = bmesh.new()
    for loc, sc, rot in items:
        m = Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(sc))
        vs = _add_prim(bm, kind, m, seg, top, sub)
        _jitter(vs, jitter * min(sc))
    return make_mesh_object(name, bm, coll, mat)


def from_pydata(name, verts, faces, coll, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def catmull(points, steps=8):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(tuple(points[-1]))
    return out


def ribbon(name, points, width, z, coll, mat, steps=8, wobble=0.15):
    """沿曲线生成贴地平面带（土路、小溪）。返回 (物体, 平滑后的中线点, 每点法线)"""
    pts = catmull(points, steps)
    verts, faces, normals = [], [], []
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        normals.append((nx, ny))
        w = width * (1 - wobble + wobble * math.sin(i * 0.9))
        verts.append((x + nx * w / 2, y + ny * w / 2, z))
        verts.append((x - nx * w / 2, y - ny * w / 2, z))
    for i in range(len(pts) - 1):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    return from_pydata(name, verts, faces, coll, mat), pts, normals


def ring_band(name, ring, s_in, s_out, z, coll, mat, cx=0.0, cy=0.0):
    """沿闭合轮廓生成环带（浅水、浪花）"""
    n = len(ring)
    verts = [(cx + (x - cx) * s_in, cy + (y - cy) * s_in, z) for x, y in ring] + \
            [(cx + (x - cx) * s_out, cy + (y - cy) * s_out, z) for x, y in ring]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return from_pydata(name, verts, faces, coll, mat)


# ============================================================
# 材质：卡通着色 + 灯光颜色混入 + 全局时段色调
# ============================================================
TOON = None
GLOW_MATS = []        # (材质, {时段: 强度})
LIGHTS = []           # (灯光物体, {时段: 功率})
WALKABLE = set()


def lin(rgb):
    """sRGB(屏幕上看到的颜色) → 线性值（Blender 材质颜色按线性解释）"""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


def build_toon_group():
    """输出 = 底色 × (阶梯明暗 × 时段色调 × 0.78 + 实际光照颜色 × 0.32)
    阶梯明暗给出卡通分层；实际光照颜色让灯笼、窗户的暖光能染到地面上。"""
    ng = bpy.data.node_groups.new("ToonCore", "ShaderNodeTree")
    ng.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    n, l = ng.nodes, ng.links
    gi = n.new("NodeGroupInput"); gi.location = (-900, 0)
    go = n.new("NodeGroupOutput"); go.location = (900, 0)
    diff = n.new("ShaderNodeBsdfDiffuse"); diff.location = (-700, 250)
    s2r = n.new("ShaderNodeShaderToRGB"); s2r.location = (-500, 250)
    ramp = n.new("ShaderNodeValToRGB"); ramp.location = (-300, 350)
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.34, 0.32, 0.50, 1)   # 阴影：偏冷紫
    cr.elements[1].position = 0.16
    cr.elements[1].color = (0.62, 0.60, 0.70, 1)   # 过渡
    e = cr.elements.new(0.42)
    e.color = (1.0, 1.0, 1.0, 1)                    # 受光
    tint = n.new("ShaderNodeRGB"); tint.name = "TimeTint"; tint.label = "时段色调"
    tint.location = (-300, 50)
    tint.outputs[0].default_value = (1, 1, 1, 1)
    m_tint = n.new("ShaderNodeVectorMath"); m_tint.operation = "MULTIPLY"; m_tint.location = (0, 300)
    s_tone = n.new("ShaderNodeVectorMath"); s_tone.operation = "SCALE"; s_tone.location = (180, 300)
    s_tone.inputs["Scale"].default_value = 0.78
    clamp = n.new("ShaderNodeVectorMath"); clamp.operation = "MINIMUM"; clamp.location = (0, 100)
    clamp.inputs[1].default_value = (1.6, 1.6, 1.6)
    s_light = n.new("ShaderNodeVectorMath"); s_light.operation = "SCALE"; s_light.location = (180, 100)
    s_light.inputs["Scale"].default_value = 0.32
    add = n.new("ShaderNodeVectorMath"); add.operation = "ADD"; add.location = (380, 200)
    mul = n.new("ShaderNodeVectorMath"); mul.operation = "MULTIPLY"; mul.location = (560, 100)
    emit = n.new("ShaderNodeEmission"); emit.location = (740, 0)
    l.new(diff.outputs["BSDF"], s2r.inputs["Shader"])
    l.new(s2r.outputs["Color"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], m_tint.inputs[0])
    l.new(tint.outputs["Color"], m_tint.inputs[1])
    l.new(m_tint.outputs["Vector"], s_tone.inputs[0])
    l.new(s2r.outputs["Color"], clamp.inputs[0])
    l.new(clamp.outputs["Vector"], s_light.inputs[0])
    l.new(s_tone.outputs["Vector"], add.inputs[0])
    l.new(s_light.outputs["Vector"], add.inputs[1])
    l.new(add.outputs["Vector"], mul.inputs[0])
    l.new(gi.outputs["Color"], mul.inputs[1])
    l.new(mul.outputs["Vector"], emit.inputs["Color"])
    l.new(emit.outputs["Emission"], go.inputs["Shader"])
    return ng


def _new_material(name):
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    m.node_tree.nodes.clear()
    return m


def toon(name, rgb):
    rgb = lin(rgb)
    m = _new_material(name)
    nt = m.node_tree
    g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = TOON
    g.inputs["Color"].default_value = (*rgb, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(g.outputs["Shader"], out.inputs["Surface"])
    m.diffuse_color = (*rgb, 1)
    return m


def glow(name, rgb, strengths):
    """自发光材质。strengths = {"morning": x, "noon": y, "night": z}"""
    rgb = lin(rgb)
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strengths["night"]
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = (*rgb, 1)
    GLOW_MATS.append((m, strengths))
    return m


def flat_emit(name, rgb):
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


PALETTE = {
    # 水
    "sea": (0.14, 0.42, 0.72), "shallow": (0.30, 0.68, 0.82), "stream": (0.42, 0.78, 0.92), "foam": (0.92, 0.97, 1.0),
    # 地面
    "grass": (0.47, 0.72, 0.28), "grass_light": (0.62, 0.82, 0.36), "grass_dark": (0.30, 0.54, 0.20),
    "cliff": (0.58, 0.46, 0.34), "dirt": (0.50, 0.38, 0.26), "path": (0.88, 0.75, 0.53), "path_edge": (0.74, 0.60, 0.42),
    "soil": (0.42, 0.29, 0.20),
    # 石头
    "rock": (0.62, 0.62, 0.64), "rock_dark": (0.45, 0.46, 0.50), "rock_warm": (0.66, 0.60, 0.54), "moss": (0.38, 0.56, 0.26),
    # 木头与房屋
    "wood": (0.50, 0.32, 0.19), "wood_dark": (0.36, 0.22, 0.13), "wood_light": (0.76, 0.56, 0.36),
    "wall": (0.95, 0.88, 0.74), "roof": (0.30, 0.47, 0.40), "roof_dark": (0.22, 0.37, 0.32), "stone": (0.68, 0.64, 0.58),
    "glass_day": (0.55, 0.70, 0.80),
    # 植物
    "trunk": (0.42, 0.28, 0.18), "leaf": (0.33, 0.60, 0.26), "leaf2": (0.42, 0.68, 0.30), "leaf3": (0.55, 0.76, 0.34),
    "pine": (0.18, 0.43, 0.28), "pine2": (0.24, 0.52, 0.32),
    "sakura": (0.99, 0.74, 0.83), "sakura2": (0.96, 0.60, 0.74), "sakura3": (1.0, 0.86, 0.90),
    "reed": (0.52, 0.66, 0.30), "cattail": (0.48, 0.32, 0.20), "lily": (0.32, 0.58, 0.32),
    # 花
    "white": (0.97, 0.96, 0.92), "pink": (0.98, 0.56, 0.70), "purple": (0.62, 0.52, 0.92), "yellow": (0.99, 0.84, 0.32),
    "orange": (0.98, 0.62, 0.28), "red": (0.88, 0.32, 0.30), "blue": (0.45, 0.62, 0.95),
    # 道具
    "boat": (0.64, 0.46, 0.28), "laptop": (0.78, 0.80, 0.84), "screen": (0.25, 0.30, 0.40), "mug": (0.95, 0.94, 0.90),
    "book_red": (0.80, 0.36, 0.34), "book_blue": (0.36, 0.52, 0.78), "book_green": (0.40, 0.62, 0.42),
    "rope": (0.82, 0.72, 0.52), "metal": (0.30, 0.30, 0.34), "pot": (0.78, 0.46, 0.32),
    "cat": (0.98, 0.66, 0.32), "beak": (0.98, 0.62, 0.20), "black": (0.12, 0.10, 0.10),
    # 人物
    "skin": (1.0, 0.86, 0.76), "hair": (0.44, 0.28, 0.18), "shirt": (0.97, 0.93, 0.85), "skirt": (0.26, 0.40, 0.32),
    "shoe": (0.40, 0.26, 0.18), "eye": (0.20, 0.14, 0.12), "leaf_clip": (0.45, 0.72, 0.36),
    # 远景
    "far_island": (0.38, 0.60, 0.44), "far_tree": (0.30, 0.52, 0.38),
}


def build_materials():
    global TOON
    TOON = build_toon_group()
    M = {k: toon("T_" + k, v) for k, v in PALETTE.items()}
    # 自发光：早 / 中 / 晚强度
    M["window"] = glow("G_window", (1.0, 0.74, 0.40), {"morning": 1.1, "noon": 0.35, "night": 5.0})
    M["lantern"] = glow("G_lantern", (1.0, 0.80, 0.48), {"morning": 1.6, "noon": 0.4, "night": 7.0})
    M["firefly"] = glow("G_firefly", (0.85, 1.0, 0.55), {"morning": 0.0, "noon": 0.0, "night": 10.0})
    M["sparkle"] = glow("G_sparkle", (1.0, 0.97, 0.88), {"morning": 3.0, "noon": 2.2, "night": 1.4})
    M["laptop_screen"] = glow("G_screen", (0.70, 0.85, 1.0), {"morning": 0.8, "noon": 0.6, "night": 2.5})
    M["mask_white"] = flat_emit("MASK_white", (1, 1, 1))
    M["mask_black"] = flat_emit("MASK_black", (0, 0, 0))
    return M


def point_light(coll, name, loc, rgb, powers, radius=0.12):
    ld = bpy.data.lights.new(name, "POINT")
    ld.color = lin(rgb)
    ld.energy = powers["night"]
    try:
        ld.shadow_soft_size = radius
    except AttributeError:
        pass
    ld.use_shadow = True
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    coll.objects.link(ob)
    LIGHTS.append((ob, powers))
    return ob


LANTERN_POWER = {"morning": 10.0, "noon": 0.0, "night": 160.0}
WINDOW_POWER = {"morning": 15.0, "noon": 0.0, "night": 260.0}


# ============================================================
# 地形
# ============================================================

def island_radius(theta):
    return 1.0 + 0.07 * math.sin(3 * theta + 0.5) + 0.05 * math.sin(5 * theta + 1.3) + 0.03 * math.sin(9 * theta)


def island_edge(theta, k=1.0):
    r = island_radius(theta) * k
    return (ISLAND_RX * r * math.cos(theta), ISLAND_RY * r * math.sin(theta))


def inside_island(x, y, margin=0.9):
    t = math.atan2(y / ISLAND_RY, x / ISLAND_RX)
    r = math.hypot(x / ISLAND_RX, y / ISLAND_RY)
    return r < island_radius(t) * margin


def blob_island(name_top, name_side, cx, cy, rx, ry, top, bottom, coll, mat_top, mat_side, n=64, radius_fn=None):
    rf = radius_fn or (lambda t: 1.0 + 0.08 * math.sin(4 * t + cx) + 0.05 * math.sin(7 * t + cy))
    ring = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = rf(t)
        ring.append((cx + rx * r * math.cos(t), cy + ry * r * math.sin(t)))
    verts = [(cx, cy, top)] + [(x, y, top) for x, y in ring]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    top_ob = from_pydata(name_top, verts, faces, coll, mat_top)
    # 岸壁分两层：上层泥土、下层岩石，向下收窄
    verts, faces = [], []
    levels = [(top, 1.0), (top - 0.35, 0.985), (bottom, 0.93)]
    for zz, k in levels:
        for x, y in ring:
            verts.append((cx + (x - cx) * k, cy + (y - cy) * k, zz))
    for L in range(len(levels) - 1):
        for i in range(n):
            j = (i + 1) % n
            faces.append((L * n + i, (L + 1) * n + i, (L + 1) * n + j, L * n + j))
    side_ob = from_pydata(name_side, verts, faces, coll, mat_side)
    return top_ob, side_ob, ring


def scatter_on_island(count, avoid, margin=0.88, tries=4000):
    """在岛面上随机撒点，避开 avoid 中的圆形区域 [(x, y, r), ...]"""
    pts = []
    for _ in range(tries):
        if len(pts) >= count:
            break
        x, y = random.uniform(-ISLAND_RX, ISLAND_RX), random.uniform(-ISLAND_RY, ISLAND_RY)
        if not inside_island(x, y, margin):
            continue
        if any((x - ax) ** 2 + (y - ay) ** 2 < ar * ar for ax, ay, ar in avoid):
            continue
        pts.append((x, y))
    return pts


# ============================================================
# 植物
# ============================================================

def tree(prefix, coll, M, x, y, z, h=3.2, r=1.5, kind="round", leaf=("leaf", "leaf2", "leaf3")):
    s = h / 3.2
    # 树干 + 根部
    shape(prefix + "_trunk", "cyl", coll, M["trunk"], loc=(x, y, z + h * 0.32), scale=(0.17 * s, 0.17 * s, h * 0.64), seg=7, top=0.65, jitter=0.02)
    shape(prefix + "_root", "cone", coll, M["trunk"], loc=(x, y, z + 0.12), scale=(0.34 * s, 0.34 * s, 0.35), seg=7)
    if kind == "pine":
        tiers = 4
        items = []
        for k in range(tiers):
            rr = r * (1.0 - k * 0.2)
            items.append(((x, y, z + h * (0.45 + k * 0.22)), (rr, rr, h * 0.36), (0, 0, random.uniform(0, 1))))
        batch(prefix + "_pine", "cone", coll, M["pine"], items[::2], seg=9, jitter=0.05)
        batch(prefix + "_pine_b", "cone", coll, M["pine2"], items[1::2], seg=9, jitter=0.05)
    else:
        # 树冠：深色在下、浅色在上，形成体积感
        groups = {leaf[0]: [], leaf[1]: [], leaf[2]: []}
        n = 7
        for k in range(n):
            a = 2 * math.pi * k / n + random.uniform(-0.3, 0.3)
            d = r * random.uniform(0.35, 0.7) if k else 0
            zz = z + h * 0.78 + random.uniform(-0.25, 0.5)
            ss = r * random.uniform(0.55, 0.8)
            key = leaf[0] if zz < z + h * 0.8 else (leaf[1] if k % 2 else leaf[2])
            groups[key].append(((x + d * math.cos(a), y + d * math.sin(a), zz), (ss, ss, ss * 0.85), (0, 0, 0)))
        groups[leaf[2]].append(((x - r * 0.15, y - r * 0.15, z + h * 0.78 + r * 0.55), (r * 0.5, r * 0.5, r * 0.42), (0, 0, 0)))
        for key, items in groups.items():
            batch(f"{prefix}_{key}", "ico", coll, M[key], items, sub=2, jitter=0.08)


def bush(prefix, coll, M, x, y, z, r=0.6, flowers=None):
    items = []
    for k in range(4):
        a = 2 * math.pi * k / 4
        items.append(((x + r * 0.45 * math.cos(a), y + r * 0.45 * math.sin(a), z + r * 0.35), (r * 0.6, r * 0.6, r * 0.5), (0, 0, 0)))
    batch(prefix, "ico", coll, M["grass_dark"], items, sub=1, jitter=0.1)
    if flowers:
        pts = [((x + random.uniform(-r, r) * 0.8, y + random.uniform(-r, r) * 0.6, z + r * 0.6 + random.uniform(0, 0.15)),
                (0.08, 0.08, 0.08), (0, 0, 0)) for _ in range(8)]
        batch(prefix + "_fl", "ico", coll, M[flowers], pts, sub=1)


def flower_patch(prefix, coll, M, cx, cy, z, spread=0.9, n=16, colors=("pink", "white", "purple", "yellow")):
    stems = []
    heads = {c: [] for c in colors}
    for i in range(n):
        x, y = cx + random.uniform(-spread, spread), cy + random.uniform(-spread * 0.6, spread * 0.6)
        hgt = random.uniform(0.18, 0.35)
        stems.append(((x, y, z + hgt / 2), (0.015, 0.015, hgt), (0, 0, 0)))
        s = random.uniform(0.08, 0.13)
        heads[colors[i % len(colors)]].append(((x, y, z + hgt), (s, s, s * 0.7), (0, 0, 0)))
    batch(prefix + "_stem", "cyl", coll, M["grass_dark"], stems, seg=4)
    for c, items in heads.items():
        batch(f"{prefix}_{c}", "ico", coll, M[c], items, sub=1)
    batch(prefix + "_leaves", "ico", coll, M["grass_dark"],
          [((cx + random.uniform(-spread, spread) * 0.8, cy + random.uniform(-spread, spread) * 0.5, z + 0.08), (0.22, 0.22, 0.1), (0, 0, 0)) for _ in range(5)],
          sub=1, jitter=0.1)


def grass_tufts(prefix, coll, M, pts, z):
    dark, light = [], []
    for i, (x, y) in enumerate(pts):
        for k in range(3):
            a = k * 2.1 + random.uniform(0, 1)
            tilt = 0.35
            h = random.uniform(0.18, 0.32)
            item = ((x + 0.05 * math.cos(a), y + 0.05 * math.sin(a), z + h / 2),
                    (0.035, 0.035, h), (tilt * math.cos(a + 1.57), tilt * math.sin(a + 1.57), 0))
            (dark if (i + k) % 3 else light).append(item)
    batch(prefix + "_dark", "cone", coll, M["grass_dark"], dark, seg=4)
    batch(prefix + "_light", "cone", coll, M["grass_light"], light, seg=4)


def reeds(prefix, coll, M, cx, cy, n=8, base_z=0.0):
    stalks, tops = [], []
    for _ in range(n):
        x, y = cx + random.uniform(-0.5, 0.5), cy + random.uniform(-0.35, 0.35)
        h = random.uniform(0.7, 1.2)
        tl = random.uniform(-0.12, 0.12)
        stalks.append(((x, y, base_z + h / 2), (0.03, 0.03, h), (tl, -tl, 0)))
        if random.random() < 0.5:
            tops.append(((x + tl * h * 0.5, y + tl * h * 0.5, base_z + h * 0.92), (0.05, 0.05, 0.16), (tl, -tl, 0)))
    batch(prefix + "_stalk", "cone", coll, M["reed"], stalks, seg=4)
    batch(prefix + "_top", "cyl", coll, M["cattail"], tops, seg=6)


# ============================================================
# 道具
# ============================================================

def lantern(prefix, coll, LC, M, x, y, z, h=1.25):
    """石座 + 木柱 + 灯箱（发光玻璃 + 木框）+ 尖顶，附带暖色点光源"""
    shape(prefix + "_base", "cyl", coll, M["stone"], loc=(x, y, z + 0.08), scale=(0.16, 0.16, 0.16), seg=6, jitter=0.01)
    shape(prefix + "_post", "cube", coll, M["wood_dark"], loc=(x, y, z + h / 2), scale=(0.09, 0.09, h))
    zc = z + h + 0.12
    shape(prefix + "_glass", "cube", coll, M["lantern"], loc=(x, y, zc), scale=(0.22, 0.22, 0.26))
    frame = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            frame.append(((x + sx * 0.12, y + sy * 0.12, zc), (0.035, 0.035, 0.3), (0, 0, 0)))
    frame.append(((x, y, zc - 0.15), (0.3, 0.3, 0.04), (0, 0, 0)))
    batch(prefix + "_frame", "cube", coll, M["wood_dark"], frame)
    shape(prefix + "_cap", "cone", coll, M["roof_dark"], loc=(x, y, zc + 0.24), scale=(0.26, 0.26, 0.2), seg=4, rot=(0, 0, math.pi / 4))
    point_light(LC, prefix + "_light", (x, y, zc), (1.0, 0.72, 0.42), LANTERN_POWER)


def fence(prefix, coll, M, a, b, z, n=6, h=0.8):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ln = math.hypot(b[0] - a[0], b[1] - a[1])
    posts, caps = [], []
    for i in range(n + 1):
        t = i / n
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        posts.append(((px, py, z + h / 2), (0.11, 0.11, h), (0, 0, ang)))
        caps.append(((px, py, z + h + 0.04), (0.08, 0.08, 0.08), (0, 0, ang + math.pi / 4)))
    batch(prefix + "_post", "cube", coll, M["wood"], posts)
    batch(prefix + "_cap", "cone", coll, M["wood_dark"], caps, seg=4)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    rails = [((mx, my, z + hz), (ln, 0.06, 0.07), (0, 0, ang)) for hz in (h * 0.4, h * 0.78)]
    batch(prefix + "_rail", "cube", coll, M["wood_light"], rails)


def potted_plant(prefix, coll, M, x, y, z, flower="pink"):
    shape(prefix + "_pot", "cyl", coll, M["pot"], loc=(x, y, z + 0.13), scale=(0.15, 0.15, 0.26), seg=8, top=1.25)
    shape(prefix + "_leaf", "ico", coll, M["leaf2"], loc=(x, y, z + 0.36), scale=(0.2, 0.2, 0.18), sub=1, jitter=0.03)
    batch(prefix + "_fl", "ico", coll, M[flower],
          [((x + random.uniform(-0.12, 0.12), y + random.uniform(-0.12, 0.12), z + 0.46), (0.06, 0.06, 0.06), (0, 0, 0)) for _ in range(4)])


def smoke(prefix, coll, M, x, y, z):
    items = []
    for k in range(5):
        s = 0.18 + k * 0.07
        items.append(((x + k * 0.18, y + k * 0.08, z + k * 0.42), (s, s, s * 0.85), (0, 0, 0)))
    batch(prefix, "ico", coll, M["white"], items, sub=2, jitter=0.15)


def cat(prefix, coll, M, x, y, z, rz=0.0):
    """睡觉的橘猫（效果图门廊上那只）"""
    root = bpy.data.objects.new(prefix, None)
    root.location = (x, y, z)
    root.rotation_euler = (0, 0, rz)
    coll.objects.link(root)
    parts = [("body", "sphere", "cat", (0, 0, 0.12), (0.28, 0.18, 0.13)),
             ("head", "sphere", "cat", (0.26, 0.04, 0.16), (0.13, 0.12, 0.11)),
             ("ear1", "cone", "cat", (0.29, 0.10, 0.27), (0.04, 0.04, 0.07)),
             ("ear2", "cone", "cat", (0.29, -0.02, 0.27), (0.04, 0.04, 0.07)),
             ("tail", "cyl", "cat", (-0.2, -0.14, 0.06), (0.04, 0.04, 0.3))]
    for nm, kind, mat, loc, sc in parts:
        ob = shape(f"{prefix}_{nm}", kind, coll, M[mat], loc=loc, scale=sc, seg=6,
                   rot=(math.pi / 2, 0, 0.6) if nm == "tail" else (0, 0, 0))
        ob.parent = root


# ============================================================
# 建筑
# ============================================================

def build_house(coll, LC, M, x, y, z):
    W, D, H = 4.4, 3.6, 2.3
    zb = z + 0.4       # 墙底
    zr = zb + H        # 屋檐
    rh = 1.9           # 屋顶高
    ov = 0.5           # 屋檐出挑

    # 石砌地基：一圈不规则石块
    stones = []
    for side, (ax, ay, bx, by) in enumerate(((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1))):
        n = 9 if side % 2 == 0 else 7
        for i in range(n):
            t = (i + 0.5) / n
            px = x + (ax + (bx - ax) * t) * (W / 2 + 0.12)
            py = y + (ay + (by - ay) * t) * (D / 2 + 0.12)
            for lvl in range(2):
                stones.append(((px + random.uniform(-0.05, 0.05), py + random.uniform(-0.05, 0.05), z + 0.1 + lvl * 0.2),
                               (0.26 + random.uniform(0, 0.12), 0.26 + random.uniform(0, 0.12), 0.11), (0, 0, random.uniform(0, 1))))
    batch("house_stones", "ico", coll, M["stone"], stones, sub=1, jitter=0.08)
    shape("house_floor", "cube", coll, M["stone"], loc=(x, y, z + 0.2), scale=(W + 0.1, D + 0.1, 0.4))

    # 墙体 + 半木结构（立柱、横梁、斜撑）
    shape("house_wall", "cube", coll, M["wall"], loc=(x, y, zb + H / 2), scale=(W, D, H))
    beams = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            beams.append(((x + sx * W / 2, y + sy * D / 2, zb + H / 2), (0.2, 0.2, H), (0, 0, 0)))
    for zz in (zb + 0.05, zb + H * 0.52, zb + H - 0.05):
        beams.append(((x, y - D / 2 - 0.02, zz), (W, 0.12, 0.14), (0, 0, 0)))
        beams.append(((x + W / 2 + 0.02, y, zz), (0.12, D, 0.14), (0, 0, 0)))
    for px in (x - W * 0.08, x + W * 0.38):
        beams.append(((px, y - D / 2 - 0.02, zb + H / 2), (0.14, 0.12, H), (0, 0, 0)))
    for py in (y - D * 0.05,):
        beams.append(((x + W / 2 + 0.02, py, zb + H / 2), (0.12, 0.14, H), (0, 0, 0)))
    # 斜撑
    beams.append(((x - W * 0.3, y - D / 2 - 0.03, zb + H * 0.26), (0.1, 0.1, 1.1), (0, math.radians(50), 0)))
    beams.append(((x + W / 2 + 0.03, y + D * 0.3, zb + H * 0.26), (0.1, 0.1, 1.0), (math.radians(-50), 0, 0)))
    batch("house_beams", "cube", coll, M["wood_dark"], beams)

    # 山墙（三角）
    gv = [(x - W / 2, y - D / 2, zr), (x - W / 2, y + D / 2, zr), (x - W / 2, y, zr + rh - 0.15),
          (x + W / 2, y - D / 2, zr), (x + W / 2, y + D / 2, zr), (x + W / 2, y, zr + rh - 0.15)]
    from_pydata("house_gable", gv, [(0, 1, 2), (3, 5, 4)], coll, M["wall"])
    # 山墙上的木条
    batch("house_gable_trim", "cube", coll, M["wood_dark"],
          [((x + W / 2 + 0.03, y, zr + 0.05), (0.1, D, 0.12), (0, 0, 0)),
           ((x + W / 2 + 0.03, y, zr + rh * 0.45), (0.1, 0.12, rh * 0.85), (0, 0, 0))])
    # 圆形小窗（山墙）
    shape("house_gable_win", "cyl", coll, M["window"], loc=(x + W / 2 + 0.06, y, zr + 0.75), scale=(0.28, 0.28, 0.06),
          rot=(0, math.pi / 2, 0), seg=12)

    # 屋顶：两坡，每坡若干排瓦片（错位），加屋脊
    ang = math.atan2(rh, D / 2 + ov)
    slope_len = math.hypot(rh, D / 2 + ov)
    rows = 7
    tiles_a, tiles_b = [], []
    for side in (-1, 1):
        for r in range(rows):
            t = (r + 0.5) / rows
            py = y + side * (D / 2 + ov) * (1 - t)
            pz = zr - 0.1 + rh * t
            cols = 9
            span = W + 2 * ov
            step = span / cols
            left = x - W / 2 - ov
            centers = [left + step * (c + 0.5) for c in range(cols)] if r % 2 == 0 else \
                      [left + step * 0.25] + [left + step * c for c in range(1, cols)] + [left + span - step * 0.25]
            for c, px in enumerate(centers):
                w_ = step * (0.5 if (r % 2 and (c == 0 or c == len(centers) - 1)) else 1.02)
                item = ((px, py, pz + 0.05), (w_, slope_len / rows * 1.25, 0.1),
                        (side * -ang, 0, 0))
                (tiles_b if (r * 7 + c * 3) % 5 == 0 else tiles_a).append(item)
    batch("house_roof_tiles", "cube", coll, M["roof"], tiles_a)
    batch("house_roof_tiles_dark", "cube", coll, M["roof_dark"], tiles_b)
    # 屋顶底板（防止从缝隙看到墙内）
    v = [(x - W / 2 - ov, y - D / 2 - ov, zr - 0.12), (x + W / 2 + ov, y - D / 2 - ov, zr - 0.12),
         (x + W / 2 + ov, y, zr + rh - 0.05), (x - W / 2 - ov, y, zr + rh - 0.05),
         (x - W / 2 - ov, y + D / 2 + ov, zr - 0.12), (x + W / 2 + ov, y + D / 2 + ov, zr - 0.12)]
    under = from_pydata("house_roof_base", v, [(0, 1, 2, 3), (3, 2, 5, 4)], coll, M["roof_dark"])
    under.modifiers.new("厚度", "SOLIDIFY").thickness = 0.12
    shape("house_ridge", "cyl", coll, M["roof_dark"], loc=(x, y, zr + rh + 0.05), scale=(0.16, 0.16, W + 2 * ov + 0.1),
          rot=(0, math.pi / 2, 0), seg=8)
    # 屋檐封檐板
    batch("house_fascia", "cube", coll, M["wood_dark"],
          [((x + sx * (W / 2 + ov), y + sy * (D / 4 + ov / 2), zr + rh / 2 - 0.05), (0.12, slope_len, 0.16), (sy * -ang, 0, 0))
           for sx in (-1, 1) for sy in (-1, 1)])

    # 烟囱 + 炊烟
    cxh, cyh = x + W * 0.28, y + 0.7
    stones = []
    for lvl in range(6):
        stones.append(((cxh, cyh, zr + 0.6 + lvl * 0.3), (0.62, 0.62, 0.32), (0, 0, random.uniform(-0.05, 0.05))))
    batch("house_chimney", "cube", coll, M["stone"], stones, jitter=0.03)
    shape("house_chimney_cap", "cube", coll, M["rock_dark"], loc=(cxh, cyh, zr + 2.4), scale=(0.75, 0.75, 0.1))
    smoke("house_smoke", coll, M, cxh + 0.1, cyh + 0.1, zr + 2.8)

    # 门（正面朝 -Y）
    dx = x + 1.05
    shape("house_door", "cube", coll, M["wood"], loc=(dx, y - D / 2 - 0.04, zb + 0.98), scale=(0.95, 0.06, 1.95))
    batch("house_door_planks", "cube", coll, M["wood_dark"],
          [((dx + k * 0.24, y - D / 2 - 0.08, zb + 0.98), (0.03, 0.03, 1.9), (0, 0, 0)) for k in (-1, 0, 1)] +
          [((dx, y - D / 2 - 0.06, zb + 2.0), (1.15, 0.1, 0.14), (0, 0, 0))])
    shape("house_door_knob", "sphere", coll, M["metal"], loc=(dx + 0.32, y - D / 2 - 0.12, zb + 0.95), scale=(0.05, 0.05, 0.05))
    shape("house_door_window", "cube", coll, M["window"], loc=(dx, y - D / 2 - 0.08, zb + 1.55), scale=(0.4, 0.03, 0.35))

    # 窗户：玻璃（夜间发光）+ 窗框 + 十字窗棂 + 窗台 + 花箱
    def window(nm, cx_, cy_, cz, face):
        if face == "front":
            off = (0, -1)
            gsz, fsz_h, fsz_v = (0.8, 0.05, 0.9), (0.95, 0.1, 0.1), (0.1, 0.1, 1.05)
        else:
            off = (1, 0)
            gsz, fsz_h, fsz_v = (0.05, 0.8, 0.9), (0.1, 0.95, 0.1), (0.1, 0.1, 1.05)
        ox, oy = off
        shape(nm + "_glass", "cube", coll, M["window"], loc=(cx_ + ox * 0.03, cy_ + oy * 0.03, cz), scale=gsz)
        fr = []
        for dz in (-0.48, 0.48):
            fr.append(((cx_ + ox * 0.07, cy_ + oy * 0.07, cz + dz), fsz_h, (0, 0, 0)))
        for dd in (-0.45, 0.45):
            fr.append(((cx_ + ox * 0.07 + (0 if face == "front" else 0), cy_ + oy * 0.07 + (dd if face != "front" else 0),
                        cz) if face != "front" else ((cx_ + dd, cy_ + oy * 0.07, cz)), fsz_v, (0, 0, 0)))
        # 十字窗棂
        fr.append(((cx_ + ox * 0.07, cy_ + oy * 0.07, cz), (fsz_h[0] * 0.9, fsz_h[1], 0.05), (0, 0, 0)))
        fr.append(((cx_ + ox * 0.07, cy_ + oy * 0.07, cz), (0.05 if face == "front" else 0.1, 0.1 if face == "front" else 0.05, 0.9), (0, 0, 0)))
        batch(nm + "_frame", "cube", coll, M["wood_dark"], fr)
        # 花箱
        bx, by = cx_ + ox * 0.22, cy_ + oy * 0.22
        shape(nm + "_box", "cube", coll, M["wood"], loc=(bx, by, cz - 0.62), scale=(0.95 if face == "front" else 0.28, 0.28 if face == "front" else 0.95, 0.2))
        fl = []
        for k in range(7):
            t = (k / 6 - 0.5) * 0.8
            fl.append(((bx + (t if face == "front" else 0), by + (0 if face == "front" else t), cz - 0.47 + random.uniform(0, 0.06)),
                       (0.09, 0.09, 0.08), (0, 0, 0)))
        batch(nm + "_fl_a", "ico", coll, M["pink"], fl[::2], sub=1)
        batch(nm + "_fl_b", "ico", coll, M["white"], fl[1::2], sub=1)
        # 窗外暖光
        point_light(LC, nm + "_light", (cx_ + ox * 0.7, cy_ + oy * 0.7, cz - 0.2), (1.0, 0.70, 0.40), WINDOW_POWER, radius=0.4)

    window("house_win_f1", x - 1.25, y - D / 2 - 0.02, zb + 1.3, "front")
    window("house_win_f2", x - 0.1, y - D / 2 - 0.02, zb + 1.3, "front")
    window("house_win_s1", x + W / 2 + 0.02, y - 0.85, zb + 1.3, "side")
    window("house_win_s2", x + W / 2 + 0.02, y + 0.85, zb + 1.3, "side")

    # 门廊：木地板（逐块）+ 立柱 + 门廊雨棚 + 栏杆 + 台阶
    py0 = y - D / 2 - 0.95
    planks = []
    for k in range(10):
        planks.append(((x - W / 2 + 0.3 + k * 0.5, py0, z + 0.26), (0.47, 1.7, 0.12), (0, 0, 0)))
    batch("house_porch_planks", "cube", coll, M["wood_light"], planks)
    porch = shape("house_porch", "cube", coll, M["wood"], loc=(x + 0.3, py0, z + 0.14), scale=(W + 1.2, 1.7, 0.18))
    WALKABLE.add(porch.name)
    WALKABLE.add("house_porch_planks")
    fence("house_rail", coll, M, (x - W / 2 - 0.25, py0 - 0.75), (x + 0.45, py0 - 0.75), z + 0.32, n=4, h=0.65)
    for k in range(3):
        st = shape(f"house_step{k}", "cube", coll, M["wood_light"], loc=(x + 1.65, py0 - 1.0 - k * 0.32, z + 0.18 - k * 0.07),
                   scale=(1.2, 0.34, 0.1))
        WALKABLE.add(st.name)
    # 门廊吊灯
    hy = y - D / 2 - 0.35
    shape("house_hang_chain", "cyl", coll, M["metal"], loc=(x + 1.9, hy, zr - 0.25), scale=(0.015, 0.015, 0.4), seg=4)
    shape("house_hang_lamp", "cube", coll, M["lantern"], loc=(x + 1.9, hy, zr - 0.55), scale=(0.2, 0.2, 0.26))
    shape("house_hang_cap", "cone", coll, M["roof_dark"], loc=(x + 1.9, hy, zr - 0.36), scale=(0.2, 0.2, 0.12), seg=4,
          rot=(0, 0, math.pi / 4))
    point_light(LC, "house_hang_light", (x + 1.9, hy - 0.2, zr - 0.65), (1.0, 0.72, 0.42), LANTERN_POWER)
    # 门廊上的小物：花盆、柴堆、猫
    potted_plant("house_pot1", coll, M, x - W / 2 + 0.1, py0 + 0.4, z + 0.32, "pink")
    potted_plant("house_pot2", coll, M, x + 0.4, py0 + 0.45, z + 0.32, "yellow")
    logs = [((x - W / 2 - 0.55, y + 0.4 + k * 0.0, z + 0.25 + (k // 3) * 0.24), (0.11, 0.11, 0.9),
             (0, math.pi / 2, 0)) for k in range(5)]
    for i, l in enumerate(logs):
        logs[i] = ((l[0][0], l[0][1] - 0.6 + (i % 3) * 0.24 + (0.12 if i >= 3 else 0), l[0][2]), l[1], (math.pi / 2, 0, 0))
    batch("house_logs", "cyl", coll, M["wood"], logs, seg=7)
    cat("house_cat", coll, M, x - 1.6, py0 + 0.2, z + 0.32, rz=0.4)
    # 墙角藤蔓
    ivy = []
    for k in range(10):
        ivy.append(((x - W / 2 - 0.05 + random.uniform(-0.1, 0.1), y - D / 2 - 0.05 + random.uniform(-0.1, 0.1),
                     zb + k * 0.24), (0.2, 0.2, 0.18), (0, 0, 0)))
    for k in range(6):
        ivy.append(((x - W / 2 - ov + 0.3 + k * 0.35, y - D / 2 - ov + 0.05, zr - 0.05), (0.2, 0.18, 0.16), (0, 0, 0)))
    batch("house_ivy", "ico", coll, M["leaf"], ivy, sub=1, jitter=0.06)
    batch("house_ivy_fl", "ico", coll, M["white"],
          [((p[0][0] + 0.08, p[0][1] - 0.1, p[0][2] + 0.05), (0.05, 0.05, 0.05), (0, 0, 0)) for p in ivy[::2]])


def build_dock(coll, LC, M, x, y, z):
    planks = [((x - 2.0 + k * 0.42, y, z), (0.39, 2.0, 0.1), (0, 0, random.uniform(-0.01, 0.01))) for k in range(10)]
    batch("dock_planks", "cube", coll, M["wood_light"], planks)
    WALKABLE.add("dock_planks")
    shape("dock_frame", "cube", coll, M["wood"], loc=(x, y, z - 0.1), scale=(4.3, 2.0, 0.1))
    posts = [((x - 2.0 + i, y + sy * 0.95, z - 0.25), (0.09, 0.09, 1.1), (0, 0, 0)) for i in range(5) for sy in (-1, 1)]
    batch("dock_posts", "cyl", coll, M["wood_dark"], posts, seg=7)
    # 缆绳卷
    shape("dock_rope", "cyl", coll, M["rope"], loc=(x - 1.4, y + 0.6, z + 0.1), scale=(0.2, 0.2, 0.1), seg=10)
    lantern("dock_lamp", coll, LC, M, x + 1.8, y + 0.85, z + 0.05)
    # 小船：船体 + 内舱 + 座板 + 桨
    bx, by, br = x - 1.0, y - 2.3, 0.15
    shape("boat_hull", "sphere", coll, M["boat"], loc=(bx, by, 0.1), scale=(1.55, 0.58, 0.32), rot=(0, 0, br))
    shape("boat_rim", "sphere", coll, M["wood_dark"], loc=(bx, by, 0.2), scale=(1.5, 0.55, 0.12), rot=(0, 0, br))
    shape("boat_inner", "sphere", coll, M["wood"], loc=(bx, by, 0.21), scale=(1.32, 0.44, 0.1), rot=(0, 0, br))
    batch("boat_seats", "cube", coll, M["wood_light"],
          [((bx + k * math.cos(br) * 0.5, by + k * math.sin(br) * 0.5, 0.3), (0.18, 0.86, 0.05), (0, 0, br)) for k in (-1, 1)])
    shape("boat_oar", "cube", coll, M["wood_light"], loc=(bx + 0.2, by + 0.25, 0.34), scale=(1.4, 0.06, 0.04), rot=(0, 0.1, br + 0.3))
    # 船边水纹
    shape("boat_ripple", "cyl", coll, M["foam"], loc=(bx, by, 0.02), scale=(1.9, 0.85, 0.01), rot=(0, 0, br), seg=20)


def build_bridge(coll, LC, M, a, b, z):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ln = math.hypot(b[0] - a[0], b[1] - a[1])
    n = 11
    planks = []
    for i in range(n):
        t = (i + 0.5) / n
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        hz = z + 0.5 * math.sin(math.pi * t)
        tilt = math.atan(0.5 * math.pi / ln * math.cos(math.pi * t))
        planks.append(((px, py, hz), (ln / n * 0.9, 1.35, 0.09), (0, -tilt, ang)))
    batch("bridge_planks", "cube", coll, M["wood_light"], planks)
    WALKABLE.add("bridge_planks")
    posts, rails = [], []
    for side in (-1, 1):
        ox, oy = -math.sin(ang) * 0.68 * side, math.cos(ang) * 0.68 * side
        prev = None
        for i in range(5):
            t = i / 4
            px, py = a[0] + (b[0] - a[0]) * t + ox, a[1] + (b[1] - a[1]) * t + oy
            hz = z + 0.5 * math.sin(math.pi * t)
            posts.append(((px, py, hz + 0.35), (0.1, 0.1, 0.75), (0, 0, 0)))
            top = Vector((px, py, hz + 0.72))
            if prev is not None:
                mid = (prev + top) / 2
                d = top - prev
                rails.append(((mid.x, mid.y, mid.z), (d.length, 0.07, 0.07), (0, -math.atan2(d.z, math.hypot(d.x, d.y)), ang)))
            prev = top
    batch("bridge_posts", "cube", coll, M["wood_dark"], posts)
    batch("bridge_rails", "cube", coll, M["wood"], rails)
    lantern("bridge_lamp", coll, LC, M, b[0] + 0.5, b[1] - 0.9, z)


def build_desk_area(coll, LC, M, x, y, z):
    # 书桌
    shape("desk_top", "cube", coll, M["wood_light"], loc=(x, y, z + 0.76), scale=(1.9, 0.95, 0.08))
    batch("desk_legs", "cube", coll, M["wood"],
          [((x + sx * 0.85, y + sy * 0.38, z + 0.37), (0.09, 0.09, 0.74), (0, 0, 0)) for sx in (-1, 1) for sy in (-1, 1)])
    # 电脑
    shape("desk_laptop", "cube", coll, M["laptop"], loc=(x - 0.25, y - 0.05, z + 0.815), scale=(0.56, 0.38, 0.03))
    shape("desk_lid", "cube", coll, M["laptop"], loc=(x - 0.25, y + 0.15, z + 1.0), scale=(0.56, 0.03, 0.38), rot=(math.radians(-14), 0, 0))
    shape("desk_screen", "cube", coll, M["laptop_screen"], loc=(x - 0.25, y + 0.13, z + 1.0), scale=(0.5, 0.02, 0.32),
          rot=(math.radians(-14), 0, 0))
    # 书堆
    books = [("book_red", 0.85), ("book_blue", 0.9), ("book_green", 0.95)]
    for k, (mat, _) in enumerate(books):
        shape(f"desk_book{k}", "cube", coll, M[mat], loc=(x + 0.6, y + 0.12, z + 0.85 + k * 0.07),
              scale=(0.36 - k * 0.03, 0.26, 0.06), rot=(0, 0, k * 0.15))
    shape("desk_notebook", "cube", coll, M["white"], loc=(x + 0.35, y - 0.25, z + 0.81), scale=(0.3, 0.22, 0.02), rot=(0, 0, -0.3))
    shape("desk_mug", "cyl", coll, M["mug"], loc=(x - 0.75, y + 0.2, z + 0.86), scale=(0.07, 0.07, 0.13), seg=10)
    # 台灯
    shape("desk_lamp_base", "cyl", coll, M["metal"], loc=(x + 0.78, y - 0.28, z + 0.82), scale=(0.09, 0.09, 0.03), seg=8)
    shape("desk_lamp_arm", "cyl", coll, M["metal"], loc=(x + 0.78, y - 0.28, z + 1.0), scale=(0.015, 0.015, 0.36), seg=4)
    shape("desk_lamp_shade", "cone", coll, M["lantern"], loc=(x + 0.72, y - 0.3, z + 1.18), scale=(0.12, 0.12, 0.12), seg=10)
    point_light(LC, "desk_lamp_light", (x + 0.7, y - 0.32, z + 1.1), (1.0, 0.78, 0.5), {"morning": 4.0, "noon": 0.0, "night": 35.0})
    # 椅子
    shape("chair_seat", "cube", coll, M["wood_light"], loc=(x, y - 0.9, z + 0.45), scale=(0.5, 0.45, 0.06))
    shape("chair_back", "cube", coll, M["wood_light"], loc=(x, y - 1.12, z + 0.75), scale=(0.5, 0.06, 0.55))
    batch("chair_legs", "cube", coll, M["wood"],
          [((x + sx * 0.2, y - 0.9 + sy * 0.18, z + 0.22), (0.05, 0.05, 0.44), (0, 0, 0)) for sx in (-1, 1) for sy in (-1, 1)])
    # 长椅（带靠背）
    bx, by = x - 1.9, y - 1.5
    shape("bench_seat", "cube", coll, M["wood_light"], loc=(bx, by, z + 0.44), scale=(1.8, 0.48, 0.08), rot=(0, 0, 0.35))
    shape("bench_back", "cube", coll, M["wood_light"], loc=(bx - 0.08, by - 0.22, z + 0.78), scale=(1.8, 0.06, 0.4), rot=(0.15, 0, 0.35))
    batch("bench_legs", "cube", coll, M["wood"],
          [((bx + sx * 0.75 * math.cos(0.35), by + sx * 0.75 * math.sin(0.35), z + 0.21), (0.1, 0.42, 0.42), (0, 0, 0.35)) for sx in (-1, 1)])
    # 树桩、鸟屋、草帽
    shape("stump", "cyl", coll, M["trunk"], loc=(x + 1.55, y + 0.25, z + 0.24), scale=(0.3, 0.3, 0.48), seg=9, jitter=0.02)
    shape("stump_top", "cyl", coll, M["wood_light"], loc=(x + 1.55, y + 0.25, z + 0.49), scale=(0.27, 0.27, 0.02), seg=9)
    shape("birdhouse_post", "cube", coll, M["wood"], loc=(x + 2.3, y + 1.0, z + 0.85), scale=(0.08, 0.08, 1.7))
    shape("birdhouse", "cube", coll, M["wood_light"], loc=(x + 2.3, y + 1.0, z + 1.8), scale=(0.36, 0.36, 0.4))
    shape("birdhouse_roof", "cone", coll, M["red"], loc=(x + 2.3, y + 1.0, z + 2.1), scale=(0.33, 0.33, 0.22), seg=4,
          rot=(0, 0, math.pi / 4))
    shape("birdhouse_hole", "cyl", coll, M["black"], loc=(x + 2.3, y + 0.81, z + 1.85), scale=(0.07, 0.07, 0.02),
          rot=(math.pi / 2, 0, 0), seg=8)
    potted_plant("desk_pot", coll, M, x - 1.0, y + 0.6, z, "purple")


def build_cherry(coll, M, x, y, z):
    # 弯曲的树干：分段圆柱
    segs = [((0, 0, 0), (0.1, 0.05, 0.9)), ((0.1, 0.05, 0.9), (-0.05, 0.15, 1.8)), ((-0.05, 0.15, 1.8), (0.05, 0.0, 2.4))]
    for i, (p0, p1) in enumerate(segs):
        a, b = Vector(p0), Vector(p1)
        d = b - a
        mid = (a + b) / 2
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_euler()
        r = 0.3 - i * 0.06
        shape(f"sakura_trunk{i}", "cyl", coll, M["trunk"], loc=(x + mid.x, y + mid.y, z + mid.z),
              scale=(r, r, d.length + 0.1), rot=rot, seg=8, top=0.8, jitter=0.02)
    branches = []
    for i, (dx, dy, dz) in enumerate(((1.1, 0.3, 0.8), (-1.0, 0.4, 0.9), (0.2, -1.0, 0.7), (0.4, 0.9, 1.0), (-0.6, -0.6, 0.8))):
        d = Vector((dx, dy, dz))
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_euler()
        mid = Vector((x, y, z + 2.1)) + d / 2
        branches.append(((mid.x, mid.y, mid.z), (0.09, 0.09, d.length), tuple(rot)))
    batch("sakura_branches", "cyl", coll, M["trunk"], branches, seg=6, top=0.5)
    # 花团：三种粉色，下深上浅
    groups = {"sakura2": [], "sakura": [], "sakura3": []}
    for i in range(14):
        a = 2 * math.pi * i / 14 + random.uniform(-0.2, 0.2)
        d = random.uniform(0.6, 1.7) if i else 0
        zz = z + 2.9 + random.uniform(-0.5, 0.6)
        s = random.uniform(0.8, 1.15)
        key = "sakura2" if zz < z + 2.8 else ("sakura" if i % 2 else "sakura3")
        groups[key].append(((x + d * math.cos(a), y + d * math.sin(a), zz), (s, s, s * 0.8), (0, 0, 0)))
    groups["sakura3"].append(((x - 0.3, y - 0.3, z + 3.8), (0.9, 0.9, 0.7), (0, 0, 0)))
    for key, items in groups.items():
        batch(f"sakura_bloom_{key}", "ico", coll, M[key], items, sub=2, jitter=0.1)
    # 地面落花 + 空中飘落的花瓣
    ground = [((x + random.uniform(-2.8, 2.8), y + random.uniform(-2.6, 2.2), z + 0.02), (0.1, 0.07, 0.01), (0, 0, random.uniform(0, 3)))
              for _ in range(60)]
    batch("sakura_petals_ground", "cyl", coll, M["sakura"], ground, seg=5)
    air = [((x + random.uniform(-3, 3), y + random.uniform(-3, 2), z + random.uniform(0.6, 3.0)), (0.08, 0.05, 0.01),
            (random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3))) for _ in range(25)]
    batch("sakura_petals_air", "cyl", coll, M["sakura3"], air, seg=5)


def build_stream(coll_bg, coll_fg, M, z):
    theta_end = math.atan2(-5.3 / ISLAND_RY, 6.4 / ISLAND_RX)
    ex, ey = island_edge(theta_end)
    pts = [(6.5, 9.5), (5.6, 6.0), (4.9, 3.0), (5.0, 0.8), (5.6, -1.8), (ex * 0.93, ey * 0.93), (ex, ey)]
    # 河床（深一点）+ 水面 + 中线高光
    ribbon("stream_bed", pts, 1.9, z + 0.01, coll_bg, M["dirt"], steps=10, wobble=0.1)
    ob, curve, normals = ribbon("stream", pts, 1.5, z + 0.03, coll_bg, M["stream"], steps=10)
    ribbon("stream_highlight", pts[1:-1], 0.25, z + 0.04, coll_bg, M["foam"], steps=10, wobble=0.6)
    # 岸边石头（大小交错，带青苔）
    rocks, mossy = [], []
    for i in range(0, len(curve) - 2, 2):
        x, y = curve[i]
        nx, ny = normals[i]
        for side in (-1, 1):
            s = random.uniform(0.2, 0.48)
            item = ((x + nx * side * (0.95 + random.uniform(-0.1, 0.15)), y + ny * side * (0.95 + random.uniform(-0.1, 0.15)),
                     z + s * 0.35), (s, s * 0.9, s * 0.65), (0, 0, random.uniform(0, 3)))
            (mossy if random.random() < 0.25 else rocks).append(item)
    batch("stream_rocks", "ico", coll_bg, M["rock"], rocks[::2], sub=1, jitter=0.12)
    batch("stream_rocks_b", "ico", coll_bg, M["rock_dark"], rocks[1::2], sub=1, jitter=0.12)
    batch("stream_rocks_moss", "ico", coll_bg, M["moss"], mossy, sub=1, jitter=0.12)
    # 溪中踏石
    batch("stream_stepping", "cyl", coll_bg, M["rock_warm"],
          [((curve[k][0] + random.uniform(-0.3, 0.3), curve[k][1] + random.uniform(-0.3, 0.3), z + 0.05), (0.25, 0.22, 0.08), (0, 0, 0))
           for k in (8, 11, 14)], seg=7, jitter=0.03)
    # 瀑布：两级水帘 + 水雾 + 两侧岩石
    ux, uy = ex / math.hypot(ex, ey), ey / math.hypot(ex, ey)
    px, py = -uy, ux
    w = 0.75
    tiers = [(0.0, z + 0.03, 0.3, z * 0.55), (0.3, z * 0.55, 0.65, 0.02)]
    for k, (d0, z0, d1, z1) in enumerate(tiers):
        v = [(ex + ux * d0 + px * w, ey + uy * d0 + py * w, z0), (ex + ux * d0 - px * w, ey + uy * d0 - py * w, z0),
             (ex + ux * d1 - px * w, ey + uy * d1 - py * w, z1), (ex + ux * d1 + px * w, ey + uy * d1 + py * w, z1)]
        from_pydata(f"waterfall{k}", v, [(0, 1, 2, 3)], coll_fg, M["stream"])
        # 水帘上的白色条纹
        stripes = []
        for j in range(5):
            t = (j + 0.5) / 5 * 2 - 1
            sx_, sy_ = px * w * t * 0.9, py * w * t * 0.9
            mid = ((ex + ux * (d0 + d1) / 2 + sx_), (ey + uy * (d0 + d1) / 2 + sy_), (z0 + z1) / 2 + 0.02)
            stripes.append((mid, (0.05, 0.05, math.hypot(d1 - d0, z0 - z1) * 0.45), (0, 0, 0)))
        batch(f"waterfall_stripes{k}", "cube", coll_fg, M["foam"], stripes)
    mist = [((ex + ux * random.uniform(0.6, 1.4) + px * random.uniform(-1.0, 1.0),
              ey + uy * random.uniform(0.6, 1.4) + py * random.uniform(-1.0, 1.0), random.uniform(0.02, 0.25)),
             (random.uniform(0.2, 0.42),) * 2 + (0.15,), (0, 0, 0)) for _ in range(9)]
    batch("waterfall_mist", "ico", coll_fg, M["foam"], mist, sub=1, jitter=0.1)
    big = [((ex + px * 1.3 * side + ux * 0.2, ey + py * 1.3 * side + uy * 0.2, z * 0.4), (0.85, 0.8, 0.75), (0, 0, side))
           for side in (-1, 1)]
    batch("waterfall_rocks", "ico", coll_fg, M["rock_dark"], big, sub=1, jitter=0.15)
    return curve


def build_garden(coll, M, x, y, z):
    """右侧菜园：两条土垄 + 作物 + 围栏 + 水壶"""
    for r in range(2):
        shape(f"garden_bed{r}", "cube", coll, M["soil"], loc=(x + 0.9, y + 0.55 + r * 0.9, z + 0.08), scale=(1.9, 0.6, 0.16))
        crops = [((x + 0.15 + c * 0.38, y + 0.55 + r * 0.9, z + 0.28), (0.17, 0.17, 0.17), (0, 0, 0)) for c in range(5)]
        batch(f"garden_crop{r}", "ico", coll, M["leaf2" if r else "leaf3"], crops, sub=1, jitter=0.04)
    batch("garden_carrot", "cone", coll, M["orange"],
          [((x + 0.34 + c * 0.38, y + 0.55, z + 0.18), (0.04, 0.04, 0.12), (math.pi, 0, 0)) for c in range(4)], seg=5)
    fence("garden_fence_a", coll, M, (x - 0.3, y), (x + 2.2, y - 0.3), z, n=5, h=0.6)
    fence("garden_fence_b", coll, M, (x + 2.2, y - 0.3), (x + 2.4, y + 2.2), z, n=5, h=0.6)
    shape("garden_can", "cyl", coll, M["blue"], loc=(x - 0.4, y + 1.0, z + 0.15), scale=(0.13, 0.13, 0.28), seg=8)
    shape("garden_can_spout", "cyl", coll, M["blue"], loc=(x - 0.25, y + 1.0, z + 0.25), scale=(0.025, 0.025, 0.25),
          rot=(0, 0.9, 0), seg=5)


def build_character(coll, M, x, y, z):
    """Q 版人物占位：大头、齐刘海短发、叶子发夹、浅色上衣、绿裙子，正面朝 -Y"""
    root = bpy.data.objects.new("CHAR_root", None)
    root.empty_display_type = "ARROWS"
    root.location = (x, y, z)
    coll.objects.link(root)
    h = CHAR_HEIGHT
    parts = [
        ("CHAR_shoeL", "sphere", "shoe", (-0.06 * h, -0.02 * h, 0.03 * h), (0.05 * h, 0.07 * h, 0.035 * h), (0, 0, 0)),
        ("CHAR_shoeR", "sphere", "shoe", (0.06 * h, -0.02 * h, 0.03 * h), (0.05 * h, 0.07 * h, 0.035 * h), (0, 0, 0)),
        ("CHAR_legL", "cyl", "skin", (-0.055 * h, 0, 0.15 * h), (0.035 * h, 0.035 * h, 0.22 * h), (0, 0, 0)),
        ("CHAR_legR", "cyl", "skin", (0.055 * h, 0, 0.15 * h), (0.035 * h, 0.035 * h, 0.22 * h), (0, 0, 0)),
        ("CHAR_skirt", "cone", "skirt", (0, 0, 0.36 * h), (0.2 * h, 0.17 * h, 0.24 * h), (0, 0, 0)),
        ("CHAR_body", "cyl", "shirt", (0, 0, 0.5 * h), (0.13 * h, 0.1 * h, 0.2 * h), (0, 0, 0)),
        ("CHAR_armL", "cyl", "shirt", (-0.16 * h, 0, 0.47 * h), (0.035 * h, 0.035 * h, 0.2 * h), (0, 0.25, 0)),
        ("CHAR_armR", "cyl", "shirt", (0.16 * h, 0, 0.47 * h), (0.035 * h, 0.035 * h, 0.2 * h), (0, -0.25, 0)),
        ("CHAR_handL", "sphere", "skin", (-0.185 * h, 0, 0.36 * h), (0.035 * h,) * 3, (0, 0, 0)),
        ("CHAR_handR", "sphere", "skin", (0.185 * h, 0, 0.36 * h), (0.035 * h,) * 3, (0, 0, 0)),
        ("CHAR_neck", "cyl", "skin", (0, 0, 0.61 * h), (0.04 * h, 0.04 * h, 0.04 * h), (0, 0, 0)),
        ("CHAR_head", "sphere", "skin", (0, 0, 0.8 * h), (0.2 * h, 0.19 * h, 0.2 * h), (0, 0, 0)),
        ("CHAR_hair", "sphere", "hair", (0, 0.035 * h, 0.84 * h), (0.225 * h, 0.22 * h, 0.21 * h), (0, 0, 0)),
        ("CHAR_bangs", "sphere", "hair", (0, -0.1 * h, 0.9 * h), (0.19 * h, 0.08 * h, 0.08 * h), (0.2, 0, 0)),
        ("CHAR_hairL", "sphere", "hair", (-0.17 * h, -0.02 * h, 0.7 * h), (0.07 * h, 0.08 * h, 0.14 * h), (0, 0, 0)),
        ("CHAR_hairR", "sphere", "hair", (0.17 * h, -0.02 * h, 0.7 * h), (0.07 * h, 0.08 * h, 0.14 * h), (0, 0, 0)),
        ("CHAR_eyeL", "sphere", "eye", (-0.075 * h, -0.175 * h, 0.78 * h), (0.025 * h, 0.012 * h, 0.035 * h), (0, 0, 0)),
        ("CHAR_eyeR", "sphere", "eye", (0.075 * h, -0.175 * h, 0.78 * h), (0.025 * h, 0.012 * h, 0.035 * h), (0, 0, 0)),
        ("CHAR_blushL", "sphere", "pink", (-0.11 * h, -0.16 * h, 0.735 * h), (0.025 * h, 0.01 * h, 0.015 * h), (0, 0, 0)),
        ("CHAR_blushR", "sphere", "pink", (0.11 * h, -0.16 * h, 0.735 * h), (0.025 * h, 0.01 * h, 0.015 * h), (0, 0, 0)),
        ("CHAR_clip", "sphere", "leaf_clip", (0.14 * h, -0.08 * h, 0.95 * h), (0.05 * h, 0.02 * h, 0.03 * h), (0, 0.5, 0.3)),
    ]
    for name, kind, mat, loc, sc, rot in parts:
        ob = shape(name, kind, coll, M[mat], loc=loc, scale=sc, rot=rot, seg=10)
        ob.parent = root
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.5)
    catcher = make_mesh_object("CHAR_shadow_catcher", bm, coll, M["white"], loc=(x, y, z + 0.005))
    catcher.is_shadow_catcher = True
    catcher.hide_render = True
    catcher.hide_viewport = True
    return root


# ============================================================
# 搭建整个场景
# ============================================================

def build_world_scene(M):
    BG = new_collection("BG_背景")
    FG = new_collection("FG_前景遮挡")
    CH = new_collection("CHAR_人物")
    LC = new_collection("LIGHTS_灯光")
    WATER = new_collection("BG_水面", BG)
    ISL = new_collection("BG_岛屿", BG)
    PROPS = new_collection("BG_建筑道具", BG)
    PLANTS = new_collection("BG_植物", BG)
    FX = new_collection("BG_氛围", BG)
    FAR = new_collection("BG_远景", BG)
    z = ISLAND_TOP

    # ---------- 水面 ----------
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=120)
    make_mesh_object("sea", bm, WATER, M["sea"], loc=(0, 20, 0))
    ring = [island_edge(2 * math.pi * i / 96) for i in range(96)]
    ring_band("shallow_water", ring, 1.0, 1.28, 0.008, WATER, M["shallow"])
    ring_band("shore_foam", ring, 1.0, 1.07, 0.016, WATER, M["foam"])
    ring_band("shore_foam_outer", ring, 1.13, 1.15, 0.016, WATER, M["foam"])
    # 水面闪点：集中在左上（迎着太阳）的一条光带 + 零散
    sparkles = []
    for _ in range(70):
        if random.random() < 0.6:
            t = random.uniform(0, 1)
            sx_, sy_ = -11 - t * 10 + random.uniform(-2.5, 2.5), 4 + t * 12 + random.uniform(-2.5, 2.5)
        else:
            a = random.uniform(0, 2 * math.pi)
            k = random.uniform(1.25, 1.9)
            sx_, sy_ = island_edge(a, k)
        if inside_island(sx_, sy_, 1.2):
            continue
        L = random.uniform(0.15, 0.45)
        sparkles.append(((sx_, sy_, 0.02), (L, L * 0.18, 0.01), (0, 0, math.radians(CAM_AZIMUTH))))
    batch("sea_sparkles", "cube", FX, M["sparkle"], sparkles)
    # 睡莲（带花）
    lilies, lily_fl = [], []
    for i in range(40):
        a = random.uniform(0, 2 * math.pi)
        x_, y_ = island_edge(a, random.uniform(1.12, 1.35))
        s = random.uniform(0.22, 0.38)
        lilies.append(((x_, y_, 0.02), (s, s, 0.015), (0, 0, random.uniform(0, 3))))
        if random.random() < 0.2:
            lily_fl.append(((x_, y_, 0.08), (0.08, 0.08, 0.06), (0, 0, 0)))
    batch("lilies", "cyl", WATER, M["lily"], lilies, seg=9)
    batch("lily_flowers", "ico", WATER, M["pink"], lily_fl, sub=1)

    # ---------- 主岛 ----------
    top, side, ring = blob_island("island_top", "island_cliff", 0, 0, ISLAND_RX, ISLAND_RY, z, -1.0,
                                  ISL, M["grass"], M["cliff"], n=96, radius_fn=island_radius)
    WALKABLE.add(top.name)
    # 草地明暗斑块（地面不那么平）
    patches_l, patches_d = [], []
    for (x_, y_) in scatter_on_island(26, [], 0.8):
        s = random.uniform(0.8, 1.8)
        item = ((x_, y_, z - 0.04), (s, s * random.uniform(0.6, 1.0), 0.1), (0, 0, random.uniform(0, 3)))
        (patches_l if random.random() < 0.6 else patches_d).append(item)
    batch("grass_patches_light", "cyl", ISL, M["grass_light"], patches_l, seg=10, jitter=0.15)
    batch("grass_patches_dark", "cyl", ISL, M["grass_dark"], patches_d, seg=10, jitter=0.15)
    # 岸边石头一圈
    shore_a, shore_b, shore_m = [], [], []
    for i, (x_, y_) in enumerate(ring):
        if random.random() < 0.85:
            s = random.uniform(0.35, 0.85)
            item = ((x_ * 1.03, y_ * 1.03, random.uniform(-0.05, 0.25)), (s, s * random.uniform(0.8, 1.2), s * 0.7),
                    (0, 0, random.uniform(0, 3)))
            r_ = random.random()
            (shore_m if r_ < 0.15 else (shore_a if r_ < 0.6 else shore_b)).append(item)
    batch("shore_rocks_a", "ico", ISL, M["rock"], shore_a, sub=1, jitter=0.12)
    batch("shore_rocks_b", "ico", ISL, M["rock_dark"], shore_b, sub=1, jitter=0.12)
    batch("shore_rocks_moss", "ico", ISL, M["moss"], shore_m, sub=1, jitter=0.12)
    # 芦苇
    for i, a in enumerate((2.6, 3.4, 4.1, 5.2, 0.4, 1.9)):
        rx_, ry_ = island_edge(a, 1.08)
        reeds(f"reeds{i}", PLANTS, M, rx_, ry_, n=9)

    # ---------- 木屋、码头 ----------
    build_house(PROPS, LC, M, -4.6, 3.2, z)
    build_dock(PROPS, LC, M, -11.6, 1.6, 0.4)

    # ---------- 土路（带路边碎石）----------
    paths = {
        "path_main": ([(-3.0, -0.6), (-2.4, -1.9), (-1.2, -3.0), (0.2, -3.9), (1.2, -4.6)], 1.35),
        "path_bridge": ([(-1.2, -3.0), (0.8, -1.8), (2.6, -0.4), (3.9, 0.6)], 1.1),
        "path_back": ([(-2.2, 1.6), (-1.0, 4.2), (0.6, 6.6)], 1.0),
        "path_dock": ([(-6.5, 0.2), (-8.5, 0.9), (-9.6, 1.4)], 1.0),
        "path_right": ([(6.2, 1.4), (7.6, 2.2), (8.3, 3.4)], 0.9),
    }
    pebbles = []
    for name, (pts, w) in paths.items():
        ribbon(name + "_edge", pts, w + 0.25, z + 0.015, PROPS, M["path_edge"])
        ob, curve, normals = ribbon(name, pts, w, z + 0.025, PROPS, M["path"])
        WALKABLE.add(ob.name)
        WALKABLE.add(name + "_edge")
        for i in range(0, len(curve), 2):
            x_, y_ = curve[i]
            nx, ny = normals[i]
            for side in (-1, 1):
                if random.random() < 0.55:
                    d = (w / 2 + 0.12) * side
                    s = random.uniform(0.07, 0.14)
                    pebbles.append(((x_ + nx * d, y_ + ny * d, z + 0.04), (s, s, s * 0.6), (0, 0, 0)))
    batch("path_pebbles", "ico", PROPS, M["rock_warm"], pebbles, sub=1, jitter=0.1)
    # 码头小路上的踏石
    batch("dock_stepping", "cyl", PROPS, M["stone"],
          [((-7.2 - k * 0.7, 0.45 + k * 0.25, z + 0.04), (0.3, 0.26, 0.05), (0, 0, k)) for k in range(4)], seg=7, jitter=0.03)

    # ---------- 小溪、木桥、菜园 ----------
    build_stream(PROPS, FG, M, z)
    build_bridge(PROPS, LC, M, (4.0, 0.65), (6.1, 1.35), z)
    build_garden(PROPS, M, 7.0, 2.6, z)

    # ---------- 书桌区、樱花 ----------
    build_desk_area(PROPS, LC, M, 1.6, -5.4, z)
    build_cherry(FG, M, 2.6, -2.4, z)

    # ---------- 路灯 ----------
    for i, (x_, y_) in enumerate(((-2.0, -0.9), (-0.4, -2.4), (2.0, -4.0), (2.9, 0.1), (-1.2, 3.6), (-7.6, 0.2))):
        lantern(f"lamp{i}", PROPS, LC, M, x_, y_, z)

    # ---------- 栅栏 ----------
    fence("fence_dock", PROPS, M, (-8.2, -0.6), (-6.8, -1.8), z, n=3)
    fence("fence_front", FG, M, (-0.8, -6.6), (3.6, -7.2), z, n=6)
    fence("fence_left", PROPS, M, (-6.8, -1.8), (-6.0, -3.8), z, n=3)

    # ---------- 植物 ----------
    trees_bg = [(1.0, 7.2, "round"), (3.2, 6.0, "round"), (-1.5, 6.6, "pine"), (7.8, 6.0, "round"), (4.0, 7.8, "pine"),
                (-7.2, 6.0, "round"), (-8.6, 3.6, "pine"), (8.6, -0.8, "round"), (-0.4, 5.0, "round"), (2.2, 3.4, "round"),
                (7.0, -1.2, "round"), (-5.0, 6.6, "pine"), (5.8, 7.6, "round"), (-3.0, 7.4, "round")]
    for i, (x_, y_, k) in enumerate(trees_bg):
        tree(f"tree{i}", PLANTS, M, x_, y_, z, h=random.uniform(3.0, 4.2), r=random.uniform(1.25, 1.7), kind=k)
    tree("tree_front0", FG, M, -6.2, -4.6, z, h=3.3, r=1.45)
    tree("tree_front1", FG, M, 7.4, -4.0, z, h=2.9, r=1.25)
    for i, (x_, y_, fl) in enumerate(((-7.4, 1.6, "white"), (-2.9, 1.0, None), (0.8, 1.6, "yellow"), (3.8, -5.6, "pink"),
                                      (-4.6, -3.4, None), (8.2, 0.8, "purple"), (-8.0, -2.6, "white"), (5.4, 4.4, None))):
        bush(f"bush{i}", PLANTS, M, x_, y_, z, r=random.uniform(0.45, 0.7), flowers=fl)
    for i, (x_, y_) in enumerate(((-6.6, 0.6), (-3.2, 0.3), (-7.3, 3.6), (-1.0, -1.0), (0.3, -5.8), (-0.6, 1.8),
                                   (3.7, -3.6), (6.6, -3.2), (-4.0, -5.4), (-6.8, -3.4), (1.8, 1.2), (4.6, -1.0))):
        flower_patch(f"flower{i}", PLANTS, M, x_, y_, z, n=16)
    avoid = [(-4.6, 3.2, 3.6), (-4.3, 0.6, 2.8), (1.6, -5.4, 2.0), (5.0, 1.0, 1.6), (5.5, -2.0, 1.4), (5.6, 5.0, 1.4),
             (7.9, 3.5, 1.8)]
    grass_tufts("grass_tufts", PLANTS, M, scatter_on_island(140, avoid, 0.9), z)

    # ---------- 鸭子 ----------
    for i, (x_, y_) in enumerate(((-9.6, -5.4), (-8.8, -6.1), (-8.0, -6.8), (-10.4, -4.6))):
        shape(f"duck{i}_body", "sphere", WATER, M["white"], loc=(x_, y_, 0.12), scale=(0.28, 0.19, 0.15), rot=(0, 0, 0.6))
        shape(f"duck{i}_tail", "cone", WATER, M["white"], loc=(x_ - 0.22, y_ - 0.12, 0.22), scale=(0.08, 0.08, 0.12),
              rot=(0, -0.8, 0.6), seg=5)
        shape(f"duck{i}_head", "sphere", WATER, M["white"], loc=(x_ + 0.18, y_ + 0.12, 0.33), scale=(0.11, 0.11, 0.11))
        shape(f"duck{i}_beak", "cone", WATER, M["beak"], loc=(x_ + 0.27, y_ + 0.18, 0.32), scale=(0.04, 0.04, 0.09),
              rot=(0, math.pi / 2, 0.6), seg=5)
        shape(f"duck{i}_ripple", "cyl", WATER, M["foam"], loc=(x_, y_, 0.015), scale=(0.42, 0.3, 0.005), rot=(0, 0, 0.6), seg=14)

    # ---------- 远岛 ----------
    for i, (cx, cy, rx, ry) in enumerate(((-16.0, 11.5, 3.6, 1.7), (-6.0, 17.0, 4.0, 1.7), (6.0, 19.5, 3.2, 1.5))):
        blob_island(f"far{i}_top", f"far{i}_side", cx, cy, rx, ry, 1.2, -0.5, FAR, M["far_island"], M["cliff"], n=40)
        ring_band(f"far{i}_foam", [(cx + rx * math.cos(2 * math.pi * k / 40), cy + ry * math.sin(2 * math.pi * k / 40)) for k in range(40)],
                  1.08, 1.16, 0.016, FAR, M["foam"], cx, cy)
        for k in range(4):
            tree(f"far{i}_tree{k}", FAR, M, cx + random.uniform(-rx * 0.6, rx * 0.6), cy + random.uniform(-ry * 0.4, ry * 0.4), 1.2,
                 h=2.2, r=1.0, kind="round" if k % 2 else "pine", leaf=("far_tree", "far_island", "leaf3"))
    shape("far_hut", "cube", FAR, M["wall"], loc=(-15.0, 11.0, 1.7), scale=(1.1, 0.9, 1.0))
    shape("far_hut_roof", "cone", FAR, M["red"], loc=(-15.0, 11.0, 2.5), scale=(1.0, 0.8, 0.6), seg=4, rot=(0, 0, math.pi / 4))
    shape("far_hut_win", "cube", FAR, M["window"], loc=(-14.6, 10.54, 1.7), scale=(0.3, 0.03, 0.3))
    point_light(LC, "far_hut_light", (-14.6, 10.0, 1.7), (1.0, 0.7, 0.4), {"morning": 0.0, "noon": 0.0, "night": 40.0})

    # ---------- 萤火虫（夜晚）----------
    flies = []
    for _ in range(36):
        x_, y_ = random.choice([(4.5, 2.0), (2.6, -2.4), (-1.0, 4.5), (6.0, -1.0), (-5.5, -3.0)])
        flies.append(((x_ + random.uniform(-2, 2), y_ + random.uniform(-2, 2), z + random.uniform(0.5, 2.6)),
                      (0.045, 0.045, 0.045), (0, 0, 0)))
    batch("fireflies", "ico", FX, M["firefly"], flies, sub=1)

    # ---------- 人物（站在门廊台阶前）----------
    build_character(CH, M, -2.7, -0.9, z)
    return BG, FG, CH, LC


# ============================================================
# 相机、太阳、时段
# ============================================================

def build_camera():
    sc = bpy.context.scene
    target = bpy.data.objects.new("CAM_target", None)
    target.location = CAM_TARGET
    sc.collection.objects.link(target)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = CAM_ORTHO_SCALE
    cam_data.shift_x = CAM_SHIFT_X
    cam_data.shift_y = CAM_SHIFT_Y
    cam_data.clip_end = 500
    cam = bpy.data.objects.new("Camera", cam_data)
    az, el = math.radians(CAM_AZIMUTH), math.radians(CAM_ELEVATION)
    d = 80
    cam.location = (CAM_TARGET[0] + d * math.cos(el) * math.sin(az),
                    CAM_TARGET[1] - d * math.cos(el) * math.cos(az),
                    CAM_TARGET[2] + d * math.sin(el))
    sc.collection.objects.link(cam)
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    sc.camera = cam
    return cam


def build_sun():
    sc = bpy.context.scene
    ld = bpy.data.lights.new("Sun", "SUN")
    ld.angle = math.radians(2)
    ld.use_shadow = True
    sun = bpy.data.objects.new("Sun", ld)
    sc.collection.objects.link(sun)
    return sun


TIMES = {
    # el/az: 太阳高度角、方位角；sun/power: 阳光颜色强度；sky: 环境光；tint: 整体色调；
    # bloom: 光晕强度；line: 描边颜色
    "morning": dict(el=13, az=-125, sun=(1.0, 0.74, 0.50), power=3.6, sky=(0.98, 0.74, 0.58), sky_power=0.75,
                    tint=(1.0, 0.86, 0.72), bloom=0.55, line=(0.36, 0.22, 0.16)),
    "noon":    dict(el=62, az=-150, sun=(1.0, 0.97, 0.90), power=4.5, sky=(0.58, 0.78, 1.00), sky_power=0.9,
                    tint=(1.0, 1.0, 1.0), bloom=0.35, line=(0.28, 0.20, 0.15)),
    "night":   dict(el=40, az=-115, sun=(0.55, 0.66, 1.0), power=0.9, sky=(0.06, 0.08, 0.18), sky_power=0.4,
                    tint=(0.36, 0.42, 0.68), bloom=1.0, line=(0.10, 0.10, 0.18)),
}


def ensure_world():
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    w = sc.world
    if bpy.app.version < (5, 0, 0):
        w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg is None:
        w.node_tree.nodes.clear()
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        out = w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return bg


def apply_time(name):
    """切换早/中/晚：太阳、环境光、色调、自发光、点光源、光晕、描边颜色"""
    t = TIMES[name]
    sc = bpy.context.scene
    sun = bpy.data.objects["Sun"]
    sun.rotation_euler = Euler((math.radians(90 - t["el"]), 0, math.radians(t["az"])), "XYZ")
    sun.data.color = lin(t["sun"])
    sun.data.energy = t["power"]
    bg = ensure_world()
    bg.inputs["Color"].default_value = (*lin(t["sky"]), 1)
    bg.inputs["Strength"].default_value = t["sky_power"]
    TOON.nodes["TimeTint"].outputs[0].default_value = (*lin(t["tint"]), 1)
    for m, s in GLOW_MATS:
        em = next(n for n in m.node_tree.nodes if n.type == "EMISSION")
        em.inputs["Strength"].default_value = s[name]
    for ob, p in LIGHTS:
        ob.data.energy = p[name]
        ob.hide_render = p[name] <= 0
    glare = _glare_node()
    if glare is not None:
        glare.inputs["Strength"].default_value = t["bloom"]
    for vl in sc.view_layers:
        for ls in vl.freestyle_settings.linesets:
            if ls.linestyle:
                ls.linestyle.color = lin(t["line"])
    sc["gsd_time"] = name
    print(f"[共生岛] 已切换到 {name}")


# ============================================================
# 渲染设置、视图层、后期光晕
# ============================================================

def set_engine_eevee(sc):
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            return
        except TypeError:
            continue


def setup_render():
    sc = bpy.context.scene
    set_engine_eevee(sc)
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    try:
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
    except Exception:
        pass
    ee = sc.eevee
    for attr, val in (("taa_render_samples", 48), ("use_shadows", True), ("shadow_ray_count", 2),
                      ("shadow_step_count", 8), ("shadow_resolution_scale", 1.0)):
        try:
            setattr(ee, attr, val)
        except Exception:
            pass
    sc.render.use_freestyle = USE_OUTLINE
    if USE_OUTLINE:
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = 1.2


def setup_compositor():
    """后期光晕：Render Layers → Glare(Bloom) → 输出。兼容 5.x（节点组）和 4.x（scene.node_tree）"""
    sc = bpy.context.scene
    if not USE_BLOOM:
        return
    if hasattr(sc, "compositing_node_group"):          # Blender 5.x
        ng = bpy.data.node_groups.new("共生岛_后期", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        sc.compositing_node_group = ng
        out = ng.nodes.new("NodeGroupOutput")
        out_sock = out.inputs["Image"]
    else:                                              # Blender 4.x
        sc.use_nodes = True
        ng = sc.node_tree
        ng.nodes.clear()
        out = ng.nodes.new("CompositorNodeComposite")
        out_sock = out.inputs["Image"]
    rl = ng.nodes.new("CompositorNodeRLayers"); rl.location = (-500, 0)
    rl.layer = "BG"
    glare = ng.nodes.new("CompositorNodeGlare"); glare.name = "Bloom"; glare.location = (-200, 0)
    out.location = (150, 0)
    if "Type" in glare.inputs:
        glare.inputs["Type"].default_value = "Bloom"
        glare.inputs["Threshold"].default_value = 0.9
        glare.inputs["Size"].default_value = 0.7
        glare.inputs["Strength"].default_value = 0.6
    else:
        glare.glare_type = "BLOOM"
        glare.threshold = 0.9
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], out_sock)
    sc.render.use_compositing = True


def _glare_node():
    sc = bpy.context.scene
    ng = getattr(sc, "compositing_node_group", None) if hasattr(sc, "compositing_node_group") else sc.node_tree
    if ng is None:
        return None
    g = ng.nodes.get("Bloom")
    if g is None or "Strength" not in g.inputs:
        return None
    return g


def setup_view_layers(BG, FG, CH, LC):
    sc = bpy.context.scene
    base = sc.view_layers[0]
    base.name = "BG"
    fg = sc.view_layers.new("FG")
    ch = sc.view_layers.new("CHAR")

    def lc(vl, coll):
        return vl.layer_collection.children[coll.name]

    lc(base, FG).exclude = False
    lc(base, CH).exclude = True
    lc(fg, BG).holdout = True
    lc(fg, CH).exclude = True
    lc(ch, BG).exclude = True
    lc(ch, FG).exclude = True
    for vl in sc.view_layers:
        vl.use_freestyle = USE_OUTLINE
        if USE_OUTLINE:
            fs = vl.freestyle_settings
            if len(fs.linesets) == 0:
                fs.linesets.new("Outline")
            for ls in fs.linesets:
                if ls.linestyle is None:
                    continue
                ls.linestyle.thickness = 1.2
    if bpy.context.window:
        bpy.context.window.view_layer = base


# ============================================================
# 导出
# ============================================================

def out_dir():
    base = bpy.path.abspath("//") if bpy.data.filepath else tempfile.gettempdir()
    d = os.path.join(base, "render")
    os.makedirs(d, exist_ok=True)
    return d


def render_layer(layer, filename, transparent, composite=False):
    sc = bpy.context.scene
    sc.render.film_transparent = transparent
    sc.render.use_compositing = composite and USE_BLOOM
    sc.render.filepath = os.path.join(out_dir(), filename)
    bpy.ops.render.render(write_still=True, layer=layer)
    print("[共生岛] 已输出", sc.render.filepath)


def _bg_only(fn):
    """渲染 BG 层时临时排除前景和人物"""
    kids = bpy.context.scene.view_layers["BG"].layer_collection.children
    kids["FG_前景遮挡"].exclude = True
    kids["CHAR_人物"].exclude = True
    try:
        fn()
    finally:
        kids["FG_前景遮挡"].exclude = False
        kids["CHAR_人物"].exclude = False


def render_scene_layers():
    for t in ("morning", "noon", "night"):
        apply_time(t)
        _bg_only(lambda: render_layer("BG", f"bg_{t}.png", transparent=False, composite=True))
        render_layer("FG", f"fg_{t}.png", transparent=True)


def preview(scale=50):
    """三个时段的整体预览（含前景和人物、含光晕），半尺寸"""
    sc = bpy.context.scene
    old = sc.render.resolution_percentage
    sc.render.resolution_percentage = scale
    cur = sc.get("gsd_time", "morning")
    kids = sc.view_layers["BG"].layer_collection.children
    kids["CHAR_人物"].exclude = False
    try:
        for t in ("morning", "noon", "night"):
            apply_time(t)
            render_layer("BG", f"preview_{t}.png", transparent=False, composite=True)
    finally:
        sc.render.resolution_percentage = old
        apply_time(cur)


def render_walkmask():
    sc = bpy.context.scene
    saved = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        saved[ob.name] = [s.material for s in ob.material_slots]
        mat = bpy.data.materials["MASK_white"] if ob.name in WALKABLE else bpy.data.materials["MASK_black"]
        for s in ob.material_slots:
            s.material = mat
    bg = ensure_world()
    old_bg = (tuple(bg.inputs["Color"].default_value), bg.inputs["Strength"].default_value)
    bg.inputs["Color"].default_value = (0, 0, 0, 1)
    old_fs = sc.render.use_freestyle
    sc.render.use_freestyle = False
    hidden = [o for o in bpy.data.objects if o.name in ("sea_sparkles", "fireflies", "shallow_water", "shore_foam", "shore_foam_outer")]
    for o in hidden:
        o.hide_render = True
    try:
        _bg_only(lambda: render_layer("BG", "walkmask.png", transparent=False))
    finally:
        for o in hidden:
            o.hide_render = False
        sc.render.use_freestyle = old_fs
        bg.inputs["Color"].default_value = old_bg[0]
        bg.inputs["Strength"].default_value = old_bg[1]
        for name, mats in saved.items():
            ob = bpy.data.objects[name]
            for s, m in zip(ob.material_slots, mats):
                s.material = m


def char_directions():
    az = math.radians(CAM_AZIMUTH)
    return {"down": az, "right": az + math.pi / 2, "up": az + math.pi, "left": az - math.pi / 2}


def render_character(frames=None):
    sc = bpy.context.scene
    root = bpy.data.objects["CHAR_root"]
    old_rot = root.rotation_euler.z
    rng = frames or range(sc.frame_start, sc.frame_end + 1)
    for dname, ang in char_directions().items():
        root.rotation_euler.z = ang
        for f in rng:
            sc.frame_set(f)
            render_layer("CHAR", f"char_{dname}_{f:03d}.png", transparent=True)
    root.rotation_euler.z = old_rot


def render_character_shadow():
    sc = bpy.context.scene
    old_engine = sc.render.engine
    old_fs = sc.render.use_freestyle
    catcher = bpy.data.objects["CHAR_shadow_catcher"]
    body = [o for o in bpy.data.objects if o.name.startswith("CHAR_") and o.type == "MESH" and o is not catcher]
    root = bpy.data.objects["CHAR_root"]
    old_rot = root.rotation_euler.z
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 32
    sc.render.use_freestyle = False
    catcher.hide_render = False
    for o in body:
        o.visible_camera = False
    try:
        for dname, ang in char_directions().items():
            root.rotation_euler.z = ang
            render_layer("CHAR", f"char_shadow_{dname}.png", transparent=True)
    finally:
        for o in body:
            o.visible_camera = True
        catcher.hide_render = True
        root.rotation_euler.z = old_rot
        sc.render.use_freestyle = old_fs
        sc.render.engine = old_engine


def render_all():
    cur = bpy.context.scene.get("gsd_time", "noon")
    render_scene_layers()
    render_walkmask()
    render_character(frames=[bpy.context.scene.frame_current])
    render_character_shadow()
    apply_time(cur)
    print("[共生岛] 全部输出完成：", out_dir())


# ============================================================
# 主流程
# ============================================================

def build():
    random.seed(SEED)
    GLOW_MATS.clear()
    LIGHTS.clear()
    WALKABLE.clear()
    clear_scene()
    M = build_materials()
    BG, FG, CH, LC = build_world_scene(M)
    build_camera()
    build_sun()
    setup_render()
    setup_view_layers(BG, FG, CH, LC)
    setup_compositor()
    bpy.context.scene.view_layers["BG"].layer_collection.children[CH.name].exclude = False
    apply_time("morning")
    for area in (bpy.context.screen.areas if bpy.context.screen else []):
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"
            area.spaces.active.shading.type = "MATERIAL"
    print(f"[共生岛] 场景搭建完成：{len(bpy.data.objects)} 个物体，{len(LIGHTS)} 盏点光源")


class _API:
    apply_time = staticmethod(apply_time)
    preview = staticmethod(preview)
    render_all = staticmethod(render_all)
    render_scene_layers = staticmethod(render_scene_layers)
    render_walkmask = staticmethod(render_walkmask)
    render_character = staticmethod(render_character)
    render_character_shadow = staticmethod(render_character_shadow)
    rebuild = staticmethod(build)


bpy.app.driver_namespace["gsd"] = _API
import builtins
builtins.gsd = _API

build()
