# -*- coding: utf-8 -*-
"""共生岛 · 魔法教室 · 黑板板书（粉笔字 + 魔法阵）。由 build_classroom.py exec。
全部放在集合 CLS_板书 里，挂在 room_root 下，房间坐标：黑板面 y≈5.12，x −3.1…1.9，z 1.58…3.72。
注意：黑板中央原本预留给桌面端课表 UI；需要叠课表时把这个集合隐藏即可。"""
import bpy, math
from mathutils import Vector

BC = bpy.data.collections.new("CLS_板书"); sc.collection.children.link(BC)
YB = 5.105                                      # 粉笔层贴在黑板面前 1.5 cm


def chalk_mat():
    m = bpy.data.materials.new("CLS_chalk"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (0.92, 0.93, 0.90, 1); em.inputs["Strength"].default_value = 0.55
    df = nt.nodes.new("ShaderNodeBsdfDiffuse"); df.inputs["Color"].default_value = (0.85, 0.86, 0.83, 1)
    ad = nt.nodes.new("ShaderNodeAddShader")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.88
    nt.links.new(df.outputs[0], ad.inputs[0]); nt.links.new(em.outputs[0], ad.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(ad.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        m.blend_method = "HASHED"
    m.diffuse_color = (0.95, 0.95, 0.92, 1)
    return m


CHALK = chalk_mat()


def chalk_text(name, body, x, z, size, rot=0.0):
    cu = bpy.data.curves.new(name, "FONT"); cu.body = body; cu.size = size
    cu.align_x = "LEFT"; cu.align_y = "CENTER"; cu.space_character = 1.05
    ob = bpy.data.objects.new(name, cu); BC.objects.link(ob)
    ob.parent = ROOM; ob.location = (x, YB, z); ob.rotation_euler = (math.pi / 2, rot, 0)
    cu.materials.append(CHALK)
    return ob


def chalk_line(name, pts, w=0.0055, cyclic=False):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = w; cu.bevel_resolution = 1
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for p, (x, z) in zip(sp.points, pts):
        p.co = (x, YB, z, 1)
    sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu); BC.objects.link(ob); ob.parent = ROOM
    cu.materials.append(CHALK)
    return ob


def circle(name, cx, cz, r, n=72, wob=0.006, w=0.0055):
    pts = [(cx + (r + wob * math.sin(7 * a + r * 9)) * math.cos(a), cz + (r + wob * math.sin(7 * a + r * 9)) * math.sin(a))
           for a in (2 * math.pi * i / n for i in range(n))]
    return chalk_line(name, pts, w, True)


def polygon(name, cx, cz, r, k, a0, w=0.0055):
    return chalk_line(name, [(cx + r * math.cos(a0 + 2 * math.pi * i / k), cz + r * math.sin(a0 + 2 * math.pi * i / k)) for i in range(k)], w, True)


# 标题 + 下划线
chalk_text("chalk_title", "LECTIO III  ~  RESONANTIA ELEMENTORUM", -2.85, 3.45, 0.15)
chalk_line("chalk_title_ul", [(-2.86, 3.33), (-1.2, 3.325), (0.35, 3.335)], 0.006)
# 左侧魔法阵：双圆 + 六芒星 + 四元素标记
MX_, MZ_ = -2.05, 2.42
circle("chalk_circ_o", MX_, MZ_, 0.62); circle("chalk_circ_i", MX_, MZ_, 0.52, wob=0.004)
polygon("chalk_tri_a", MX_, MZ_, 0.52, 3, math.pi / 2); polygon("chalk_tri_b", MX_, MZ_, 0.52, 3, -math.pi / 2)
circle("chalk_core", MX_, MZ_, 0.11, n=36, wob=0.002)
for i, (lab, ang) in enumerate((("IGNIS", 90), ("AQUA", 270), ("VENTUS", 180), ("TERRA", 0))):
    a = math.radians(ang)
    chalk_text(f"chalk_el_{i}", lab, MX_ + 0.80 * math.cos(a) - 0.17, MZ_ + 0.80 * math.sin(a), 0.085)
for i in range(6):
    a = math.pi / 2 + i * math.pi / 3
    circle(f"chalk_node_{i}", MX_ + 0.52 * math.cos(a), MZ_ + 0.52 * math.sin(a), 0.035, n=18, wob=0.0015, w=0.004)
# 右侧公式（老师指第三行，教鞭从 x≈−0.2 划到 +0.2）
chalk_text("chalk_eq1", "IGNIS + VENTUS  =  FLAMMA", -0.95, 2.92, 0.12)
chalk_text("chalk_eq2", "AQUA  + TERRA   =  LUTUM", -0.95, 2.62, 0.12)
chalk_text("chalk_eq3", "VERBUM . GESTUS . VOLUNTAS", -0.95, 2.25, 0.12)
chalk_line("chalk_eq3_ul", [(-0.97, 2.15), (0.4, 2.142), (1.2, 2.15)], 0.005)
chalk_line("chalk_arrow", [(-1.18, 2.42), (-1.0, 2.33), (-0.98, 2.29)], 0.005)
chalk_line("chalk_arrow_h", [(-1.06, 2.30), (-0.98, 2.29), (-1.0, 2.37)], 0.005)
# 角落：小星星与备注
polygon("chalk_star", 1.35, 2.88, 0.13, 5, math.pi / 2)
chalk_line("chalk_star_in", [(1.35 + 0.13 * math.cos(math.pi / 2 + i * 4 * math.pi / 5), 2.88 + 0.13 * math.sin(math.pi / 2 + i * 4 * math.pi / 5)) for i in range(6)], 0.0045)
chalk_text("chalk_note", "NB: INCANTATIO LENTA!", -0.95, 1.86, 0.085, rot=0.0)
log(f"黑板板书：{len(BC.objects)} 个粉笔对象（集合 {BC.name}）")
