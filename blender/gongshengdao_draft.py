# -*- coding: utf-8 -*-
"""
共生岛 · Blender 场景草稿（白模 + 卡通着色 + 分层输出）
=====================================================
按开题报告里图9–图11的效果图搭的布局草稿：
  左上木屋 + 左侧码头小船，土路从木屋弯到下方书桌，
  中下樱花树，右侧小溪 + 木桥 + 入海瀑布，背景树林和远岛，
  画面右上角留空给“今日课程 / 今日待办”卡片。

用法（Blender 4.2 及以上）：
  1. 打开 Blender → 顶部切到 Scripting 工作区
  2. 文本编辑器里 Open 这个文件 → 点 ▶ Run Script
  3. 运行后会清空当前场景并重新搭建；在相机视角（小键盘 0）里看效果
  4. 想切换早/中/晚：在下方 Python 控制台输入
         gsd.apply_time("morning")   # 或 "noon" / "night"
  5. 想批量导出 PixiJS 用的素材：把下面 DO_RENDER 改成 True 再运行，
     或在控制台输入 gsd.render_all()
     输出在 .blend 同目录（未保存则在系统临时目录）的 render/ 文件夹：
         bg_morning.png / fg_morning.png …   背景层 / 前景遮挡层（透明底）
         walkmask.png                         可行走区域遮罩（白=可走）
         char_<方向>_<帧>.png                 人物精灵序列帧（透明底）
         char_shadow_<方向>.png               人物阴影层（Cycles 阴影捕捉）

坐标约定：Z 朝上，1 单位 ≈ 1 米；相机从右前方斜俯视（正交）。
所有可调参数都在 “配置” 一节。
"""

import bpy
import bmesh
import math
import os
import random
import sys
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
CAM_SHIFT_X = 0.07      # 画面平移，正值让岛偏左，给右上角卡片留空
CAM_SHIFT_Y = 0.08       # 正值让岛偏下，给顶部远岛留位置
USE_OUTLINE = True      # Freestyle 描边（会让渲染变慢，草稿阶段可关）
DO_RENDER = False       # True = 运行后直接批量导出素材
SEED = 7

ISLAND_RX, ISLAND_RY = 10.0, 8.5   # 主岛椭圆半径
ISLAND_TOP = 0.45                   # 岛面高度
CHAR_HEIGHT = 1.15                  # 人物身高（相对木屋门高约 2）

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
    # 删除多余的视图层
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


def shape(name, kind, coll, mat, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), seg=10, top=1.0, sub=1):
    """kind: cube(边长1，中心原点) / cyl(半径1 高1，中心原点) / cone / ico / sphere"""
    bm = bmesh.new()
    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
    elif kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                              radius1=1.0, radius2=top, depth=1.0)
    elif kind == "cone":
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                              radius1=1.0, radius2=0.0, depth=1.0)
    elif kind == "ico":
        bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    elif kind == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    else:
        raise ValueError(kind)
    return make_mesh_object(name, bm, coll, mat, loc, rot, scale)


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
    """折线 → 平滑曲线（Catmull-Rom），points 为 (x, y)"""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def ribbon(name, points, width, z, coll, mat, steps=8):
    """沿曲线生成贴地的平面带（土路、小溪）"""
    pts = catmull(points, steps)
    verts, faces = [], []
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        w = width * (0.85 + 0.15 * math.sin(i * 0.9))  # 边缘轻微起伏
        verts.append((x + nx * w / 2, y + ny * w / 2, z))
        verts.append((x - nx * w / 2, y - ny * w / 2, z))
    for i in range(len(pts) - 1):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
    return from_pydata(name, verts, faces, coll, mat), pts


# ============================================================
# 材质：卡通着色（Shader to RGB + 阶梯色带）+ 全局时段色调
# ============================================================
TOON = None
GLOW_MATS = []        # (材质, 早/中/晚强度)
WALKABLE = set()      # 可行走物体名称


def build_toon_group():
    ng = bpy.data.node_groups.new("ToonCore", "ShaderNodeTree")
    ng.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    n, l = ng.nodes, ng.links
    gi = n.new("NodeGroupInput"); gi.location = (-800, 0)
    go = n.new("NodeGroupOutput"); go.location = (600, 0)
    diff = n.new("ShaderNodeBsdfDiffuse"); diff.location = (-600, 200)
    s2r = n.new("ShaderNodeShaderToRGB"); s2r.location = (-400, 200)
    ramp = n.new("ShaderNodeValToRGB"); ramp.location = (-200, 200)
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.36, 0.34, 0.50, 1)   # 阴影：略偏冷紫
    cr.elements[1].position = 0.18
    cr.elements[1].color = (0.64, 0.62, 0.70, 1)   # 过渡
    e = cr.elements.new(0.45)
    e.color = (1.0, 1.0, 1.0, 1)                    # 受光
    tint = n.new("ShaderNodeRGB"); tint.name = "TimeTint"; tint.label = "时段色调"
    tint.location = (-200, -150)
    tint.outputs[0].default_value = (1, 1, 1, 1)
    m1 = n.new("ShaderNodeVectorMath"); m1.operation = "MULTIPLY"; m1.location = (100, 100)
    m2 = n.new("ShaderNodeVectorMath"); m2.operation = "MULTIPLY"; m2.location = (250, 0)
    emit = n.new("ShaderNodeEmission"); emit.location = (420, 0)
    l.new(diff.outputs["BSDF"], s2r.inputs["Shader"])
    l.new(s2r.outputs["Color"], ramp.inputs["Fac"])
    l.new(gi.outputs["Color"], m1.inputs[0])
    l.new(ramp.outputs["Color"], m1.inputs[1])
    l.new(m1.outputs["Vector"], m2.inputs[0])
    l.new(tint.outputs["Color"], m2.inputs[1])
    l.new(m2.outputs["Vector"], emit.inputs["Color"])
    l.new(emit.outputs["Emission"], go.inputs["Shader"])
    return ng


def _new_material(name):
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    m.node_tree.nodes.clear()
    return m


def lin(rgb):
    """sRGB(屏幕上看到的颜色) → 线性值（Blender 材质颜色按线性解释）"""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


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
    """自发光材质（窗户、灯笼）。strengths = {"morning":x, "noon":y, "night":z}"""
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


def build_materials():
    global TOON
    TOON = build_toon_group()
    M = {}
    C = {
        "sea": (0.16, 0.48, 0.78), "stream": (0.35, 0.70, 0.90), "foam": (0.88, 0.95, 1.0),
        "grass": (0.42, 0.68, 0.25), "grass_dark": (0.28, 0.50, 0.18), "cliff": (0.55, 0.47, 0.38),
        "path": (0.86, 0.72, 0.50), "rock": (0.58, 0.58, 0.60), "rock_dark": (0.42, 0.42, 0.46),
        "wood": (0.55, 0.35, 0.20), "wood_light": (0.74, 0.54, 0.34), "wall": (0.93, 0.86, 0.72),
        "roof": (0.30, 0.46, 0.38), "stone": (0.66, 0.62, 0.56), "trunk": (0.40, 0.27, 0.18),
        "leaf": (0.30, 0.58, 0.24), "leaf2": (0.38, 0.66, 0.28), "pine": (0.18, 0.42, 0.26),
        "sakura": (0.98, 0.70, 0.80), "sakura2": (0.95, 0.58, 0.72), "white": (0.97, 0.96, 0.92),
        "pink": (0.98, 0.55, 0.70), "purple": (0.62, 0.50, 0.90), "yellow": (0.98, 0.84, 0.32),
        "lily": (0.30, 0.55, 0.30), "boat": (0.62, 0.45, 0.28), "skin": (1.0, 0.85, 0.74),
        "hair": (0.40, 0.25, 0.16), "shirt": (0.96, 0.92, 0.84), "skirt": (0.25, 0.38, 0.30),
        "laptop": (0.75, 0.77, 0.80), "far_island": (0.36, 0.58, 0.40),
    }
    for k, v in C.items():
        M[k] = toon("T_" + k, v)
    M["window"] = glow("G_window", (1.0, 0.72, 0.38), {"morning": 1.2, "noon": 0.35, "night": 6.0})
    M["lantern"] = glow("G_lantern", (1.0, 0.78, 0.45), {"morning": 1.5, "noon": 0.3, "night": 9.0})
    M["mask_white"] = flat_emit("MASK_white", (1, 1, 1))
    M["mask_black"] = flat_emit("MASK_black", (0, 0, 0))
    return M


# ============================================================
# 场景元素
# ============================================================

def island_radius(theta):
    """主岛轮廓的半径扰动（固定公式，方便计算岸边位置）"""
    return 1.0 + 0.07 * math.sin(3 * theta + 0.5) + 0.05 * math.sin(5 * theta + 1.3) + 0.03 * math.sin(9 * theta)


def island_edge(theta, rx=ISLAND_RX, ry=ISLAND_RY, cx=0.0, cy=0.0):
    r = island_radius(theta)
    return (cx + rx * r * math.cos(theta), cy + ry * r * math.sin(theta))


def blob_island(name_top, name_side, cx, cy, rx, ry, top, bottom, coll_top, coll_side, mat_top, mat_side, n=64, radius_fn=None):
    rf = radius_fn or (lambda t: 1.0 + 0.08 * math.sin(4 * t + cx) + 0.05 * math.sin(7 * t + cy))
    ring = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = rf(t)
        ring.append((cx + rx * r * math.cos(t), cy + ry * r * math.sin(t)))
    # 顶面（扇形三角化，星形轮廓可用）
    verts = [(cx, cy, top)] + [(x, y, top) for x, y in ring]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    top_ob = from_pydata(name_top, verts, faces, coll_top, mat_top)
    # 侧面（岸壁，向下略收）
    verts, faces = [], []
    for x, y in ring:
        verts.append((x, y, top))
    for x, y in ring:
        verts.append((cx + (x - cx) * 0.93, cy + (y - cy) * 0.93, bottom))
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, n + i, n + j, j))
    side_ob = from_pydata(name_side, verts, faces, coll_side, mat_side)
    return top_ob, side_ob, ring


def tree(prefix, coll, M, x, y, z, h=3.0, r=1.4, leaf="leaf", kind="round"):
    shape(prefix + "_trunk", "cyl", coll, M["trunk"], loc=(x, y, z + h * 0.3), scale=(0.18 * h / 3, 0.18 * h / 3, h * 0.6), seg=7, top=0.7)
    if kind == "pine":
        for k in range(3):
            s = r * (1.0 - k * 0.25)
            shape(prefix + f"_pine{k}", "cone", coll, M["pine"], loc=(x, y, z + h * (0.55 + k * 0.28)), scale=(s, s, h * 0.45), seg=8)
    else:
        for k in range(3):
            ox, oy = random.uniform(-0.45, 0.45) * r, random.uniform(-0.45, 0.45) * r
            s = r * random.uniform(0.7, 1.0)
            shape(prefix + f"_leaf{k}", "ico", coll, M[leaf if k != 1 else "leaf2"],
                  loc=(x + ox, y + oy, z + h * 0.75 + random.uniform(-0.2, 0.4)), scale=(s, s, s * 0.85), sub=1)


def flowers(prefix, coll, M, cx, cy, z, n=10, spread=0.8):
    cols = ["pink", "white", "purple", "yellow", "pink", "white"]
    for i in range(n):
        x, y = cx + random.uniform(-spread, spread), cy + random.uniform(-spread * 0.6, spread * 0.6)
        s = random.uniform(0.12, 0.2)
        shape(f"{prefix}_{i}", "ico", coll, M[random.choice(cols)], loc=(x, y, z + s * 0.8), scale=(s, s, s), sub=1)
    shape(prefix + "_bush", "ico", coll, M["grass_dark"], loc=(cx, cy, z + 0.15), scale=(spread, spread * 0.6, 0.25), sub=1)


def lantern(prefix, coll, M, x, y, z):
    shape(prefix + "_post", "cube", coll, M["wood"], loc=(x, y, z + 0.6), scale=(0.1, 0.1, 1.2))
    shape(prefix + "_box", "cube", coll, M["lantern"], loc=(x, y, z + 1.3), scale=(0.26, 0.26, 0.32))
    shape(prefix + "_cap", "cone", coll, M["wood"], loc=(x, y, z + 1.55), scale=(0.24, 0.24, 0.18), seg=4, rot=(0, 0, math.pi / 4))


def fence(prefix, coll, M, a, b, z, n=6):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ln = math.hypot(b[0] - a[0], b[1] - a[1])
    for i in range(n + 1):
        t = i / n
        shape(f"{prefix}_p{i}", "cube", coll, M["wood"], loc=(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, z + 0.4), scale=(0.12, 0.12, 0.8))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    for k, hz in enumerate((0.35, 0.65)):
        shape(f"{prefix}_rail{k}", "cube", coll, M["wood_light"], loc=(mx, my, z + hz), scale=(ln, 0.07, 0.07), rot=(0, 0, ang))


def build_house(coll, M, x, y, z):
    W, D, H = 4.4, 3.6, 2.3
    # 石基
    shape("house_base", "cube", coll, M["stone"], loc=(x, y, z + 0.2), scale=(W + 0.3, D + 0.3, 0.4))
    # 墙体
    shape("house_wall", "cube", coll, M["wall"], loc=(x, y, z + 0.4 + H / 2), scale=(W, D, H))
    # 木框
    for sx in (-1, 1):
        for sy in (-1, 1):
            shape(f"house_beam_{sx}_{sy}", "cube", coll, M["wood"], loc=(x + sx * W / 2, y + sy * D / 2, z + 0.4 + H / 2), scale=(0.18, 0.18, H))
    # 人字形屋顶（屋脊沿 X 方向）
    zr = z + 0.4 + H
    ov = 0.45
    rh = 1.8
    v = [(x - W / 2 - ov, y - D / 2 - ov, zr - 0.1), (x + W / 2 + ov, y - D / 2 - ov, zr - 0.1),
         (x + W / 2 + ov, y, zr + rh), (x - W / 2 - ov, y, zr + rh),
         (x - W / 2 - ov, y + D / 2 + ov, zr - 0.1), (x + W / 2 + ov, y + D / 2 + ov, zr - 0.1)]
    f = [(0, 1, 2, 3), (3, 2, 5, 4)]
    roof = from_pydata("house_roof", v, f, coll, M["roof"])
    roof.modifiers.new("厚度", "SOLIDIFY").thickness = 0.18
    # 山墙
    gv = [(x - W / 2, y - D / 2, zr), (x - W / 2, y + D / 2, zr), (x - W / 2, y, zr + rh - 0.1),
          (x + W / 2, y - D / 2, zr), (x + W / 2, y + D / 2, zr), (x + W / 2, y, zr + rh - 0.1)]
    from_pydata("house_gable", gv, [(0, 1, 2), (3, 5, 4)], coll, M["wall"])
    # 烟囱
    shape("house_chimney", "cube", coll, M["stone"], loc=(x + W * 0.28, y + 0.6, zr + rh * 0.75), scale=(0.55, 0.55, 1.6))
    # 门窗（正面朝 -Y，侧面朝 +X，都对着相机）
    shape("house_door", "cube", coll, M["wood"], loc=(x + 0.9, y - D / 2 - 0.03, z + 0.4 + 0.95), scale=(0.9, 0.06, 1.9))
    for i, wx in enumerate((-1.3, -0.3)):
        shape(f"house_win_front{i}", "cube", coll, M["window"], loc=(x + wx, y - D / 2 - 0.04, z + 0.4 + 1.3), scale=(0.75, 0.05, 0.85))
    for i, wy in enumerate((-0.8, 0.7)):
        shape(f"house_win_side{i}", "cube", coll, M["window"], loc=(x + W / 2 + 0.04, y + wy, z + 0.4 + 1.3), scale=(0.05, 0.75, 0.85))
    # 门廊木平台 + 台阶
    porch = shape("house_porch", "cube", coll, M["wood_light"], loc=(x + 0.3, y - D / 2 - 0.9, z + 0.25), scale=(W + 1.2, 1.6, 0.18))
    WALKABLE.add(porch.name)
    for k in range(3):
        st = shape(f"house_step{k}", "cube", coll, M["wood_light"], loc=(x + 1.6, y - D / 2 - 1.95 - k * 0.35, z + 0.18 - k * 0.07), scale=(1.2, 0.35, 0.1))
        WALKABLE.add(st.name)
    # 门廊栏杆
    fence("house_rail", coll, M, (x - W / 2 - 0.2, y - D / 2 - 1.65), (x + 0.9, y - D / 2 - 1.65), z + 0.3, n=4)
    # 门口小灯
    lantern("house_lamp", coll, M, x + 1.7, y - D / 2 - 0.4, z + 0.3)


def build_dock(coll, M, x, y, z):
    deck = shape("dock_deck", "cube", coll, M["wood_light"], loc=(x, y, z), scale=(4.2, 2.0, 0.16))
    WALKABLE.add(deck.name)
    for i in range(5):
        for sy in (-1, 1):
            shape(f"dock_post{i}_{sy}", "cyl", coll, M["wood"], loc=(x - 2 + i, y + sy * 0.9, z - 0.4), scale=(0.08, 0.08, 1.0), seg=6)
    # 小船
    shape("boat_hull", "sphere", coll, M["boat"], loc=(x - 1.0, y - 2.2, 0.08), scale=(1.5, 0.55, 0.3), rot=(0, 0, 0.15))
    shape("boat_inner", "sphere", coll, M["wood"], loc=(x - 1.0, y - 2.2, 0.16), scale=(1.3, 0.42, 0.18), rot=(0, 0, 0.15))
    lantern("dock_lamp", coll, M, x + 1.8, y + 0.8, z + 0.08)


def build_bridge(coll, M, a, b, z):
    """拱形木桥，从 a 到 b"""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ln = math.hypot(b[0] - a[0], b[1] - a[1])
    n = 9
    for i in range(n):
        t = (i + 0.5) / n
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        hz = z + 0.45 * math.sin(math.pi * t)
        p = shape(f"bridge_plank{i}", "cube", coll, M["wood_light"], loc=(px, py, hz), scale=(ln / n * 0.92, 1.3, 0.1), rot=(0, 0, ang))
        WALKABLE.add(p.name)
    for side in (-1, 1):
        ox, oy = -math.sin(ang) * 0.65 * side, math.cos(ang) * 0.65 * side
        for i in range(4):
            t = i / 3
            px, py = a[0] + (b[0] - a[0]) * t + ox, a[1] + (b[1] - a[1]) * t + oy
            shape(f"bridge_post{side}_{i}", "cube", coll, M["wood"], loc=(px, py, z + 0.45 * math.sin(math.pi * t) + 0.35), scale=(0.1, 0.1, 0.7))
        shape(f"bridge_rail{side}", "cube", coll, M["wood"], loc=((a[0] + b[0]) / 2 + ox, (a[1] + b[1]) / 2 + oy, z + 0.85), scale=(ln, 0.07, 0.07), rot=(0, 0, ang))


def build_desk_area(coll, M, x, y, z):
    # 书桌（人物写字、用电脑的位置）
    shape("desk_top", "cube", coll, M["wood_light"], loc=(x, y, z + 0.75), scale=(1.8, 0.9, 0.08))
    for sx in (-1, 1):
        for sy in (-1, 1):
            shape(f"desk_leg{sx}{sy}", "cube", coll, M["wood"], loc=(x + sx * 0.8, y + sy * 0.35, z + 0.37), scale=(0.08, 0.08, 0.74))
    shape("desk_laptop", "cube", coll, M["laptop"], loc=(x - 0.2, y, z + 0.81), scale=(0.55, 0.38, 0.03))
    shape("desk_screen", "cube", coll, M["laptop"], loc=(x - 0.2, y + 0.2, z + 1.0), scale=(0.55, 0.03, 0.38), rot=(math.radians(-12), 0, 0))
    shape("desk_books", "cube", coll, M["pink"], loc=(x + 0.55, y + 0.05, z + 0.86), scale=(0.35, 0.26, 0.14))
    shape("desk_lamp", "cube", coll, M["lantern"], loc=(x + 0.75, y - 0.25, z + 0.9), scale=(0.15, 0.15, 0.22))
    # 长椅（休息位置）
    shape("bench_seat", "cube", coll, M["wood_light"], loc=(x, y - 1.0, z + 0.42), scale=(1.8, 0.45, 0.08))
    for sx in (-1, 1):
        shape(f"bench_leg{sx}", "cube", coll, M["wood"], loc=(x + sx * 0.75, y - 1.0, z + 0.2), scale=(0.1, 0.4, 0.4))
    # 树桩凳
    shape("stump", "cyl", coll, M["trunk"], loc=(x + 1.5, y + 0.2, z + 0.25), scale=(0.3, 0.3, 0.5), seg=8)
    # 鸟屋
    shape("birdhouse_post", "cube", coll, M["wood"], loc=(x + 2.2, y + 0.9, z + 0.8), scale=(0.08, 0.08, 1.6))
    shape("birdhouse", "cube", coll, M["wood_light"], loc=(x + 2.2, y + 0.9, z + 1.7), scale=(0.35, 0.35, 0.4))


def build_cherry(coll, M, x, y, z):
    shape("sakura_trunk", "cyl", coll, M["trunk"], loc=(x, y, z + 1.0), scale=(0.28, 0.28, 2.0), seg=8, top=0.6)
    for i, (dx, dy, rz) in enumerate(((0.6, 0.2, -0.6), (-0.5, 0.3, 0.6), (0.1, -0.5, 0.2))):
        shape(f"sakura_branch{i}", "cyl", coll, M["trunk"], loc=(x + dx * 0.6, y + dy * 0.6, z + 2.2),
              scale=(0.1, 0.1, 1.2), rot=(dy * 0.8, -dx * 0.8, rz), seg=6, top=0.5)
    for i in range(7):
        a = 2 * math.pi * i / 7
        r = 1.3 if i else 0
        s = random.uniform(1.0, 1.35)
        shape(f"sakura_bloom{i}", "ico", coll, M["sakura" if i % 2 else "sakura2"],
              loc=(x + r * math.cos(a), y + r * math.sin(a), z + 2.9 + random.uniform(-0.3, 0.4)), scale=(s, s, s * 0.8), sub=2)
    # 落花
    for i in range(14):
        shape(f"sakura_petal{i}", "cyl", coll, M["sakura"], loc=(x + random.uniform(-2.5, 2.5), y + random.uniform(-2.5, 2.0), z + 0.02),
              scale=(0.12, 0.12, 0.01), seg=6)


def build_stream(coll_bg, coll_fg, M, z):
    """右侧小溪：从背景树林流下，穿过木桥，到岸边形成瀑布入海"""
    theta_end = math.atan2(-5.3 / ISLAND_RY, 6.4 / ISLAND_RX)
    ex, ey = island_edge(theta_end)
    pts = [(6.5, 9.5), (5.6, 6.0), (4.9, 3.0), (5.0, 0.8), (5.6, -1.8), (ex * 0.93, ey * 0.93), (ex, ey)]
    ob, curve = ribbon("stream", pts, 1.5, z + 0.03, coll_bg, M["stream"], steps=10)
    # 岸边石头
    for i in range(0, len(curve) - 2, 3):
        x, y = curve[i]
        a, b = curve[i], curve[min(i + 1, len(curve) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1
        for side in (-1, 1):
            nx, ny = -dy / ln * side, dx / ln * side
            s = random.uniform(0.25, 0.5)
            shape(f"stream_rock{i}_{side}", "ico", coll_bg, M["rock" if random.random() > 0.3 else "rock_dark"],
                  loc=(x + nx * 0.95, y + ny * 0.95, z + s * 0.4), scale=(s, s * 0.9, s * 0.7), sub=1)
    # 瀑布：从岸边垂直落到海面
    ux, uy = ex / math.hypot(ex, ey), ey / math.hypot(ex, ey)
    px, py = -uy, ux
    w = 0.7
    v = [(ex + px * w, ey + py * w, z + 0.03), (ex - px * w, ey - py * w, z + 0.03),
         (ex - px * w + ux * 0.5, ey - py * w + uy * 0.5, 0.02), (ex + px * w + ux * 0.5, ey + py * w + uy * 0.5, 0.02)]
    from_pydata("waterfall", v, [(0, 1, 2, 3)], coll_fg, M["foam"])
    for i in range(5):
        s = random.uniform(0.25, 0.45)
        shape(f"waterfall_foam{i}", "ico", coll_bg, M["foam"],
              loc=(ex + ux * 0.9 + px * random.uniform(-0.8, 0.8), ey + uy * 0.9 + py * random.uniform(-0.8, 0.8), 0.05),
              scale=(s, s, s * 0.35), sub=1)
    for side in (-1, 1):
        s = 0.8
        shape(f"waterfall_rock{side}", "ico", coll_fg, M["rock_dark"], loc=(ex + px * 1.3 * side, ey + py * 1.3 * side, z * 0.5),
              scale=(s, s, s * 0.9), sub=1)
    return curve


def build_character(coll, M, x, y, z):
    """人物占位：Q 版比例（大头），正面朝 -Y。之后换成正式建模，名字保持 CHAR_root 即可"""
    root = bpy.data.objects.new("CHAR_root", None)
    root.empty_display_type = "ARROWS"
    root.location = (x, y, z)
    coll.objects.link(root)
    h = CHAR_HEIGHT
    parts = [
        ("CHAR_legs", "cyl", M["skin"], (0, 0, h * 0.13), (0.12 * h, 0.1 * h, 0.26 * h), dict(seg=8)),
        ("CHAR_skirt", "cone", M["skirt"], (0, 0, h * 0.36), (0.24 * h, 0.24 * h, 0.3 * h), dict(seg=10)),
        ("CHAR_body", "cyl", M["shirt"], (0, 0, h * 0.5), (0.16 * h, 0.13 * h, 0.24 * h), dict(seg=10, top=0.85)),
        ("CHAR_head", "sphere", M["skin"], (0, 0, h * 0.8), (0.22 * h, 0.21 * h, 0.22 * h), {}),
        ("CHAR_hair", "sphere", M["hair"], (0, 0.03 * h, h * 0.84), (0.245 * h, 0.235 * h, 0.23 * h), {}),
    ]
    for name, kind, mat, loc, sc, kw in parts:
        ob = shape(name, kind, coll, mat, loc=loc, scale=sc, **kw)
        ob.parent = root
    # 刘海前开口：用脸部小球露出
    face = shape("CHAR_face", "sphere", coll, M["skin"], loc=(0, -0.06 * h, h * 0.78), scale=(0.18 * h, 0.17 * h, 0.17 * h))
    face.parent = root
    # 阴影捕捉面（仅 Cycles 阴影层使用，平时隐藏）
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.5)
    catcher = make_mesh_object("CHAR_shadow_catcher", bm, coll, M["white"], loc=(x, y, z + 0.005))
    catcher.is_shadow_catcher = True
    catcher.hide_render = True
    catcher.hide_viewport = True
    return root


def build_world_scene(M):
    sc = bpy.context.scene
    root = sc.collection
    BG = new_collection("BG_背景")
    FG = new_collection("FG_前景遮挡")
    CH = new_collection("CHAR_人物")
    WATER = new_collection("BG_水面", BG)
    ISL = new_collection("BG_岛屿", BG)
    PROPS = new_collection("BG_建筑道具", BG)
    PLANTS = new_collection("BG_植物", BG)
    FAR = new_collection("BG_远景", BG)

    z = ISLAND_TOP

    # 海面
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=120)
    make_mesh_object("sea", bm, WATER, M["sea"], loc=(0, 20, 0))

    # 主岛
    top, side, ring = blob_island("island_top", "island_cliff", 0, 0, ISLAND_RX, ISLAND_RY, z, -1.0,
                                  ISL, ISL, M["grass"], M["cliff"], n=72, radius_fn=island_radius)
    WALKABLE.add(top.name)
    # 岸边石头一圈 + 睡莲
    for i, (x, y) in enumerate(ring):
        if random.random() < 0.75:
            s = random.uniform(0.35, 0.8)
            shape(f"shore_rock{i}", "ico", ISL, M["rock" if random.random() > 0.35 else "rock_dark"],
                  loc=(x * 1.02, y * 1.02, random.uniform(0.0, 0.25)), scale=(s, s * random.uniform(0.8, 1.2), s * 0.7), sub=1)
        if random.random() < 0.3:
            s = random.uniform(0.25, 0.4)
            shape(f"lily{i}", "cyl", WATER, M["lily"], loc=(x * 1.18, y * 1.18, 0.02), scale=(s, s, 0.02), seg=8)

    # 木屋（左上）+ 码头（左侧水面）
    build_house(PROPS, M, -4.6, 3.2, z)
    build_dock(PROPS, M, -11.6, 1.6, 0.4)

    # 土路
    path_main = [(-3.0, -0.6), (-2.4, -1.9), (-1.2, -3.0), (0.2, -3.9), (1.2, -4.6)]
    path_bridge = [(-1.2, -3.0), (0.8, -1.8), (2.6, -0.4), (3.9, 0.6)]
    path_back = [(-2.2, 1.6), (-1.0, 4.2), (0.6, 6.6)]
    path_dock = [(-6.5, 0.2), (-8.5, 0.9), (-9.6, 1.4)]
    path_right = [(6.2, 1.4), (7.6, 2.2), (8.3, 3.4)]
    for name, pts, w in (("path_main", path_main, 1.3), ("path_bridge", path_bridge, 1.1), ("path_back", path_back, 1.0),
                         ("path_dock", path_dock, 1.0), ("path_right", path_right, 0.9)):
        ob, _ = ribbon(name, pts, w, z + 0.02, PROPS, M["path"])
        WALKABLE.add(ob.name)

    # 小溪、木桥
    build_stream(PROPS, FG, M, z)
    build_bridge(PROPS, M, (4.0, 0.65), (6.1, 1.35), z)

    # 书桌区（中下）
    build_desk_area(PROPS, M, 1.6, -5.4, z)

    # 樱花树（前景，人物走到树后会被遮挡）
    build_cherry(FG, M, 2.6, -2.4, z)

    # 灯笼
    for i, (x, y) in enumerate(((-2.0, -0.9), (-0.4, -2.4), (2.0, -4.0), (2.9, 0.1), (7.2, 1.5), (-1.2, 3.6))):
        lantern(f"lamp{i}", PROPS, M, x, y, z)

    # 栅栏：码头上岸处、书桌外侧（前景）、右侧菜园
    fence("fence_dock", PROPS, M, (-8.2, -0.6), (-6.8, -1.8), z, n=3)
    fence("fence_front", FG, M, (-0.8, -6.6), (3.6, -7.2), z, n=6)
    fence("fence_garden_a", PROPS, M, (7.0, 3.0), (9.0, 2.6), z, n=4)
    fence("fence_garden_b", PROPS, M, (9.0, 2.6), (9.2, 5.0), z, n=4)
    for r in range(3):
        for c in range(4):
            shape(f"garden_crop{r}{c}", "ico", PROPS, M["leaf2"], loc=(7.4 + c * 0.42, 3.4 + r * 0.5, z + 0.15), scale=(0.18, 0.18, 0.18), sub=1)

    # 花丛
    for i, (x, y) in enumerate(((-6.6, 0.6), (-3.2, 0.4), (-7.3, 3.6), (-1.0, -1.0), (0.4, -5.6), (-0.6, 1.8), (3.6, -3.6), (6.6, -3.2))):
        flowers(f"flower{i}", PROPS, M, x, y, z, n=9)

    # 背景树林
    trees_bg = [(1.0, 7.2, "round"), (3.2, 6.0, "round"), (-1.5, 6.6, "pine"), (7.8, 6.0, "round"), (4.0, 7.8, "pine"),
                (-7.2, 6.0, "round"), (-8.6, 3.6, "pine"), (8.6, -0.8, "round"), (-0.4, 5.0, "round"), (2.2, 3.4, "round"),
                (7.0, -1.2, "round"), (-5.0, 6.6, "pine")]
    for i, (x, y, k) in enumerate(trees_bg):
        tree(f"tree{i}", PLANTS, M, x, y, z, h=random.uniform(3.0, 4.0), r=random.uniform(1.2, 1.7), kind=k)
    # 近景树（前景遮挡）
    tree("tree_front0", FG, M, -6.2, -4.6, z, h=3.2, r=1.4)
    tree("tree_front1", FG, M, 7.4, -4.0, z, h=2.8, r=1.2)

    # 鸭子
    for i, (x, y) in enumerate(((-9.6, -5.4), (-8.8, -6.1), (-8.0, -6.8))):
        shape(f"duck{i}_body", "sphere", WATER, M["white"], loc=(x, y, 0.12), scale=(0.28, 0.18, 0.15))
        shape(f"duck{i}_head", "sphere", WATER, M["white"], loc=(x + 0.2, y - 0.05, 0.32), scale=(0.11, 0.11, 0.11))

    # 远岛（左上背景，带小屋）
    for i, (cx, cy, rx, ry) in enumerate(((-16.0, 11.5, 3.6, 1.7), (-6.0, 17.0, 4.0, 1.7), (6.0, 19.5, 3.2, 1.5))):
        blob_island(f"far{i}_top", f"far{i}_side", cx, cy, rx, ry, 1.2, -0.5, FAR, FAR, M["far_island"], M["cliff"], n=40)
        for k in range(4):
            tree(f"far{i}_tree{k}", FAR, M, cx + random.uniform(-rx * 0.6, rx * 0.6), cy + random.uniform(-ry * 0.4, ry * 0.4), 1.2,
                 h=2.2, r=1.0, leaf="far_island", kind="round" if k % 2 else "pine")
    shape("far_hut", "cube", FAR, M["wall"], loc=(-15.0, 11.0, 1.7), scale=(1.1, 0.9, 1.0))
    shape("far_hut_roof", "cone", FAR, M["roof"], loc=(-15.0, 11.0, 2.5), scale=(1.0, 0.8, 0.6), seg=4, rot=(0, 0, math.pi / 4))

    # 人物占位：站在门廊前
    build_character(CH, M, -2.6, -0.8, z)

    return BG, FG, CH


# ============================================================
# 相机、灯光、时段
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
    ld.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", ld)
    sc.collection.objects.link(sun)
    return sun


TIMES = {
    # 太阳高度角/方位角(度)、阳光颜色、强度、天空颜色、天空强度、整体色调
    "morning": dict(el=14, az=-130, sun=(1.0, 0.76, 0.52), power=3.5, sky=(0.98, 0.72, 0.55), sky_power=0.7, tint=(1.0, 0.87, 0.74)),
    "noon":    dict(el=62, az=-150, sun=(1.0, 0.97, 0.90), power=4.5, sky=(0.55, 0.76, 1.00), sky_power=0.9, tint=(1.0, 1.0, 1.0)),
    "night":   dict(el=38, az=-120, sun=(0.55, 0.66, 1.0), power=0.8, sky=(0.05, 0.07, 0.16), sky_power=0.35, tint=(0.40, 0.46, 0.72)),
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
    """切换早/中/晚：太阳、天空、全局色调、窗户和灯笼亮度"""
    t = TIMES[name]
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
    bpy.context.scene["gsd_time"] = name
    print(f"[共生岛] 已切换到 {name}")


# ============================================================
# 渲染设置与视图层
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
        sc.view_settings.view_transform = "Standard"   # 卡通配色不要被 AgX/Filmic 压灰
        sc.view_settings.look = "None"
    except Exception:
        pass
    try:
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    sc.render.use_freestyle = USE_OUTLINE
    if USE_OUTLINE:
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = 1.3


def setup_view_layers(BG, FG, CH):
    sc = bpy.context.scene
    base = sc.view_layers[0]
    base.name = "BG"
    fg = sc.view_layers.new("FG")
    ch = sc.view_layers.new("CHAR")

    def lc(vl, coll):
        return vl.layer_collection.children[coll.name]

    # BG：背景 + 人物（预览用）；导出时人物另出
    lc(base, FG).exclude = False
    lc(base, CH).exclude = True
    # FG：只出前景遮挡物，背景作为 holdout（被背景挡住的部分会抠空）
    lc(fg, BG).holdout = True
    lc(fg, CH).exclude = True
    # CHAR：只出人物
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
                ls.linestyle.color = lin((0.30, 0.20, 0.15))
                ls.linestyle.thickness = 1.3
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


def render_layer(layer, filename, transparent):
    sc = bpy.context.scene
    sc.render.film_transparent = transparent
    sc.render.filepath = os.path.join(out_dir(), filename)
    bpy.ops.render.render(write_still=True, layer=layer)
    print("[共生岛] 已输出", sc.render.filepath)


def render_scene_layers():
    """三个时段 × 背景层/前景层"""
    kids = bpy.context.scene.view_layers["BG"].layer_collection.children
    for t in ("morning", "noon", "night"):
        apply_time(t)
        # 背景层不含前景遮挡物和人物
        kids["FG_前景遮挡"].exclude = True
        kids["CHAR_人物"].exclude = True
        try:
            render_layer("BG", f"bg_{t}.png", transparent=False)
        finally:
            kids["FG_前景遮挡"].exclude = False
            kids["CHAR_人物"].exclude = False
        render_layer("FG", f"fg_{t}.png", transparent=True)


def render_walkmask():
    """可行走遮罩：可走的面渲成白色，其余全黑"""
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
    vl = sc.view_layers["BG"]
    vl.layer_collection.children["FG_前景遮挡"].exclude = True
    vl.layer_collection.children["CHAR_人物"].exclude = True
    try:
        render_layer("BG", "walkmask.png", transparent=False)
    finally:
        vl.layer_collection.children["FG_前景遮挡"].exclude = False
        vl.layer_collection.children["CHAR_人物"].exclude = False
        sc.render.use_freestyle = old_fs
        bg.inputs["Color"].default_value = old_bg[0]
        bg.inputs["Strength"].default_value = old_bg[1]
        for name, mats in saved.items():
            ob = bpy.data.objects[name]
            for s, m in zip(ob.material_slots, mats):
                s.material = m


def char_directions():
    """4 个屏幕方向对应的人物朝向（人物默认面朝 -Y）"""
    az = math.radians(CAM_AZIMUTH)
    return {"down": az, "right": az + math.pi / 2, "up": az + math.pi, "left": az - math.pi / 2}


def render_character(frames=None):
    """人物序列帧：4 方向 × 动作帧（默认当前动作的帧范围）"""
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
    """人物阴影层：用 Cycles 阴影捕捉面，只留下投影（人物本身不可见）"""
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
    GLOW_MATS.clear()
    WALKABLE.clear()
    clear_scene()
    M = build_materials()
    BG, FG, CH = build_world_scene(M)
    build_camera()
    build_sun()
    setup_render()
    setup_view_layers(BG, FG, CH)
    # BG 视图层默认显示人物，方便看比例
    bpy.context.scene.view_layers["BG"].layer_collection.children[CH.name].exclude = False
    apply_time("morning")
    # 视口切到相机 + 材质预览
    for area in (bpy.context.screen.areas if bpy.context.screen else []):
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"
            area.spaces.active.shading.type = "MATERIAL"
    print(f"[共生岛] 场景搭建完成：{len(bpy.data.objects)} 个物体")


# 让控制台可以用 gsd.apply_time(...) / gsd.render_all()
class _API:
    apply_time = staticmethod(apply_time)
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
if DO_RENDER:
    render_all()
