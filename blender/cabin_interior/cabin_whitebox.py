# -*- coding: utf-8 -*-
"""
共生岛 · 木屋室内 · 布局白模 v1（2026-11-24）
================================================
运行（Mac，无界面，不打开任何 .blend）：
  Blender -b --factory-startup -P blender/cabin_interior/cabin_whitebox.py -- [--times night,dawn] [--pct 50] [--samples 32] [--wb-only] [--closeups] [--headcrop] [--deskcams]

做什么：
  · 用岛屿同一套画风函数（lin / pbr / glow / PALETTE，风格化 PBR + AO + Bloom）搭剖面木屋室内；室内人物不加描边
  · 远处两面墙完整：北墙 = 木屋正面（门 + 两扇窗），东墙 = 山墙（两扇窗）；近处两面墙切到地板高度
  · 镜头和岛屿相同：方位 −28°、俯角 42°、正交
  · 家具道具全部原创：书桌 / 椅子 / 墙上书架 / 台灯 / 床 / 被子 / 枕头 / 床头柜 / 小夜灯 / 衣帽架 / 火炉 / 地毯 / 橘猫 ……
  · 从 island_night.blend 追加伊蕾娜 3 份：书桌坐姿（C3_fire_loop 第 1 帧）、中央站姿（A1_idle 第 1 帧）、床上侧睡（Laying Sleeping 第 40 帧，见 build_sleep）
  · 侧睡：冻结成静态网格，被子是程序高度场（不用物理），只露头，头发 / 头带不顶被子，穿模检查全为 0
  · 屋里不戴帽：帽子（人物自己的帽子网格）挂在门边衣帽架上
输出（blender/cabin_interior/whitebox/v1/）：
  wb_main.jpg 主镜头 Workbench · wb_top.jpg 俯视（1 米网格 + 站位 + 路径）· eevee_<时段>.jpg 风格预览 · layout.json · build_log.txt
  另存 blender/cabin_interior/cabin_whitebox.blend
坐标：Z 朝上，1 单位 = 1 米；地板顶面 z = 0；北墙内侧 y = +1.9，东墙内侧 x = +2.4。
"""
import bpy, bmesh, math, os, sys, json, time, random
from mathutils import Vector, Matrix, Euler, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("GSD_CABIN_BUILD_OUT") or os.path.join(HERE, "whitebox", "v1")
os.makedirs(OUT, exist_ok=True)
LOGP = os.path.join(OUT, "build_log.txt")
open(LOGP, "w", encoding="utf-8").close()
T0 = time.time()


def log(m):
    m = f"[{time.time() - T0:6.1f}s] {m}"
    print(m, flush=True)
    with open(LOGP, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


RENDER_TIMES = [t for t in arg("--times", "night,dawn").split(",") if t]
PCT = int(arg("--pct", "50"))
SAMPLES = int(arg("--samples", "32"))
WB_ONLY = "--wb-only" in ARGV
# 外部文件：Mac 默认在 ~/Desktop/共生岛；Windows 用环境变量指过去（见 docs/04_Harness/Codex提示词_室内渲染.md）
GSD_ROOT = os.environ.get("GSD_ROOT") or os.path.expanduser("~/Desktop/共生岛")
CHAR_SRC = os.environ.get("GSD_CHAR_SRC") or os.path.join(GSD_ROOT, "blender", "island_final", "island_night.blend")
LIB_DIR = os.path.dirname(HERE)          # 仓库 blender/：retarget_mixamo.py、cloth_sim.py
CLOTH_PATH = os.path.join(LIB_DIR, "cloth_sim.py")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
if sys.platform == "win32":
    FONT_PATH = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc")
random.seed(24)

RES_X, RES_Y = 2560, 1440
CAM_AZ, CAM_EL = -28.0, 42.0
IX, IY = 2.4, 1.9          # 室内半宽（x）/ 半深（y）
WT, WH = 0.2, 2.5          # 墙厚、墙高
GROUND = -0.40             # 木屋外草地高度（室内地板比地面高 0.4，和岛上木屋一致）
CHAIR_SEAT = 0.37          # 椅面高：B1 打字坐姿下脚踝离地约 6 cm（脚平踩地板）
BED_TOP = 0.52             # 床垫顶面

sc = bpy.context.scene
sc.render.fps = 24
log(f"Blender {bpy.app.version_string}")

# ============================================================ 清场 + 集合
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for it in list(blk):
        if it.users == 0:
            blk.remove(it)

COL = {}
for nm in ("ROOM", "FURN", "PROPS", "BASE", "LIGHTS", "CHARS", "MARKS", "HIDDEN"):
    c = bpy.data.collections.new("CAB_" + nm)
    sc.collection.children.link(c)
    COL[nm] = c

# ============================================================ 材质（和岛屿 v3 相同的函数）
GLOW = []      # (材质, {时段: 强度})
LIGHTS = []    # (灯光物体, {时段: 功率})
SHOW = []      # (物体, {时段集合}) —— 按时段显隐


def lin(rgb):
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


def _new_material(name):
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    m.node_tree.nodes.clear()
    return m


def _sock(sockets, name, typ=None):
    for s in sockets:
        if s.name == name and (typ is None or s.type == typ) and s.enabled:
            return s
    for s in sockets:
        if s.name == name and (typ is None or s.type == typ):
            return s
    raise KeyError(name)


def mix_color(nt, fac, a, b):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    nt.links.new(fac, _sock(m.inputs, "Factor", "VALUE"))
    for sock, val in ((_sock(m.inputs, "A", "RGBA"), a), (_sock(m.inputs, "B", "RGBA"), b)):
        if isinstance(val, tuple):
            sock.default_value = (*val, 1) if len(val) == 3 else val
        else:
            nt.links.new(val, sock)
    return _sock(m.outputs, "Result", "RGBA")


def _set(sockets, name, val):
    try:
        sockets[name].default_value = val
    except (KeyError, TypeError):
        pass


def pbr(name, rgb, var=0.12, scale=3.0, rough=0.82, sss=0.0, spec=0.25, bump=0.0):
    """风格化 PBR（同岛屿 v3）：底色 × 噪声明暗起伏 → 环境光遮蔽 → Principled"""
    m = _new_material(name)
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    bsdf = N.new("ShaderNodeBsdfPrincipled")
    tc = N.new("ShaderNodeTexCoord")
    noise = N.new("ShaderNodeTexNoise")
    _set(noise.inputs, "Scale", scale); _set(noise.inputs, "Detail", 4.0); _set(noise.inputs, "Roughness", 0.6)
    Lk.new(tc.outputs["Object"], noise.inputs["Vector"])
    mr = N.new("ShaderNodeMapRange")
    _set(mr.inputs, "From Min", 0.3); _set(mr.inputs, "From Max", 0.7)
    _set(mr.inputs, "To Min", 1 - var); _set(mr.inputs, "To Max", 1 + var)
    Lk.new(noise.outputs["Fac"], mr.inputs["Value"])
    hs = N.new("ShaderNodeHueSaturation")
    hs.inputs["Color"].default_value = (*lin(rgb), 1)
    Lk.new(mr.outputs["Result"], hs.inputs["Value"])
    ao = N.new("ShaderNodeAmbientOcclusion")
    _set(ao.inputs, "Distance", 0.35)
    Lk.new(hs.outputs["Color"], ao.inputs["Color"])
    Lk.new(ao.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf.inputs, "Roughness", rough)
    _set(bsdf.inputs, "Specular IOR Level", spec)
    if sss:
        _set(bsdf.inputs, "Subsurface Weight", sss)
        _set(bsdf.inputs, "Subsurface Radius", (0.3, 0.5, 0.15))
        _set(bsdf.inputs, "Subsurface Scale", 0.03)
    if bump:
        bp = N.new("ShaderNodeBump")
        _set(bp.inputs, "Strength", bump)
        Lk.new(noise.outputs["Fac"], bp.inputs["Height"])
        Lk.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    Lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    return m


def patch_mat(name, c1, c2, scale=2.6):
    """拼布被面：平面方格（只用 x、y，不随被子起伏变形）"""
    m = _new_material(name)
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    bsdf = N.new("ShaderNodeBsdfPrincipled")
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    com = N.new("ShaderNodeCombineXYZ")
    Lk.new(tc.outputs["Object"], sep.inputs["Vector"])
    Lk.new(sep.outputs["X"], com.inputs["X"]); Lk.new(sep.outputs["Y"], com.inputs["Y"])
    chk = N.new("ShaderNodeTexChecker")
    _set(chk.inputs, "Scale", scale)
    chk.inputs["Color1"].default_value = (*lin(c1), 1)
    chk.inputs["Color2"].default_value = (*lin(c2), 1)
    Lk.new(com.outputs["Vector"], chk.inputs["Vector"])
    ao = N.new("ShaderNodeAmbientOcclusion")
    _set(ao.inputs, "Distance", 0.25)
    Lk.new(chk.outputs["Color"], ao.inputs["Color"])
    Lk.new(ao.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf.inputs, "Roughness", 0.92); _set(bsdf.inputs, "Specular IOR Level", 0.15)
    _set(bsdf.inputs, "Sheen Weight", 0.3)
    Lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*lin(tuple((a + b) / 2 for a, b in zip(c1, c2))), 1)
    return m


def glow(name, rgb, st):
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(rgb), 1)
    em.inputs["Strength"].default_value = st.get("night", 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    m["cab_strengths"] = st
    GLOW.append((m, st))
    return m


def glass_mat(name):
    m = _new_material(name)
    nt = m.node_tree
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf.inputs["Base Color"].default_value = (*lin((0.82, 0.92, 0.98)), 1)
    _set(bsdf.inputs, "Roughness", 0.06); _set(bsdf.inputs, "Alpha", 0.16); _set(bsdf.inputs, "Specular IOR Level", 0.7)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
            break
        except Exception:
            pass
    m.diffuse_color = (*lin((0.70, 0.84, 0.92)), 1)
    return m


def flat(name, rgb):
    """标注用（只在 Workbench 俯视图出现）"""
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(rgb), 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    return m


PAL = {
    # 岛屿原色
    "wood": (0.50, 0.32, 0.19), "wood_dark": (0.36, 0.22, 0.13), "wood_light": (0.76, 0.56, 0.36),
    "stone": (0.68, 0.64, 0.58), "rock": (0.62, 0.62, 0.64), "rock_dark": (0.45, 0.46, 0.50),
    "grass": (0.47, 0.72, 0.28), "grass_dark": (0.30, 0.54, 0.20), "grass_light": (0.62, 0.82, 0.36),
    "cliff": (0.58, 0.46, 0.34), "soil": (0.42, 0.29, 0.20), "moss": (0.38, 0.56, 0.26),
    "leaf": (0.33, 0.60, 0.26), "leaf2": (0.42, 0.68, 0.30), "leaf3": (0.55, 0.76, 0.34),
    "white": (0.97, 0.96, 0.92), "pink": (0.98, 0.56, 0.70), "purple": (0.62, 0.52, 0.92), "yellow": (0.99, 0.84, 0.32),
    "red": (0.88, 0.32, 0.30), "orange": (0.98, 0.62, 0.28),
    "book_red": (0.80, 0.36, 0.34), "book_blue": (0.36, 0.52, 0.78), "book_green": (0.40, 0.62, 0.42),
    "book_purple": (0.52, 0.40, 0.70), "book_mustard": (0.86, 0.66, 0.30), "book_teal": (0.30, 0.58, 0.60),
    "metal": (0.30, 0.30, 0.34), "mug": (0.95, 0.94, 0.90), "pot": (0.78, 0.46, 0.32), "cat": (0.98, 0.66, 0.32),
    "rope": (0.82, 0.72, 0.52), "black": (0.12, 0.10, 0.10),
    # 室内新增
    "plaster": (0.96, 0.90, 0.78), "plaster_cut": (0.86, 0.78, 0.66),
    "wains_a": (0.70, 0.50, 0.32), "wains_b": (0.64, 0.45, 0.28),
    "floor_a": (0.78, 0.58, 0.38), "floor_b": (0.71, 0.51, 0.32), "floor_c": (0.83, 0.64, 0.43),
    "quilt_a": (0.58, 0.72, 0.88), "quilt_b": (0.97, 0.91, 0.80), "throw": (0.42, 0.60, 0.62),
    "sheet": (0.97, 0.96, 0.92), "mattress": (0.95, 0.92, 0.85),
    "curtain": (0.72, 0.66, 0.86), "rug1": (0.80, 0.42, 0.38), "rug2": (0.96, 0.88, 0.72),
    "rug3": (0.40, 0.56, 0.60), "rug4": (0.88, 0.66, 0.36),
    "iron": (0.20, 0.20, 0.23), "brass": (0.86, 0.66, 0.32), "paper": (0.97, 0.94, 0.86), "ink": (0.12, 0.12, 0.22),
    "leather": (0.48, 0.30, 0.20), "straw": (0.86, 0.72, 0.42), "shade": (0.96, 0.78, 0.58),
    "potion_a": (0.55, 0.82, 0.76), "potion_b": (0.84, 0.56, 0.82), "cushion": (0.66, 0.58, 0.86),
    "cat_white": (0.98, 0.95, 0.90), "terracotta": (0.80, 0.48, 0.34),
}
SPEC = {
    "plaster": dict(var=0.06, scale=2.5, rough=0.95, bump=0.05), "plaster_cut": dict(var=0.08, scale=4, rough=0.95),
    "floor_a": dict(var=0.18, scale=5), "floor_b": dict(var=0.18, scale=5), "floor_c": dict(var=0.18, scale=5),
    "wood": dict(var=0.22, scale=6), "wood_dark": dict(var=0.22, scale=6), "wood_light": dict(var=0.2, scale=6),
    "wains_a": dict(var=0.2, scale=6), "wains_b": dict(var=0.2, scale=6),
    "stone": dict(var=0.2, scale=4, bump=0.2), "rock": dict(var=0.22, scale=2.5), "cliff": dict(var=0.25, scale=1.2, rough=0.95),
    "grass": dict(var=0.28, scale=0.6, rough=0.95),
    "leaf": dict(var=0.25, scale=2.5, sss=0.25), "leaf2": dict(var=0.25, scale=2.5, sss=0.25), "leaf3": dict(var=0.2, scale=2.5, sss=0.25),
    "metal": dict(var=0.05, rough=0.35, spec=0.6), "iron": dict(var=0.08, rough=0.45, spec=0.5),
    "brass": dict(var=0.05, rough=0.3, spec=0.8), "mug": dict(var=0.03, rough=0.3, spec=0.5),
    "curtain": dict(var=0.08, scale=8, rough=0.95, sss=0.15), "shade": dict(var=0.05, rough=0.9),
    "sheet": dict(var=0.04, rough=0.95), "mattress": dict(var=0.04, rough=0.95),
    "potion_a": dict(var=0.03, rough=0.15, spec=0.8), "potion_b": dict(var=0.03, rough=0.15, spec=0.8),
}
_MC = {}


def mat(key):
    if key not in _MC:
        _MC[key] = pbr("C_" + key, PAL[key], **SPEC.get(key, {}))
    return _MC[key]


G_BULB = glow("G_desk_bulb", (1.0, 0.82, 0.55), {"dawn": 0, "day": 0, "night": 0, "late": 0})       # 夜里关灯（11-25 用户要求：只留显示器的光）
G_NIGHT = glow("G_night_lamp", (1.0, 0.76, 0.48), {"dawn": 1.2, "day": 0.35, "night": 0, "late": 0})
G_FIRE = glow("G_fire", (1.0, 0.48, 0.14), {"dawn": 1.5, "day": 0.8, "night": 0, "late": 0})
GLASS = glass_mat("C_glass")
QUILT = patch_mat("C_quilt", PAL["quilt_a"], PAL["quilt_b"])

# ============================================================ 几何工具（尺寸写进网格，倒角按米计）


def mk(name, bm, coll, m, loc=(0, 0, 0), rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    coll.objects.link(ob)
    if m is not None:
        me.materials.append(m)
    return ob


def D(sx, sy, sz):
    return Matrix.Diagonal((sx, sy, sz, 1.0))


def bevel(ob, w=0.01, seg=2):
    md = ob.modifiers.new("倒角", "BEVEL")
    md.width = w
    md.segments = seg
    md.limit_method = "ANGLE"
    return ob


def smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def subsurf(ob, lv=1):
    md = ob.modifiers.new("细分", "SUBSURF")
    md.levels = lv
    md.render_levels = lv
    return ob


def box(name, coll, m, loc, size, rot=(0, 0, 0), bv=0.01, seg=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=D(*size))
    ob = mk(name, bm, coll, m, loc, rot)
    if bv > 0:
        bevel(ob, min(bv, 0.3 * min(size)), seg)
    return ob


def cyl(name, coll, m, loc, r, h, seg=16, r2=None, rot=(0, 0, 0), bv=0.0, sm=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    ob = mk(name, bm, coll, m, loc, rot)
    if bv:
        bevel(ob, bv)
    if sm:
        for p in ob.data.polygons:
            p.use_smooth = abs(p.normal.z) < 0.5
    return ob


def sph(name, coll, m, loc, rad, seg=16, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1.0, matrix=D(*rad))
    return smooth(mk(name, bm, coll, m, loc, rot))


def lathe(name, coll, m, loc, prof, seg=24, rot=(0, 0, 0), cap_bot=True, cap_top=True):
    """旋转体。prof = [(半径, 高度), ...] 自下而上"""
    verts, faces = [], []
    n = len(prof)
    for r, z in prof:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for i in range(n - 1):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    if cap_bot and prof[0][0] > 1e-4:
        faces.append(tuple(range(seg))[::-1])
    if cap_top and prof[-1][0] > 1e-4:
        faces.append(tuple(range((n - 1) * seg, n * seg)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = rot
    coll.objects.link(ob)
    me.materials.append(m)
    return smooth(ob)


def prims(name, kind, coll, m, items, seg=8, jitter=0.0, sub=1):
    """很多同材质小件合成一个物体。items = [(位置, 尺寸, 旋转欧拉), ...]"""
    bm = bmesh.new()
    for loc, s, rot in items:
        M = Matrix.Translation(loc) @ Euler(rot).to_matrix().to_4x4() @ D(*s)
        if kind == "cube":
            r = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
        elif kind == "cyl":
            r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=1, radius2=1, depth=1, matrix=M)
        elif kind == "cone":
            r = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=1, radius2=0, depth=1, matrix=M)
        elif kind == "ico":
            r = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0, matrix=M)
        else:
            r = bmesh.ops.create_uvsphere(bm, u_segments=max(seg, 10), v_segments=max(seg // 2, 6), radius=1.0, matrix=M)
        if jitter:
            amp = jitter * min(s)
            for v in r["verts"]:
                v.co += Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1))) * amp
    ob = mk(name, bm, coll, m)
    if kind in ("ico", "sphere"):
        smooth(ob)
    return ob


def boxes(name, coll, m, items, bv=0.0):
    """items = [(中心, 尺寸, 绕 z 角度), ...]"""
    ob = prims(name, "cube", coll, m, [(c, s, (0, 0, rz)) for c, s, rz in items])
    if bv:
        bevel(ob, bv)
    return ob


def tube(name, coll, m, pts, r, smooth_curve=True):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS" if smooth_curve and len(pts) > 2 else "POLY")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    if smooth_curve and len(pts) > 2:
        sp.order_u = 3
        sp.use_endpoint_u = True
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    cu.materials.append(m)
    return ob


def show_at(ob, times):
    SHOW.append((ob, set(times)))
    return ob


def empty(name, loc, coll):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    coll.objects.link(e)
    return e


def parent_keep(ch, par):
    mw = ch.matrix_world.copy()
    ch.parent = par
    ch.matrix_parent_inverse = par.matrix_world.inverted()
    ch.matrix_world = mw


# ============================================================ 门窗位置（北墙 u = x，东墙 u = y）
#            名称       中心u  宽     底     顶
NORTH_OPEN = [("door", -1.55, 0.85, 0.00, 1.95),
              ("win_f2", -0.45, 0.90, 0.95, 1.95),
              ("win_f1", 1.50, 0.95, 1.05, 1.95)]
EAST_OPEN = [("win_l2", -0.55, 0.90, 0.90, 1.95),
             ("win_l1", 0.58, 0.65, 1.10, 1.90)]

# 家具位置（世界坐标）
DESK_C, DESK_W, DESK_D, DESK_TOP = (-0.45, 0.675), 1.00, 0.55, 0.65     # 桌面 0.65：键盘键帽正好在打字手指下面；11-25 往南挪 10 cm，桌子和拉开的椅子之间才站得下
CHAIR_C = (-0.45, 1.55)
BED_X, BED_Y = (0.40, 2.35), (0.70, 1.85)
BED_CY = (BED_Y[0] + BED_Y[1]) / 2
NIGHTSTAND_C = (2.15, 0.44)
COATSTAND_C = (-2.20, 1.62)
STOVE_C = (2.05, -1.45)
RUG_C = (0.15, -0.35)
TRUNK_C = (-1.55, -1.45)


def nwall(u, z, d=0.0):
    """北墙内表面上的点（d = 离开墙面向屋里）"""
    return (u, IY - d, z)


def ewall(u, z, d=0.0):
    return (IX - d, u, z)


# ============================================================ 房间外壳
def wall_solids(u0, u1, ops):
    items, cur = [], u0
    for (_, c, w, z0, z1) in sorted(ops, key=lambda o: o[1]):
        a, b = c - w / 2, c + w / 2
        if a > cur + 1e-4:
            items.append((cur, a, 0.0, WH))
        if z0 > 1e-4:
            items.append((cur if False else a, b, 0.0, z0))
        if z1 < WH - 1e-4:
            items.append((a, b, z1, WH))
        cur = b
    if cur < u1 - 1e-4:
        items.append((cur, u1, 0.0, WH))
    return items


def build_shell():
    C = COL["ROOM"]
    # --- 地板：逐块木板，三种深浅
    rows = 20
    pw = 2 * IY / rows
    groups = {"floor_a": [], "floor_b": [], "floor_c": []}
    for r in range(rows):
        y = -IY + pw * (r + 0.5)
        x = -IX
        L0 = random.uniform(0.3, 1.4)
        while x < IX - 1e-3:
            L = L0 if x == -IX else random.uniform(1.2, 2.3)
            x2 = min(IX, x + L)
            if IX - x2 < 0.3:
                x2 = IX
            groups[random.choice(list(groups))].append((((x + x2) / 2, y, -0.02), (x2 - x - 0.006, pw - 0.006, 0.04), 0.0))
            x = x2
    for k, it in groups.items():
        boxes("cab_floor_" + k, C, mat(k), it, bv=0.003)
    box("cab_subfloor", C, mat("wood_dark"), (0, 0, -0.10), (2 * IX + 2 * WT, 2 * IY + 2 * WT, 0.12), bv=0.0)
    # 地板下的托梁端头（切面上看得到）
    joists = [((x, -IY - WT / 2, -0.10), (0.10, WT + 0.04, 0.16), 0.0) for x in [-2.2 + 0.55 * k for k in range(9)]]
    joists += [((-IX - WT / 2, y, -0.10), (WT + 0.04, 0.10, 0.16), 0.0) for y in [-1.7 + 0.55 * k for k in range(7)]]
    boxes("cab_joist_ends", C, mat("wood"), joists, bv=0.008)

    # --- 北墙 / 东墙（灰泥 + 门窗洞）
    nitems = wall_solids(-IX - WT, IX + WT, NORTH_OPEN)
    boxes("cab_wall_N", C, mat("plaster"), [(((a + b) / 2, IY + WT / 2, (z0 + z1) / 2), (b - a, WT, z1 - z0), 0.0)
                                             for a, b, z0, z1 in nitems])
    eitems = wall_solids(-IY - WT, IY, EAST_OPEN)
    boxes("cab_wall_E", C, mat("plaster"), [((IX + WT / 2, (a + b) / 2, (z0 + z1) / 2), (WT, b - a, z1 - z0), 0.0)
                                             for a, b, z0, z1 in eitems])

    # --- 墙裙：竖木板到 0.88 m（门洞处断开）
    door = NORTH_OPEN[0]
    da, db = door[1] - door[2] / 2 - 0.07, door[1] + door[2] / 2 + 0.07
    wa, wb = [], []
    u = -IX
    k = 0
    while u < IX - 1e-3:
        u2 = min(IX, u + 0.115)
        if not (u2 > da and u < db):
            (wa if k % 2 == 0 else wb).append((((u + u2) / 2, IY - 0.011, 0.44), (u2 - u - 0.004, 0.022, 0.88), 0.0))
        u, k = u2, k + 1
    u, k = -IY, 0
    while u < IY - 1e-3:
        u2 = min(IY, u + 0.115)
        (wa if k % 2 == 0 else wb).append(((IX - 0.011, (u + u2) / 2, 0.44), (0.022, u2 - u - 0.004, 0.88), 0.0))
        u, k = u2, k + 1
    boxes("cab_wains_a", C, mat("wains_a"), wa, bv=0.004)
    boxes("cab_wains_b", C, mat("wains_b"), wb, bv=0.004)
    cap = [(((-IX + da) / 2, IY - 0.03, 0.905), (da + IX, 0.06, 0.05), 0.0),
           (((db + IX) / 2, IY - 0.03, 0.905), (IX - db, 0.06, 0.05), 0.0),
           ((IX - 0.03, 0.0, 0.905), (0.06, 2 * IY, 0.05), 0.0)]
    boxes("cab_wains_cap", C, mat("wood"), cap, bv=0.012)

    # --- 半木结构：顶梁、窗头横梁、立柱
    T = []
    T.append(((0.0, IY - 0.035, 2.43), (2 * IX, 0.07, 0.14), 0.0))                 # 北墙顶梁
    T.append(((IX - 0.035, 0.0, 2.43), (0.07, 2 * IY, 0.14), 0.0))                 # 东墙顶梁
    T.append(((0.0, IY - 0.03, 2.0), (2 * IX, 0.06, 0.10), 0.0))                   # 窗头横梁（兼过梁）
    T.append(((IX - 0.03, 0.0, 2.0), (0.06, 2 * IY, 0.10), 0.0))
    T.append(((IX - 0.06, IY - 0.06, WH / 2), (0.14, 0.14, WH), 0.0))              # 远角立柱
    for (_, c, w, z0, z1) in NORTH_OPEN:
        for uu in (c - w / 2 - 0.05, c + w / 2 + 0.05):
            T.append(((uu, IY - 0.03, (0.93 + 2.36) / 2 if z0 > 0 else 1.18), (0.08, 0.06, 2.36 - 0.93 if z0 > 0 else 2.36), 0.0))
    for (_, c, w, z0, z1) in EAST_OPEN:
        for uu in (c - w / 2 - 0.05, c + w / 2 + 0.05):
            T.append(((IX - 0.03, uu, (0.93 + 2.36) / 2), (0.06, 0.08, 2.36 - 0.93), 0.0))
    boxes("cab_timber", C, mat("wood_dark"), T, bv=0.01)
    # 两面墙在切口处的端柱（像木屋外墙角柱）
    box("cab_post_NW", C, mat("wood_dark"), (-IX - WT / 2, IY + WT / 2, WH / 2), (WT + 0.02, WT + 0.02, WH), bv=0.015)
    box("cab_post_SE", C, mat("wood_dark"), (IX + WT / 2, -IY - WT / 2, WH / 2), (WT + 0.02, WT + 0.02, WH), bv=0.015)
    # 墙体切面顶（墙厚上沿）
    boxes("cab_wall_top", C, mat("wood"), [((0.0, IY + WT / 2, WH + 0.02), (2 * IX + 2 * WT, WT + 0.04, 0.04), 0.0),
                                            ((IX + WT / 2, -0.1, WH + 0.02), (WT + 0.04, 2 * IY + WT, 0.04), 0.0)], bv=0.008)

    # --- 近处两面墙切到地板以上 0.24 m（木地梁 + 灰泥切面）
    stub = [((-0.1, -IY - WT / 2, 0.0), (2 * IX + WT, WT, 0.20), 0.0),
            ((-IX - WT / 2, 0.0, 0.0), (WT, 2 * IY, 0.20), 0.0)]
    boxes("cab_stub_sill", C, mat("wood_dark"), stub, bv=0.012)
    cut = [((-0.1, -IY - WT / 2, 0.16), (2 * IX + WT - 0.02, WT - 0.04, 0.10), 0.0),
           ((-IX - WT / 2, 0.0, 0.16), (WT - 0.04, 2 * IY - 0.02, 0.10), 0.0)]
    boxes("cab_stub_cut", C, mat("plaster_cut"), cut, bv=0.01)

    # --- 只投影、镜头看不见的屋顶和近墙：阳光只能从窗户进来
    H = COL["HIDDEN"]
    sb = [((0, 0, WH + 0.05), (2 * IX + 2 * WT, 2 * IY + 2 * WT, 0.06), 0.0),
          ((0, -IY - WT / 2, WH / 2), (2 * IX + 2 * WT, WT, WH), 0.0),
          ((-IX - WT / 2, 0, WH / 2), (WT, 2 * IY + 2 * WT, WH), 0.0)]
    o = boxes("cab_shadow_box", H, mat("plaster"), sb)
    o.visible_camera = False
    for a in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        try:
            setattr(o, a, False)
        except Exception:
            pass

    # --- 石砌地基（一圈不规则石块）
    st = []
    W2, D2 = IX + WT, IY + WT
    for side, (ax, ay, bx, by) in enumerate(((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1))):
        n = 12 if side % 2 == 0 else 10
        for i in range(n):
            t = (i + 0.5) / n
            px = (ax + (bx - ax) * t) * (W2 + 0.06)
            py = (ay + (by - ay) * t) * (D2 + 0.06)
            for lvl in range(2):
                st.append(((px + random.uniform(-0.04, 0.04), py + random.uniform(-0.04, 0.04), GROUND + 0.07 + lvl * 0.13),
                           (0.24 + random.uniform(0, 0.1), 0.2 + random.uniform(0, 0.08), 0.085), (0, 0, random.uniform(0, 3))))
    prims("cab_foundation", "ico", C, mat("stone"), st, jitter=0.25)
    box("cab_foundation_core", C, mat("rock_dark"), (0, 0, (GROUND - 0.16) / 2), (2 * W2, 2 * D2, -GROUND - 0.16 + 0.02), bv=0.0)


def build_door():
    C = COL["ROOM"]
    _, c, w, z0, z1 = NORTH_OPEN[0]
    a, b = c - w / 2, c + w / 2
    yc = IY + WT / 2
    # 门框（贴脸）
    boxes("cab_door_trim", C, mat("wood_dark"),
          [((a - 0.035, IY - 0.015, z1 / 2), (0.07, 0.05, z1), 0.0), ((b + 0.035, IY - 0.015, z1 / 2), (0.07, 0.05, z1), 0.0)], bv=0.01)
    # 门板：竖木板（门向外开，白模是关着的）
    pl = []
    n = 5
    for k in range(n):
        u0 = a + w * k / n
        pl.append((((u0 + w / n / 2), yc, z1 / 2), (w / n - 0.008, 0.045, z1 - 0.01), 0.0))
    boxes("cab_door_planks", C, mat("wood"), pl, bv=0.006)
    yi = yc - 0.0225 - 0.014
    bat = [((c, yi, 0.34), (w - 0.10, 0.028, 0.13), 0.0), ((c, yi, 1.62), (w - 0.10, 0.028, 0.13), 0.0)]
    boxes("cab_door_battens", C, mat("wood_light"), bat, bv=0.008)
    L = math.hypot(w - 0.2, 1.62 - 0.34 - 0.13)
    ang = math.atan2(1.62 - 0.34 - 0.13, w - 0.2)
    box("cab_door_brace", C, mat("wood_light"), (c, yi, 0.98), (L, 0.026, 0.11), rot=(0, -ang, 0), bv=0.008)
    hinges = [((a + 0.18, yi - 0.016, z), (0.34, 0.008, 0.045), 0.0) for z in (0.34, 1.62)]
    boxes("cab_door_hinges", C, mat("iron"), hinges, bv=0.003)
    cyl("cab_door_latch", C, mat("iron"), (b - 0.13, yi - 0.03, 1.0), 0.045, 0.012, seg=16, rot=(math.pi / 2, 0, 0))
    lathe("cab_door_ring", C, mat("iron"), (b - 0.13, yi - 0.05, 0.94), [(0.035, -0.006), (0.042, 0), (0.035, 0.006)],
          seg=20, rot=(math.pi / 2, 0, 0), cap_bot=False, cap_top=False)
    # 门垫
    box("cab_doormat", COL["PROPS"], mat("straw"), (c, IY - 0.42, 0.008), (0.75, 0.45, 0.016), bv=0.006)


def build_window(nm, wall, c, w, z0, z1):
    C = COL["ROOM"]
    h = z1 - z0
    if wall == "N":
        P = lambda u, z, d: (u, IY - d, z)
        S3 = lambda su, sd, sz: (su, sd, sz)
    else:
        P = lambda u, z, d: (IX - d, u, z)
        S3 = lambda su, sd, sz: (sd, su, sz)
    mid = -WT / 2       # 墙厚中线（d 为负 = 往墙里）
    fr = []
    zc = (z0 + z1) / 2
    for zz in (z0 + 0.025, z1 - 0.025):
        fr.append((P(c, zz, mid), S3(w, 0.07, 0.05), 0.0))
    for uu in (c - w / 2 + 0.025, c + w / 2 - 0.025):
        fr.append((P(uu, zc, mid), S3(0.05, 0.07, h), 0.0))
    fr.append((P(c, zc, mid), S3(0.032, 0.05, h), 0.0))                 # 竖棂
    fr.append((P(c, z0 + h * 0.62, mid), S3(w, 0.05, 0.03), 0.0))        # 横棂
    boxes(f"cab_{nm}_frame", C, mat("wood_dark"), fr, bv=0.006)
    g = box(f"cab_{nm}_glass", C, GLASS, P(c, zc, mid - 0.012), S3(w - 0.04, 0.006, h - 0.04), bv=0.0)
    g.visible_shadow = False
    # 贴脸 + 窗台板
    tr = [(P(c - w / 2 - 0.035, zc, 0.015), S3(0.07, 0.05, h), 0.0), (P(c + w / 2 + 0.035, zc, 0.015), S3(0.07, 0.05, h), 0.0)]
    boxes(f"cab_{nm}_trim", C, mat("wood_dark"), tr, bv=0.01)
    box(f"cab_{nm}_sill", C, mat("wood_light"), P(c, z0 - 0.015, 0.02), S3(w + 0.20, 0.13, 0.035), bv=0.01)
    # 窗帘杆 + 两种窗帘（开 / 合）
    rod_z = z1 + 0.12
    ua, ub = c - w / 2 - 0.16, c + w / 2 + 0.16
    tube(f"cab_{nm}_rod", C, mat("brass"), [P(ua, rod_z, 0.07), P(ub, rod_z, 0.07)], 0.012, smooth_curve=False)
    for uu in (ua, ub):
        sph(f"cab_{nm}_finial", C, mat("brass"), P(uu, rod_z, 0.07), (0.025, 0.025, 0.025), seg=12)
    bot = z0 - 0.06
    curtain(f"cab_{nm}_cur_open", wall, P, ua, ub, rod_z - 0.02, bot, "open", c)
    curtain(f"cab_{nm}_cur_closed", wall, P, ua, ub, rod_z - 0.02, bot, "closed", c, gap=0.025)
    curtain(f"cab_{nm}_cur_gap", wall, P, ua, ub, rod_z - 0.02, bot, "closed", c, gap=0.10)


def curtain(name, wall, P, ua, ub, ztop, zbot, state, c, gap=0.0):
    nu, nz = 26, 12
    coll = COL["ROOM"]
    pieces = []
    for side in (-1, 1):
        verts, faces = [], []
        for j in range(nz + 1):
            t = j / nz
            z = ztop + (zbot - ztop) * t
            if state == "open":
                # 系在两侧：上宽、系带处收窄、下摆散开
                tie = 0.55
                wdt = 0.24 + (0.10 - 0.24) * (t / tie) if t < tie else 0.10 + (0.19 - 0.10) * ((t - tie) / (1 - tie))
                if side < 0:
                    a, b = ua - 0.02, ua - 0.02 + wdt
                else:
                    a, b = ub + 0.02 - wdt, ub + 0.02
                folds, amp = 3, 0.03
            else:
                a, b = (ua, c - gap / 2) if side < 0 else (c + gap / 2, ub)
                folds, amp = 5, 0.022
            for i in range(nu + 1):
                s = i / nu
                u = a + (b - a) * s
                d = 0.07 + amp * math.sin(2 * math.pi * folds * s + side) * (0.8 + 0.2 * t)
                verts.append(P(u, z, d))
        for j in range(nz):
            for i in range(nu):
                k = j * (nu + 1) + i
                faces.append((k, k + 1, k + nu + 2, k + nu + 1))
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update()
        ob = bpy.data.objects.new(f"{name}_{'L' if side < 0 else 'R'}", me)
        coll.objects.link(ob)
        me.materials.append(mat("curtain"))
        sd = ob.modifiers.new("厚度", "SOLIDIFY")
        sd.thickness = 0.01
        smooth(ob)
        pieces.append(ob)
    return pieces


# ============================================================ 家具
def books_row(prefix, coll, x0, x1, y, z, depth=0.16, wall="N", lean_last=True):
    """一排立着的书（沿墙方向），返回已用到的位置"""
    cols = ["book_red", "book_blue", "book_green", "book_purple", "book_mustard", "book_teal"]
    covers = {k: [] for k in cols}
    pages = []
    u = x0
    while u < x1 - 0.03:
        t = random.uniform(0.025, 0.05)
        hh = random.uniform(0.15, 0.22)
        if u + t > x1:
            break
        cx = u + t / 2
        k = random.choice(cols)
        if wall == "N":
            covers[k].append(((cx, y, z + hh / 2), (t, depth, hh), (0, 0, 0)))
            pages.append(((cx, y - 0.006, z + hh / 2), (t - 0.008, depth, hh - 0.012), (0, 0, 0)))
        u += t + 0.003
    for k, it in covers.items():
        if it:
            prims(f"{prefix}_cov_{k}", "cube", coll, mat(k), it)
    prims(f"{prefix}_pages", "cube", coll, mat("paper"), pages)


def book(prefix, coll, loc, size, rz=0.0, color="book_red", open_=False):
    w, d, t = size
    if open_:
        box(prefix + "_cover", coll, mat(color), (loc[0], loc[1], loc[2] + 0.004), (w + 0.02, d + 0.02, 0.008), rot=(0, 0, rz), bv=0.002)
        for s in (-1, 1):
            o = box(prefix + f"_page{s}", coll, mat("paper"), (loc[0] + s * w / 4 * math.cos(rz), loc[1] + s * w / 4 * math.sin(rz), loc[2] + 0.016),
                    (w / 2 - 0.004, d, 0.012), rot=(0, -s * 0.07, rz), bv=0.003)
    else:
        box(prefix + "_cover", coll, mat(color), (loc[0], loc[1], loc[2] + t / 2), (w, d, t), rot=(0, 0, rz), bv=0.003)
        box(prefix + "_pages", coll, mat("paper"), (loc[0] + 0.004, loc[1], loc[2] + t / 2), (w - 0.006, d - 0.01, t - 0.008), rot=(0, 0, rz), bv=0.0)


def build_desk():
    F, P = COL["FURN"], COL["PROPS"]
    cx, cy = DESK_C
    W, Dp, top = DESK_W, DESK_D, DESK_TOP
    box("cab_desk_top", F, mat("wood_light"), (cx, cy, top - 0.02), (W, Dp, 0.04), bv=0.012)
    box("cab_desk_apron", F, mat("wood"), (cx, cy, top - 0.085), (W - 0.08, Dp - 0.08, 0.09), bv=0.008)
    prof = [(0.028, 0), (0.022, 0.06), (0.026, 0.1), (0.02, 0.3), (0.024, 0.5), (0.03, 0.55), (0.03, top - 0.13)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            lathe("cab_desk_leg", F, mat("wood"), (cx + sx * (W / 2 - 0.05), cy + sy * (Dp / 2 - 0.05), 0), prof, seg=12)
    # 朝镜头一侧的两个抽屉面
    for sx in (-1, 1):
        box("cab_desk_drawer", F, mat("wood_light"), (cx + sx * 0.22, cy - Dp / 2 + 0.035, top - 0.085), (0.36, 0.012, 0.07), bv=0.004)
        sph("cab_desk_knob", F, mat("brass"), (cx + sx * 0.22, cy - Dp / 2 + 0.025, top - 0.085), (0.014, 0.014, 0.014), seg=10)
    box("cab_desk_shelf", F, mat("wood"), (cx, cy, 0.12), (W - 0.12, Dp - 0.12, 0.025), bv=0.005)
    # 桌上：显示器（桌子远端正中，屏幕朝她）、键盘（B1 里按手的位置摆）、台灯（左后）、一摞书（右后）、笔记本、马克杯（右前）
    lx, ly = LAMP_XY
    lathe("cab_lamp_base", P, mat("brass"), (lx, ly, top), [(0.075, 0), (0.075, 0.012), (0.05, 0.03), (0.016, 0.04)], seg=24)
    cyl("cab_lamp_stem", P, mat("brass"), (lx, ly, top + 0.19), 0.011, 0.31, seg=10)
    lathe("cab_lamp_shade", P, mat("shade"), (lx, ly, top + 0.30),
          [(0.135, 0.0), (0.12, 0.04), (0.085, 0.10), (0.05, 0.135), (0.0, 0.14)], seg=28, cap_bot=False)
    sh = bpy.data.objects["cab_lamp_shade"]
    sh.modifiers.new("厚度", "SOLIDIFY").thickness = 0.006
    sph("cab_lamp_bulb", P, G_BULB, (lx, ly, top + 0.355), (0.028, 0.028, 0.034), seg=14)
    for i, (col, th) in enumerate((("book_red", 0.035), ("book_green", 0.03), ("book_mustard", 0.04))):
        z = top + sum(t for _, t in (("", 0.035), ("", 0.03), ("", 0.04))[:i])
        book(f"cab_stack{i}", P, (cx + 0.38, cy - 0.15, z), (0.20 - i * 0.015, 0.15, th), rz=0.15 * (i - 1), color=col)
    box("cab_notebook", P, mat("paper"), (cx + 0.37, cy + 0.06, top + 0.006), (0.16, 0.21, 0.012), rot=(0, 0, 0.30), bv=0.003)
    tube("cab_pencil", P, mat("mustard") if "mustard" in PAL else mat("wood_light"),
         [(cx + 0.31, cy + 0.02, top + 0.016), (cx + 0.42, cy + 0.10, top + 0.016)], 0.0035)
    mx_ = cx + 0.40
    lathe("cab_mug", P, mat("mug"), (mx_, cy + 0.20, top), [(0.035, 0), (0.038, 0.01), (0.038, 0.085), (0.033, 0.085), (0.031, 0.015)], seg=20)
    tube("cab_mug_handle", P, mat("mug"), [(mx_ + 0.036, cy + 0.20, top + 0.07), (mx_ + 0.065, cy + 0.20, top + 0.055),
                                          (mx_ + 0.036, cy + 0.20, top + 0.02)], 0.006)
    build_monitor(P, top)
    build_keyboard(P, (cx, cy + 0.15), 0.44, top)


MON_C = (DESK_C[0] + 0.02, DESK_C[1] - 0.14)       # 显示器底座中心（桌子远端，离她约 0.5 m）
MON_W, MON_H, MON_Z0 = 0.52, 0.31, 0.12             # 屏幕宽 / 高 / 屏幕下沿离桌面
LAMP_XY = (DESK_C[0] - 0.40, DESK_C[1] - 0.12)       # 台灯挪到左后角，给键盘和手让位
G_SCREEN = glow("G_screen", (1.0, 0.84, 0.62), {"dawn": 0, "day": 1.2, "night": 2.6, "late": 2.6})        # 暖色屏幕（护眼模式）；睡觉时也开着（11-25 用户要求）
G_SCREEN_UI = glow("G_screen_ui", (1.0, 0.70, 0.42), {"dawn": 0, "day": 1.0, "night": 2.0, "late": 2.0})


def build_monitor(P, top):
    """原创显示器：椭圆底座 + 立柱 + 窄边框屏幕；屏幕朝 +y（朝坐着的她），发冷白光"""
    cx, cy = MON_C
    zc = top + MON_Z0 + MON_H / 2
    cyl("cab_mon_base", P, mat("ink"), (cx, cy - 0.02, top + 0.008), 0.11, 0.016, seg=28)
    bpy.data.objects["cab_mon_base"].scale = (1.0, 0.72, 1.0)
    box("cab_mon_neck", P, mat("ink"), (cx, cy - 0.04, top + 0.10), (0.05, 0.022, 0.19), rot=(0.12, 0, 0), bv=0.006)
    box("cab_mon_body", P, mat("ink"), (cx, cy, zc), (MON_W + 0.02, 0.024, MON_H + 0.02), rot=(0.10, 0, 0), bv=0.008)
    scr = box("cab_mon_screen", P, G_SCREEN, (cx, cy + 0.0125, zc), (MON_W - 0.01, 0.002, MON_H - 0.01), rot=(0.10, 0, 0), bv=0.0)
    show_at(scr, ("night", "day", "late", "wb"))
    off = box("cab_mon_screen_off", P, mat("ink"), (cx, cy + 0.0125, zc), (MON_W - 0.01, 0.002, MON_H - 0.01), rot=(0.10, 0, 0), bv=0.0)
    show_at(off, ("dawn",))
    # 屏幕上的界面：几块浅色窗口条（不写任何文字）
    for i, (u, v, w, h) in enumerate(((-0.13, 0.06, 0.20, 0.10), (0.10, 0.07, 0.22, 0.08), (-0.05, -0.07, 0.36, 0.06))):
        ui = box(f"cab_mon_ui{i}", P, G_SCREEN_UI, (cx + u, cy + 0.0145 - v * math.sin(0.10), zc + v * math.cos(0.10)),
                 (w, 0.001, h), rot=(-0.10, 0, 0), bv=0.0)
        show_at(ui, ("night", "day", "late", "wb"))


def build_keyboard(P, c, w, top, d=0.15, h=0.022):
    """键盘：底板 + 一格格键帽（B1 会按手的位置重摆）"""
    cx, cy = c
    box("cab_kb_base", P, mat("ink"), (cx, cy, top + h * 0.45), (w, d, h * 0.9), bv=0.006)
    keys = []
    rows, cols = 5, max(10, int(w / 0.03))
    kw, kd = (w - 0.03) / cols, (d - 0.03) / rows
    for r_ in range(rows):
        for c_ in range(cols):
            keys.append(((cx - w / 2 + 0.015 + kw * (c_ + 0.5), cy - d / 2 + 0.015 + kd * (r_ + 0.5), top + h * 0.9 + 0.004), (kw * 0.82, kd * 0.82, 0.008), 0.0))
    boxes("cab_kb_keys", P, mat("iron"), keys, bv=0.0015)          # 深灰键帽，屏幕光一照不会白得发亮


def build_chair():
    F = COL["FURN"]
    cx, cy = CHAIR_C
    s = CHAIR_SEAT
    box("cab_chair_seat", F, mat("wood_light"), (cx, cy, s - 0.02), (0.42, 0.40, 0.04), bv=0.012)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lathe("cab_chair_leg", F, mat("wood"), (cx + sx * 0.17, cy + sy * 0.16, 0),
                  [(0.02, 0), (0.016, 0.1), (0.02, 0.2), (0.018, s - 0.04)], seg=10)
    st = [((cx, cy + sy * 0.16, 0.14), (0.34, 0.022, 0.022), 0.0) for sy in (-1, 1)]
    boxes("cab_chair_stretch", F, mat("wood"), st, bv=0.005)
    # 靠背在 +y（她面朝 −y 坐）
    by = cy + 0.18
    for sx in (-1, 1):
        cyl("cab_chair_post", F, mat("wood"), (cx + sx * 0.17, by, s + 0.24), 0.018, 0.48, seg=10)
    box("cab_chair_rail", F, mat("wood_light"), (cx, by, s + 0.46), (0.40, 0.035, 0.07), bv=0.012)
    for k in range(4):
        cyl("cab_chair_spindle", F, mat("wood"), (cx - 0.105 + k * 0.07, by, s + 0.22), 0.009, 0.42, seg=8)
    box("cab_chair_cushion", F, mat("cushion"), (cx, cy - 0.01, s + 0.018), (0.36, 0.34, 0.035), bv=0.015, seg=3)


def build_wall_shelf():
    P, F = COL["PROPS"], COL["FURN"]
    x0, x1, z = -0.98, 0.08, 2.14
    box("cab_shelf_board", F, mat("wood_light"), ((x0 + x1) / 2, IY - 0.11, z), (x1 - x0, 0.21, 0.03), bv=0.008)
    for xx in (x0 + 0.1, x1 - 0.1):
        box("cab_shelf_bracket", F, mat("wood_dark"), (xx, IY - 0.07, z - 0.08), (0.03, 0.12, 0.13), bv=0.006)
    books_row("cab_shelf_books", P, x0 + 0.03, x0 + 0.62, IY - 0.10, z + 0.015)
    for i, (xx, col) in enumerate(((x0 + 0.72, "potion_a"), (x0 + 0.84, "potion_b"))):
        lathe(f"cab_jar{i}", P, mat(col), (xx, IY - 0.10, z + 0.015),
              [(0.035, 0), (0.042, 0.02), (0.042, 0.10), (0.02, 0.13), (0.02, 0.15), (0, 0.15)], seg=16)
        cyl(f"cab_jar_cork{i}", P, mat("wood_light"), (xx, IY - 0.10, z + 0.175), 0.022, 0.03, seg=10)
    lathe("cab_shelf_pot", P, mat("terracotta"), (x1 - 0.08, IY - 0.10, z + 0.015), [(0.04, 0), (0.05, 0.07), (0.052, 0.08), (0.0, 0.08)], seg=14)
    prims("cab_shelf_plant", "ico", P, mat("leaf2"),
          [((x1 - 0.08 + random.uniform(-0.04, 0.04), IY - 0.10 + random.uniform(-0.03, 0.03), z + 0.11 + random.uniform(0, 0.05)),
            (0.04, 0.04, 0.035), (0, 0, 0)) for _ in range(7)], jitter=0.2)
    # 窗台小物
    lathe("cab_cactus_pot", P, mat("terracotta"), (-0.78, IY - 0.04, 0.95 + 0.02), [(0.035, 0), (0.045, 0.06), (0, 0.06)], seg=14)
    sph("cab_cactus", P, mat("leaf"), (-0.78, IY - 0.04, 0.95 + 0.11), (0.03, 0.03, 0.05), seg=12)


def quilt_surface(name, lump, coll):
    """被子：网格曲面。lump=True 时中间鼓起一个人形（仰躺），床靠墙一侧塞进去，靠屋里一侧垂下来"""
    x0, x1 = BED_X[0] + 0.07, BED_X[1] - 0.36
    ny, nx = 26, 36
    top0 = BED_TOP + 0.035
    yc = BED_CY

    def bump(x, y):
        if not lump:
            return 0.0
        prof = [(x0, 0.10), (x0 + 0.12, 0.17), (x0 + 0.40, 0.10), (x0 + 0.62, 0.12), (x0 + 0.78, 0.15), (x0 + 1.05, 0.19), (x1 - 0.12, 0.27), (x1 + 0.02, 0.27)]
        h = prof[-1][1]
        for (xa, ha), (xb, hb) in zip(prof, prof[1:]):
            if xa <= x <= xb:
                h = ha + (hb - ha) * (x - xa) / (xb - xa)
                break
        return h * math.exp(-((y - yc) / 0.27) ** 4)

    verts, faces, mats = [], [], []
    # v: 0..1 跨床宽；前 22% 是垂下来的部分
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        for j in range(ny + 1):
            v = j / ny
            if v < 0.22:
                s = 1 - v / 0.22
                y = BED_Y[0] + 0.05 - 0.07 * math.sin(s * math.pi / 2)
                z = top0 - 0.24 * s
            else:
                y = BED_Y[0] + 0.05 + (BED_Y[1] - 0.03 - BED_Y[0] - 0.05) * (v - 0.22) / 0.78
                z = top0 + bump(x, y)
            z += 0.006 * math.sin(x * 23 + y * 7) * math.sin(y * 17)
            verts.append((x, y, z))
    for i in range(nx):
        for j in range(ny):
            k = i * (ny + 1) + j
            faces.append((k, k + ny + 1, k + ny + 2, k + 1))
            xm = x0 + (x1 - x0) * (i + 0.5) / nx
            mats.append(1 if xm > x1 - 0.10 else (2 if xm < x0 + 0.24 else 0))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    for p, mi in zip(me.polygons, mats):
        p.material_index = mi
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    for m in (QUILT, mat("sheet"), mat("throw")):
        me.materials.append(m)
    sd = ob.modifiers.new("厚度", "SOLIDIFY")
    sd.thickness = 0.03
    sd.offset = 1.0
    subsurf(ob, 1)
    smooth(ob)
    return ob


def build_bed():
    F, P = COL["FURN"], COL["PROPS"]
    xa, xb = BED_X
    ya, yb = BED_Y
    # 床腿 / 床头 / 床尾
    for yy in (ya + 0.035, yb - 0.035):
        box("cab_bed_headpost", F, mat("wood"), (xb - 0.04, yy, 0.53), (0.07, 0.07, 1.06), bv=0.012)
        sph("cab_bed_headknob", F, mat("wood_light"), (xb - 0.04, yy, 1.10), (0.045, 0.045, 0.04), seg=14)
        box("cab_bed_footpost", F, mat("wood"), (xa + 0.035, yy, 0.37), (0.07, 0.07, 0.74), bv=0.012)
        sph("cab_bed_footknob", F, mat("wood_light"), (xa + 0.035, yy, 0.775), (0.04, 0.04, 0.035), seg=14)
    box("cab_bed_headpanel", F, mat("wood_light"), (xb - 0.04, BED_CY, 0.70), (0.035, yb - ya - 0.10, 0.52), bv=0.01)
    box("cab_bed_headrail", F, mat("wood"), (xb - 0.04, BED_CY, 0.99), (0.06, yb - ya - 0.06, 0.07), bv=0.015)
    box("cab_bed_footpanel", F, mat("wood_light"), (xa + 0.035, BED_CY, 0.52), (0.03, yb - ya - 0.10, 0.30), bv=0.01)
    box("cab_bed_footrail", F, mat("wood"), (xa + 0.035, BED_CY, 0.69), (0.055, yb - ya - 0.06, 0.06), bv=0.012)
    for yy in (ya + 0.035, yb - 0.035):
        box("cab_bed_siderail", F, mat("wood"), ((xa + xb) / 2, yy, 0.28), (xb - xa - 0.1, 0.05, 0.12), bv=0.01)
    box("cab_mattress", F, mat("mattress"), ((xa + xb) / 2 + 0.0, BED_CY, BED_TOP - 0.09), (xb - xa - 0.14, yb - ya - 0.07, 0.18), bv=0.05, seg=3)
    # 枕头 + 靠垫
    p = box("cab_pillow", P, mat("sheet"), (xb - 0.25, BED_CY, BED_TOP + 0.065), (0.34, 0.62, 0.13), bv=0.05, seg=3)
    subsurf(p, 1); smooth(p)
    show_at(p, ("night", "day"))       # 睡觉时段换成被头压出凹陷的枕头（见 build_sleep）
    p = box("cab_cushion_bed", P, mat("cushion"), (xb - 0.13, yb - 0.25, BED_TOP + 0.20), (0.10, 0.32, 0.30),
            rot=(0, -0.35, 0), bv=0.04, seg=3)
    subsurf(p, 1); smooth(p)
    show_at(quilt_surface("cab_quilt_flat", False, P), ("night", "day"))


def build_nightstand():
    F, P = COL["FURN"], COL["PROPS"]
    x, y = NIGHTSTAND_C
    box("cab_ns_body", F, mat("wood"), (x, y, 0.27), (0.40, 0.40, 0.46), bv=0.012)
    box("cab_ns_top", F, mat("wood_light"), (x, y, 0.515), (0.44, 0.44, 0.03), bv=0.01)
    box("cab_ns_drawer", F, mat("wood_light"), (x - 0.205, y, 0.38), (0.012, 0.32, 0.13), bv=0.004)
    sph("cab_ns_knob", F, mat("brass"), (x - 0.215, y, 0.38), (0.014, 0.014, 0.014), seg=10)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("cab_ns_leg", F, mat("wood_dark"), (x + sx * 0.17, y + sy * 0.17, 0.02), (0.05, 0.05, 0.04), bv=0.008)
    # 蘑菇小夜灯 + 闹钟 + 书
    book("cab_ns_book", P, (x + 0.02, y + 0.06, 0.53), (0.18, 0.13, 0.03), rz=0.3, color="book_purple")
    lathe("cab_nl_stem", P, mat("mattress"), (x + 0.05, y + 0.08, 0.56), [(0.03, 0), (0.022, 0.03), (0.018, 0.10), (0.02, 0.12)], seg=16)
    lathe("cab_nl_cap", P, G_NIGHT, (x + 0.05, y + 0.08, 0.675), [(0.0, 0.0), (0.085, 0.0), (0.082, 0.02), (0.065, 0.06), (0.035, 0.085), (0.0, 0.092)], seg=24)
    cyl("cab_clock_body", P, mat("red"), (x - 0.08, y - 0.10, 0.60), 0.045, 0.035, seg=20, rot=(0, math.pi / 2, 0))
    cyl("cab_clock_face", P, mat("white"), (x - 0.099, y - 0.10, 0.60), 0.036, 0.004, seg=20, rot=(0, math.pi / 2, 0))
    for s in (-1, 1):
        sph("cab_clock_bell", P, mat("brass"), (x - 0.08, y - 0.10 + s * 0.028, 0.648), (0.018, 0.018, 0.014), seg=10)


def build_coatstand():
    F, P = COL["FURN"], COL["PROPS"]
    x, y = COATSTAND_C
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.4
        box("cab_cs_foot", F, mat("wood"), (x + 0.12 * math.cos(a), y + 0.12 * math.sin(a), 0.04), (0.26, 0.04, 0.05),
            rot=(0, 0, a), bv=0.01)
    lathe("cab_cs_post", F, mat("wood"), (x, y, 0.0),
          [(0.05, 0.0), (0.05, 0.06), (0.03, 0.12), (0.024, 0.5), (0.03, 0.55), (0.024, 0.6), (0.022, 1.5),
           (0.03, 1.56), (0.022, 1.62), (0.022, 1.70), (0.03, 1.72), (0.0, 1.73)], seg=14)
    sph("cab_cs_finial", F, mat("wood_light"), (x, y, 1.76), (0.035, 0.035, 0.035), seg=14)
    for k in range(4):
        a = 2 * math.pi * k / 4 + 0.6
        tube("cab_cs_hook", F, mat("brass"), [(x + 0.02 * math.cos(a), y + 0.02 * math.sin(a), 1.56),
                                              (x + 0.11 * math.cos(a), y + 0.11 * math.sin(a), 1.53),
                                              (x + 0.14 * math.cos(a), y + 0.14 * math.sin(a), 1.60)], 0.007)
    # 挂在钩上的小挎包
    a = 2 * math.pi * 1 / 4 + 0.6
    hx, hy = x + 0.13 * math.cos(a), y + 0.13 * math.sin(a)
    tube("cab_bag_strap", P, mat("leather"), [(hx, hy, 1.56), (hx + 0.05, hy - 0.03, 1.25), (hx + 0.02, hy - 0.05, 1.08)], 0.008)
    tube("cab_bag_strap2", P, mat("leather"), [(hx, hy, 1.56), (hx - 0.03, hy - 0.07, 1.25), (hx - 0.06, hy - 0.06, 1.08)], 0.008)
    box("cab_bag", P, mat("leather"), (hx, hy - 0.05, 0.98), (0.22, 0.08, 0.18), rot=(0, 0, a), bv=0.025, seg=3)
    box("cab_bag_flap", P, mat("wood_dark"), (hx, hy - 0.093, 1.02), (0.20, 0.012, 0.10), rot=(0, 0, a), bv=0.01)


def build_broom():
    P = COL["PROPS"]
    y = IY - 0.07
    for xx in (-1.85, -1.25):
        cyl("cab_peg", P, mat("wood_dark"), (xx, IY - 0.04, 2.17), 0.014, 0.09, seg=10, rot=(math.pi / 2, 0, 0))
    cyl("cab_broom_handle", P, mat("wood_light"), (-1.58, y, 2.20), 0.018, 1.1, seg=12, rot=(0, math.pi / 2, 0))
    lathe("cab_broom_bristle", P, mat("straw"), (-2.13, y, 2.20),
          [(0.025, 0.0), (0.05, 0.04), (0.085, 0.16), (0.11, 0.30), (0.10, 0.31), (0.0, 0.32)], seg=18, rot=(0, -math.pi / 2, 0))
    for d in (0.03, 0.09):
        cyl("cab_broom_band", P, mat("rope"), (-2.13 + 0.0 - d + 0.0, y, 2.20), 0.04 + d * 0.35, 0.012, seg=16, rot=(0, math.pi / 2, 0))


def build_stove():
    F, P = COL["FURN"], COL["PROPS"]
    x, y = STOVE_C
    box("cab_hearth", F, mat("stone"), (x + 0.02, y, 0.03), (0.78, 0.76, 0.06), bv=0.015)
    # 墙上的石砌隔热板
    st = []
    for r in range(6):
        for k in range(4):
            st.append(((IX - 0.03, y - 0.36 + 0.18 * k + (0.09 if r % 2 else 0), 0.12 + r * 0.17),
                       (0.05, 0.17, 0.155), (0, 0, 0)))
    prims("cab_heatshield", "cube", F, mat("stone"), [s for s in st if abs(s[0][1] - y) < 0.42], jitter=0.06)
    for k in range(3):
        a = 2 * math.pi * k / 3
        cyl("cab_stove_leg", F, mat("iron"), (x + 0.15 * math.cos(a), y + 0.15 * math.sin(a), 0.11), 0.025, 0.10, seg=10)
    lathe("cab_stove_body", F, mat("iron"), (x, y, 0.0),
          [(0.17, 0.16), (0.22, 0.22), (0.26, 0.34), (0.25, 0.48), (0.21, 0.58), (0.20, 0.64), (0.235, 0.66), (0.235, 0.70), (0.0, 0.70)], seg=28)
    # 炉门朝屋里（−x、略朝 −y），门上的火光窗
    da = math.atan2(-0.35, -1.0)
    dx, dy = math.cos(da), math.sin(da)
    box("cab_stove_door", F, mat("iron"), (x + 0.255 * dx, y + 0.255 * dy, 0.34), (0.03, 0.18, 0.16), rot=(0, 0, da), bv=0.01)
    box("cab_stove_fire", F, G_FIRE, (x + 0.272 * dx, y + 0.272 * dy, 0.34), (0.012, 0.12, 0.08), rot=(0, 0, da), bv=0.004)
    sph("cab_stove_knob", F, mat("brass"), (x + 0.285 * dx - 0.07 * dy, y + 0.285 * dy + 0.07 * dx, 0.34), (0.014, 0.014, 0.014), seg=10)
    # 烟管：竖直上去，再拐进东墙
    tube("cab_stove_pipe", F, mat("iron"), [(x, y, 0.70), (x, y, 1.80), (x + 0.05, y, 1.95), (x + 0.20, y, 1.97), (IX + 0.05, y, 1.97)], 0.065)
    cyl("cab_pipe_collar", F, mat("iron"), (IX - 0.01, y, 1.97), 0.10, 0.02, seg=20, rot=(0, math.pi / 2, 0))
    # 水壶
    kx, ky = x + 0.03, y - 0.02
    lathe("cab_kettle", P, mat("brass"), (kx, ky, 0.70), [(0.06, 0), (0.10, 0.03), (0.105, 0.07), (0.08, 0.11), (0.04, 0.13), (0.045, 0.14), (0, 0.15)], seg=20)
    tube("cab_kettle_spout", P, mat("brass"), [(kx - 0.08, ky, 0.75), (kx - 0.13, ky, 0.80), (kx - 0.16, ky, 0.84)], 0.012)
    tube("cab_kettle_handle", P, mat("wood_dark"), [(kx - 0.05, ky, 0.83), (kx, ky, 0.92), (kx + 0.05, ky, 0.83)], 0.008)
    # 柴筐 + 猫垫
    bx, by = 1.38, -1.68
    lathe("cab_logbasket", P, mat("straw"), (bx, by, 0), [(0.15, 0), (0.19, 0.04), (0.2, 0.22), (0.19, 0.23), (0.17, 0.05)], seg=20, cap_top=False)
    logs = []
    for k in range(5):
        a = k * 1.3
        logs.append(((bx + 0.07 * math.cos(a), by + 0.07 * math.sin(a), 0.22), (0.035, 0.035, 0.42), (0.25 * math.cos(a), 0.25 * math.sin(a), 0)))
    prims("cab_logs", "cyl", P, mat("wood"), logs, seg=8)
    lathe("cab_cat_cushion", P, mat("rug1"), (1.05, -1.42, 0), [(0.0, 0.0), (0.22, 0.0), (0.25, 0.04), (0.23, 0.08), (0.17, 0.085), (0.15, 0.05), (0.0, 0.045)], seg=24)


def build_rug():
    P = COL["PROPS"]
    cols = ["rug1", "rug2", "rug3", "rug2", "rug4", "rug2", "rug1"]
    for i, r in enumerate([1.0, 0.87, 0.74, 0.61, 0.48, 0.35, 0.20]):
        cyl(f"cab_rug{i}", P, mat(cols[i]), (RUG_C[0], RUG_C[1], 0.006 + i * 0.0015), r, 0.012, seg=48, rot=(0, 0, 0), sm=False)
        bpy.data.objects[f"cab_rug{i}"].scale = (1.0, 0.82, 1.0)


def build_misc():
    F, P = COL["FURN"], COL["PROPS"]
    # 旅行箱
    x, y = TRUNK_C
    box("cab_trunk", F, mat("leather"), (x, y, 0.17), (0.72, 0.40, 0.30), bv=0.02)
    l = box("cab_trunk_lid", F, mat("wood"), (x, y, 0.35), (0.74, 0.42, 0.10), bv=0.045, seg=3)
    for xx in (x - 0.22, x + 0.22):
        box("cab_trunk_strap", F, mat("wood_dark"), (xx, y, 0.22), (0.05, 0.43, 0.38), bv=0.006)
    box("cab_trunk_latch", F, mat("brass"), (x, y - 0.215, 0.29), (0.07, 0.015, 0.08), bv=0.005)
    # 大盆栽（近处左角，低矮）
    px, py = -2.08, -1.58
    lathe("cab_bigpot", F, mat("terracotta"), (px, py, 0), [(0.11, 0), (0.15, 0.24), (0.165, 0.25), (0.165, 0.29), (0.0, 0.29)], seg=20)
    leaves = []
    for k in range(10):
        a = k * 2.4
        tilt = random.uniform(0.6, 1.0)
        L = random.uniform(0.18, 0.26)
        leaves.append(((px + 0.13 * math.cos(a), py + 0.13 * math.sin(a), 0.42 + random.uniform(0, 0.18)),
                       (L, 0.08, 0.012), (0, -tilt * 0.6, a)))
    prims("cab_bigplant", "sphere", F, mat("leaf"), leaves[::2], seg=12)
    prims("cab_bigplant2", "sphere", F, mat("leaf2"), leaves[1::2], seg=12)
    for k in range(5):
        a = k * 1.25
        tube(f"cab_stem{k}", F, mat("leaf3"), [(px, py, 0.28), (px + 0.06 * math.cos(a), py + 0.06 * math.sin(a), 0.42),
                                              (px + 0.12 * math.cos(a), py + 0.12 * math.sin(a), 0.5)], 0.006)
    # 地垫子 + 一本书
    c = box("cab_floor_cushion", P, mat("cushion"), (-1.20, -0.42, 0.06), (0.48, 0.48, 0.12), rot=(0, 0, 0.3), bv=0.045, seg=3)
    subsurf(c, 1); smooth(c)
    book("cab_floor_book", P, (-0.86, -0.66, 0.0), (0.20, 0.15, 0.035), rz=-0.5, color="book_teal")
    # 墙上的日历 + 挂钟（北墙两扇窗之间）
    cx = 0.52
    box("cab_calendar", P, mat("paper"), (cx, IY - 0.006, 1.42), (0.30, 0.008, 0.38), bv=0.0)
    box("cab_calendar_head", P, mat("red"), (cx, IY - 0.011, 1.585), (0.30, 0.006, 0.06), bv=0.0)
    cells = [((cx - 0.105 + 0.07 * i, IY - 0.011, 1.50 - 0.06 * j), (0.05, 0.004, 0.04), 0.0) for i in range(4) for j in range(5)]
    boxes("cab_calendar_cells", P, mat("plaster_cut"), cells)
    lathe("cab_cal_mark", P, mat("red"), (cx - 0.035, IY - 0.015, 1.38), [(0.03, -0.002), (0.03, 0.002)], seg=20,
          rot=(math.pi / 2, 0, 0), cap_bot=False, cap_top=False)
    cyl("cab_clock", P, mat("wood_light"), (cx, IY - 0.02, 2.22), 0.11, 0.035, seg=32, rot=(math.pi / 2, 0, 0))
    cyl("cab_clock_dial", P, mat("white"), (cx, IY - 0.039, 2.22), 0.09, 0.004, seg=32, rot=(math.pi / 2, 0, 0))
    box("cab_clock_h", P, mat("black"), (cx + 0.02, IY - 0.043, 2.235), (0.05, 0.003, 0.008), rot=(0, -0.6, 0), bv=0.0)
    box("cab_clock_m", P, mat("black"), (cx - 0.005, IY - 0.044, 2.255), (0.005, 0.003, 0.07), bv=0.0)
    # 东墙两扇窗之间挂一束干花
    hx = IX - 0.04
    hy = 0.08
    tube("cab_dry_string", P, mat("rope"), [(hx, hy, 1.95), (hx, hy, 1.82)], 0.003, smooth_curve=False)
    stems = [((hx - 0.01, hy + random.uniform(-0.03, 0.03), 1.70), (0.004, 0.004, 0.24), (random.uniform(-0.15, 0.15), random.uniform(-0.15, 0.15), 0))
             for _ in range(7)]
    prims("cab_dry_stems", "cyl", P, mat("leaf3"), stems, seg=5)
    heads = [((hx - 0.02, hy + random.uniform(-0.06, 0.06), 1.58 + random.uniform(-0.03, 0.03)), (0.025, 0.025, 0.03), (0, 0, 0)) for _ in range(9)]
    prims("cab_dry_heads", "ico", P, mat("purple"), heads[::2], jitter=0.2)
    prims("cab_dry_heads2", "ico", P, mat("yellow"), heads[1::2], jitter=0.2)
    # 东窗窗台的小盆栽、床上方窗台的玻璃瓶
    lathe("cab_herb_pot", P, mat("terracotta"), (IX - 0.05, -0.85, 0.90 + 0.02), [(0.04, 0), (0.05, 0.07), (0, 0.07)], seg=14)
    prims("cab_herb", "ico", P, mat("leaf"), [((IX - 0.05 + random.uniform(-0.03, 0.03), -0.85 + random.uniform(-0.04, 0.04),
                                               1.0 + random.uniform(0, 0.06)), (0.035, 0.035, 0.03), (0, 0, 0)) for _ in range(8)], jitter=0.2)
    lathe("cab_vase", P, mat("potion_a"), (1.80, IY - 0.04, 1.05 + 0.02), [(0.03, 0), (0.04, 0.05), (0.02, 0.11), (0.024, 0.13), (0, 0.13)], seg=16)


def build_cat(name="cab_cat", loc=None):
    """睡在床尾被子上的橘猫（蜷成一团，原创简化造型）"""
    P = COL["PROPS"]
    root = empty(name, loc or (BED_X[0] + 0.30, BED_Y[1] - 0.24, BED_TOP + 0.05), P)
    root.rotation_euler = (0, 0, 0.5)
    parts = []
    parts.append(sph("cab_cat_body", P, mat("cat"), (0, 0, 0.075), (0.19, 0.145, 0.08), seg=20))
    parts.append(sph("cab_cat_head", P, mat("cat"), (0.12, -0.085, 0.07), (0.07, 0.068, 0.06), seg=18))
    parts.append(sph("cab_cat_muzzle", P, mat("cat_white"), (0.17, -0.11, 0.055), (0.03, 0.03, 0.022), seg=12))
    for s in (-1, 1):
        o = cyl("cab_cat_ear", P, mat("cat"), (0.12 + 0.03 * s, -0.08 - 0.02, 0.135), 0.025, 0.045, seg=8, r2=0.0)
        o.rotation_euler = (0.3 * s, 0.25, 0)
        parts.append(o)
    parts.append(tube("cab_cat_tail", P, mat("cat"), [(-0.17, 0.03, 0.04), (-0.16, -0.10, 0.03), (-0.02, -0.17, 0.03), (0.09, -0.15, 0.03)], 0.026))
    stripes = [((-0.05 + 0.07 * k, 0.0, 0.15), (0.018, 0.12, 0.012), (0, 0, 0)) for k in range(3)]
    parts.append(prims("cab_cat_stripes", "sphere", P, mat("orange"), stripes, seg=10))
    for o in parts:
        o.parent = root
    return root, parts


# ============================================================ 浮岛底座（让室内像从岛上切下来的一块）
def build_base():
    B = COL["BASE"]
    n = 72

    def R(th):
        rx, ry = 3.85, 3.35
        r = 1.0 / math.sqrt((math.cos(th) / rx) ** 2 + (math.sin(th) / ry) ** 2)
        return r * (1 + 0.03 * math.sin(3 * th + 1.0) + 0.02 * math.sin(5 * th + 2.0) + 0.01 * math.sin(9 * th))

    levels = [(GROUND, 1.0), (GROUND - 0.10, 0.985), (GROUND - 0.40, 0.93), (GROUND - 0.68, 0.74), (GROUND - 0.88, 0.42), (GROUND - 1.0, 0.16)]
    verts = []
    for z, k in levels:
        for i in range(n):
            th = 2 * math.pi * i / n
            r = R(th) * k * (1 + (0.04 * math.sin(7 * th + z * 5) if z < GROUND - 0.2 else 0))
            verts.append((r * math.cos(th), r * math.sin(th), z + (0.05 * math.sin(4 * th + z) if z < GROUND - 0.2 else 0)))
    verts.append((0.0, 0.0, GROUND - 1.08))
    faces = [tuple(range(n))]
    for L in range(len(levels) - 1):
        for i in range(n):
            a, b = L * n + i, L * n + (i + 1) % n
            faces.append((a + n, b + n, b, a))
    last = (len(levels) - 1) * n
    tip = len(verts) - 1
    for i in range(n):
        faces.append((last + (i + 1) % n, last + i, tip))
    me = bpy.data.meshes.new("cab_island")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("cab_island", me)
    B.objects.link(ob)
    me.materials.append(mat("grass"))
    me.materials.append(mat("cliff"))
    for p in me.polygons:
        p.material_index = 0 if p.index == 0 else 1
    # 草丛、小花、石头、灌木：只撒在木屋外圈
    tuft_a, tuft_b, fl, rocks = [], [], {"pink": [], "white": [], "purple": [], "yellow": []}, []
    for _ in range(900):
        th = random.uniform(0, 2 * math.pi)
        rr = R(th) * math.sqrt(random.uniform(0.0, 1.0)) * 0.96
        x, y = rr * math.cos(th), rr * math.sin(th)
        if abs(x) < IX + WT + 0.28 and abs(y) < IY + WT + 0.28:
            continue
        s = random.uniform(0.05, 0.09)
        for k in range(3):
            (tuft_a if random.random() < 0.6 else tuft_b).append(
                ((x + random.uniform(-0.03, 0.03), y + random.uniform(-0.03, 0.03), GROUND + s * 1.2), (s * 0.18, s * 0.18, s * 2.4),
                 (random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), 0)))
        if random.random() < 0.12:
            fl[random.choice(list(fl))].append(((x, y, GROUND + 0.12), (0.035, 0.035, 0.03), (0, 0, 0)))
    for _ in range(18):
        th = random.uniform(0, 2 * math.pi)
        r = R(th) * random.uniform(0.86, 0.97)
        rocks.append(((r * math.cos(th), r * math.sin(th), GROUND + 0.02), (random.uniform(0.1, 0.22), random.uniform(0.08, 0.18), 0.09),
                      (0, 0, random.uniform(0, 3))))
    prims("cab_grass_a", "cone", B, mat("grass_dark"), tuft_a, seg=4)
    prims("cab_grass_b", "cone", B, mat("grass_light"), tuft_b, seg=4)
    for k, it in fl.items():
        if it:
            prims(f"cab_flowers_{k}", "ico", B, mat(k), it)
    prims("cab_rocks", "ico", B, mat("rock"), rocks, jitter=0.3)
    for bx, by, r in ((-3.25, 1.45, 0.42), (-3.05, -0.9, 0.3), (1.9, -2.75, 0.36), (-1.0, -2.85, 0.28), (3.3, -1.6, 0.4)):
        it = [((bx + random.uniform(-r, r) * 0.5, by + random.uniform(-r, r) * 0.5, GROUND + r * random.uniform(0.5, 0.9)),
               (r * 0.55, r * 0.55, r * 0.5), (0, 0, 0)) for _ in range(5)]
        prims(f"cab_bush_{bx:.0f}_{by:.0f}", "ico", B, mat(random.choice(["leaf", "leaf2"])), it, jitter=0.15)
        prims(f"cab_bushfl_{bx:.0f}_{by:.0f}", "ico", B, mat(random.choice(["pink", "white"])),
              [((bx + random.uniform(-r, r) * 0.6, by + random.uniform(-r, r) * 0.6, GROUND + r * 1.05), (0.04, 0.04, 0.035), (0, 0, 0)) for _ in range(5)])


# ============================================================ 搭建
build_shell()
build_door()
for nm, c, w, z0, z1 in NORTH_OPEN[1:]:
    build_window(nm, "N", c, w, z0, z1)
for nm, c, w, z0, z1 in EAST_OPEN:
    build_window(nm, "E", c, w, z0, z1)
build_desk()
build_chair()
build_wall_shelf()
build_bed()
build_nightstand()
build_coatstand()
CS_K = 0.85                             # 衣帽架整体压到 0.85 高（顶 1.79 → 1.52）：伊蕾娜约 1.4 m，原来伸手够不到帽子
_cs = empty("cab_cs_root", (COATSTAND_C[0], COATSTAND_C[1], 0.0), COL["FURN"])
bpy.context.view_layer.update()
for _o in [o for c in ("FURN", "PROPS") for o in COL[c].all_objects if o.name.startswith(("cab_cs_", "cab_bag_")) and o is not _cs]:
    parent_keep(_o, _cs)
_cs.scale = (1.0, 1.0, CS_K)
bpy.context.view_layer.update()
build_broom()
build_stove()
build_rug()
build_misc()
CAT_ROOT, CAT_PARTS = build_cat()
for _o in CAT_PARTS:
    show_at(_o, ("night", "day"))
build_base()
log(f"场景搭好：{len(bpy.data.objects)} 个物体")

# 窗帘各时段状态：open 拉开 / closed 合上 / gap 留缝
CURTAIN = {
    "wb": {"win_f2": "open", "win_f1": "open", "win_l1": "open", "win_l2": "open"},
    "night": {"win_f2": "open", "win_f1": "open", "win_l1": "open", "win_l2": "open"},
    "day": {"win_f2": "open", "win_f1": "open", "win_l1": "open", "win_l2": "open"},
    "dawn": {"win_f2": "closed", "win_f1": "closed", "win_l1": "gap", "win_l2": "closed"},
    "late": {"win_f2": "closed", "win_f1": "closed", "win_l1": "open", "win_l2": "closed"},
}
for nm in ("win_f2", "win_f1", "win_l1", "win_l2"):
    for st in ("open", "closed", "gap"):
        for side in ("L", "R"):
            ob = bpy.data.objects.get(f"cab_{nm}_cur_{st}_{side}")
            if ob:
                show_at(ob, [t for t, d in CURTAIN.items() if d[nm] == st])

# ============================================================ 灯光
ROOM_E_NIGHT, ROOM_E_LATE = 200.0, 120.0   # 显示器照全屋的点光（W）：夜里学习 / 深夜睡觉
ROOM_Z = 1.5                               # 这盏点光的高度
ROOM_DESK_K = 0.25                         # 书桌机位（B1 / B6 近景）只用这盏点光的 25%：脸主要由屏幕照亮，背后墙面留一点（11-27 实测：100% 平均亮度 117，25% 为 89）


def point(name, loc, rgb, powers, radius=0.05, shadow=True):
    ld = bpy.data.lights.new(name, "POINT")
    ld.color = lin(rgb)
    ld.energy = powers.get("night", 0)
    ld.shadow_soft_size = radius
    ld.use_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    COL["LIGHTS"].objects.link(ob)
    LIGHTS.append((ob, powers))
    return ob


lx, ly = LAMP_XY
point("L_desk_lamp", (lx, ly, DESK_TOP + 0.35), (1.0, 0.74, 0.46), {"dawn": 0, "day": 0, "night": 0, "late": 0}, radius=0.03)
_ml = bpy.data.lights.new("L_monitor", "AREA")
_ml.shape = "RECTANGLE"
_ml.size, _ml.size_y = MON_W - 0.02, MON_H - 0.02
_ml.color = lin((1.0, 0.76, 0.50))             # 暖光
_ml.use_shadow = True
_ml.spread = math.radians(75)                  # 光束收窄：主要照脸和上半身，不铺满整间屋
try:                                           # EEVEE 自定义照射距离：1.3 m 以外不受这盏灯影响
    _ml.use_custom_distance = True
    _ml.cutoff_distance = 1.8
except AttributeError:
    pass
L_MON = bpy.data.objects.new("L_monitor", _ml)
L_MON.location = (MON_C[0], MON_C[1] + 0.03, DESK_TOP + MON_Z0 + MON_H / 2)
L_MON.rotation_euler = Vector((0, 0.465, 0.175)).to_track_quat("-Z", "Y").to_euler()     # 朝 +y（朝她的脸），跟屏幕一样略往上仰
COL["LIGHTS"].objects.link(L_MON)
LIGHTS.append((L_MON, {"dawn": 0, "day": 4, "night": 45, "late": 45}))      # 夜里屋里唯一的光（学习 / 睡觉都是）
# 睡觉时桌面那边的余光照到床上：屏幕位置一盏宽角度暖光朝床
_sl = bpy.data.lights.new("L_desk_spill", "AREA")
_sl.shape = "RECTANGLE"
_sl.size, _sl.size_y = MON_W, MON_H
_sl.color = lin((1.0, 0.76, 0.50))
_sl.use_shadow = True
_sl.spread = math.radians(110)
try:
    _sl.use_custom_distance = True
    _sl.cutoff_distance = 4.0
except AttributeError:
    pass
L_SPILL = bpy.data.objects.new("L_desk_spill", _sl)
L_SPILL.location = (MON_C[0], MON_C[1] + 0.05, DESK_TOP + MON_Z0 + MON_H / 2)
_bed_c = Vector(((BED_X[0] + BED_X[1]) / 2, (BED_Y[0] + BED_Y[1]) / 2, BED_TOP + 0.10))
L_SPILL.rotation_euler = (_bed_c - L_SPILL.location).to_track_quat("-Z", "Y").to_euler()
COL["LIGHTS"].objects.link(L_SPILL)
LIGHTS.append((L_SPILL, {"dawn": 0, "day": 0, "night": 0, "late": 30}))
# 显示器照亮整间屋（用户 11-27：房间都亮一点，电脑周围最亮，远端弱一点）：屏幕前一盏柔和暖色点光，不限距离，
# 点光按距离平方衰减 → 书桌一带最亮、床 / 门口 / 火炉逐渐变暗。深夜跟着屏幕一起微闪（screen_flicker）
_room_e = [float(x) for x in os.environ.get("GSD_ROOM_E", f"{ROOM_E_NIGHT},{ROOM_E_LATE}").split(",")]
# 放在屏幕前上方 1.5 m 高：太低的话桌面会在南半边地板投出一大片硬影子（11-27 试过 0.9 m）
L_ROOM = point("L_monitor_room", (MON_C[0], MON_C[1] + 0.35, ROOM_Z), (1.0, 0.74, 0.48),
               {"dawn": 0, "day": 0, "night": _room_e[0], "late": _room_e[1]}, radius=0.6)
point("L_stove", (STOVE_C[0] - 0.42, STOVE_C[1] - 0.12, 0.32), (1.0, 0.50, 0.20), {"dawn": 4, "day": 2, "night": 0, "late": 0}, radius=0.1)
point("L_night_lamp", (NIGHTSTAND_C[0] + 0.05, NIGHTSTAND_C[1] + 0.08, 0.70), (1.0, 0.72, 0.45), {"dawn": 3, "day": 0, "night": 0, "late": 0}, radius=0.05)
fl = bpy.data.lights.new("L_fill", "AREA")
fl.shape = "DISK"
fl.size = 3.5
fl.use_shadow = False
fob = bpy.data.objects.new("L_fill", fl)
fob.location = (0.3, 0.2, 2.45)
COL["LIGHTS"].objects.link(fob)
LIGHTS.append((fob, {"dawn": 40, "day": 60, "night": 0, "late": 0}))
FILL_COL = {"dawn": (0.80, 0.84, 1.0), "day": (1.0, 0.97, 0.92), "night": (1.0, 0.80, 0.60), "late": (0.70, 0.76, 1.0)}
sld = bpy.data.lights.new("Sun", "SUN")
sld.angle = math.radians(1.5)
sld.use_shadow = True
SUN = bpy.data.objects.new("Sun", sld)
COL["LIGHTS"].objects.link(SUN)

TIME_CFG = {
    # dir = 阳光 / 月光在水平面上的前进方向；el = 高度角
    "dawn": dict(dir=(-0.82, 0.57), el=22, sun=(1.0, 0.72, 0.46), power=7.0, world=(0.44, 0.48, 0.64), wpow=0.45,
                 sky=((0.98, 0.80, 0.66), (0.55, 0.62, 0.82)), tint=(0.86, 0.86, 0.96), bloom=0.6, line=(0.12, 0.09, 0.13), exposure=0.5),
    "day": dict(dir=(-0.60, 0.80), el=38, sun=(1.0, 0.96, 0.90), power=5.0, world=(0.70, 0.80, 0.98), wpow=0.9,
                sky=((0.86, 0.93, 1.0), (0.50, 0.72, 0.97)), tint=(1.0, 1.0, 1.0), bloom=0.3, line=(0.12, 0.09, 0.13), exposure=0.0),
    "night": dict(dir=(0.25, -0.97), el=34, sun=(0.62, 0.72, 1.0), power=0.6, world=(0.08, 0.10, 0.22), wpow=0.2,
                  sky=((0.14, 0.18, 0.34), (0.05, 0.07, 0.17)), tint=(1.0, 0.90, 0.80), bloom=0.9, line=(0.10, 0.08, 0.12), exposure=0.9),
    "late": dict(dir=(-0.82, 0.57), el=30, sun=(0.58, 0.68, 1.0), power=0.6, world=(0.05, 0.06, 0.14), wpow=0.2,
                 sky=((0.08, 0.10, 0.22), (0.03, 0.04, 0.11)), tint=(1.0, 0.90, 0.80), bloom=1.0, line=(0.08, 0.08, 0.14), exposure=0.9),
}


# ============================================================ 世界（镜头看到渐变天色，照明用纯色）
def build_world():
    w = bpy.data.worlds.new("CabinWorld")
    sc.world = w
    if bpy.app.version < (5, 0, 0):
        w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bl = nt.nodes.new("ShaderNodeBackground"); bl.name = "BG_light"
    bc = nt.nodes.new("ShaderNodeBackground"); bc.name = "BG_cam"
    lp = nt.nodes.new("ShaderNodeLightPath")
    mx = nt.nodes.new("ShaderNodeMixShader")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    rp = nt.nodes.new("ShaderNodeValToRGB"); rp.name = "SkyRamp"
    nt.links.new(tc.outputs["Window"], sp.inputs["Vector"])
    nt.links.new(sp.outputs["Y"], rp.inputs["Fac"])
    nt.links.new(rp.outputs["Color"], bc.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs["Fac"])
    nt.links.new(bl.outputs["Background"], mx.inputs[1])
    nt.links.new(bc.outputs["Background"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])


build_world()

# --- 窗外岛屿背景板（render_window_bg.py 在岛屿成品里拍的广角图）：只给书桌近景镜头用；主镜头是正交俯视，会看到板子本身
BD_DIR = os.path.join(HERE, "backdrop")
BD_D, BD_FOV, BD_EYE, BD_ASPECT = 10.0, 110.0, 1.25, 1350 / 2400
BD_TAG = {"night": "night", "late": "night", "day": "noon", "dawn": "morning", "wb": "night"}
BD_STR = {"night": 1.0, "late": 0.55, "day": 1.0, "dawn": 0.9, "wb": 1.0}
BACKDROPS = []


def build_window_backdrops():
    W_ = 2 * BD_D * math.tan(math.radians(BD_FOV) / 2)
    H_ = W_ * BD_ASPECT
    n = 0
    for tag in sorted(set(BD_TAG.values())):
        for view in ("front", "west"):
            path = os.path.join(BD_DIR, f"island_{tag}_{view}.png")
            if not os.path.exists(path):
                log(f"窗外背景：缺 {os.path.basename(path)}，跳过")
                continue
            m = _new_material(f"BD_{tag}_{view}")
            nt = m.node_tree
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = bpy.data.images.load(path, check_existing=True)
            tx.extension = "EXTEND"
            em = nt.nodes.new("ShaderNodeEmission")
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(tx.outputs["Color"], em.inputs["Color"])
            nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            GLOW.append((m, {t: BD_STR[t] for t, tg in BD_TAG.items() if tg == tag}))
            # 视点在屋子正中；正面板在北墙外（室内 +y），西侧板在东墙外（室内 +x）；从里往外看，图片左边 = 看的人的左手边
            if view == "front":
                c = Vector((0, BD_D, BD_EYE)); ax_u, ax_v = Vector((1, 0, 0)), Vector((0, 0, 1))
            else:
                c = Vector((BD_D, 0, BD_EYE)); ax_u, ax_v = Vector((0, -1, 0)), Vector((0, 0, 1))
            vs = [c + ax_u * (W_ * (u - 0.5)) + ax_v * (H_ * (v - 0.5)) for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))]
            me = bpy.data.meshes.new(f"cab_backdrop_{tag}_{view}")
            me.from_pydata(vs, [], [(0, 1, 2, 3)])
            uv = me.uv_layers.new()
            for li, (u, v) in zip(range(4), ((0, 0), (1, 0), (1, 1), (0, 1))):
                uv.data[li].uv = (u, v)
            me.materials.append(m)
            ob = bpy.data.objects.new(me.name, me)
            COL["BASE"].objects.link(ob)
            ob.visible_shadow = False
            ob.visible_diffuse = False
            ob.visible_glossy = False
            ob.visible_transmission = False
            ob.visible_volume_scatter = False
            ob.hide_render = True                    # 默认藏起；渲书桌镜头时才打开（见 backdrops_on）
            BACKDROPS.append((ob, tag))
            n += 1
    log(f"窗外背景板 {n} 块（离屋子中心 {BD_D} m，宽 {W_:.1f} m）")


DESK_ONLY = []      # 只在书桌近景镜头里出现的物体（主镜头是剖面，西墙切掉了）


def build_west_wall_desk():
    """完整西墙（灰泥 + 竖木墙裙 + 压顶 + 顶梁）：近景镜头往左上看会穿过切掉的西墙看到外面，补上；主镜头不显示"""
    C = COL["ROOM"]
    obs = [box("cab_deskonly_wall_W", C, mat("plaster"), (-IX - WT / 2, 0, WH / 2), (WT, 2 * IY + 2 * WT, WH), bv=0.0)]
    wa, wb = [], []
    u, k = -IY, 0
    while u < IY - 1e-3:
        u2 = min(IY, u + 0.115)
        (wa if k % 2 == 0 else wb).append(((-IX + 0.011, (u + u2) / 2, 0.44), (0.022, u2 - u - 0.004, 0.88), 0.0))
        u, k = u2, k + 1
    obs.append(boxes("cab_deskonly_wains_a", C, mat("wains_a"), wa, bv=0.004))
    obs.append(boxes("cab_deskonly_wains_b", C, mat("wains_b"), wb, bv=0.004))
    obs.append(box("cab_deskonly_wains_cap", C, mat("wood"), (-IX + 0.03, 0, 0.905), (0.06, 2 * IY, 0.05), bv=0.012))
    obs.append(box("cab_deskonly_beam", C, mat("wood_dark"), (-IX + 0.035, 0, 2.43), (0.07, 2 * IY, 0.14), bv=0.01))
    for o in obs:
        o.hide_render = True
        DESK_ONLY.append(o)


build_west_wall_desk()


def backdrops_on(t, on=True):
    for ob, tag in BACKDROPS:
        ob.hide_render = not (on and BD_TAG.get(t) == tag)
    for ob in DESK_ONLY:
        ob.hide_render = not on


build_window_backdrops()


# ============================================================ 人物：追加 3 份
CH_INFO = {}


def assign(ob, act):
    ob.animation_data_create()
    ob.animation_data.action = act
    try:
        if act.slots:
            ob.animation_data.action_slot = act.slots[0]
    except Exception:
        pass


# ================================================================== B1 学习循环（--b1）
B1 = "--b1" in ARGV
B1_CLIP = "Typing"          # Mixamo 坐着打字：手在桌面上动，配摊开的书 / 笔记本读成「写字、记笔记」
B1_LOOP, B1_S0, B1_XF = 192, 24, 24
B1_INFO = {}
B1_HEAD_DOWN = (("neck.x", 8.0), ("head.x", 12.0))     # 低头看键盘 / 屏幕下沿：在 Typing 原动作上再往前点 20°


def _act_fcurves(act):
    try:
        return list(act.fcurves)
    except AttributeError:
        return [fc for l in act.layers for s_ in l.strips for cb in s_.channelbags for fc in cb.fcurves]


def _sample_act(act, n, rig):
    modes = {pb.name: pb.rotation_mode for pb in rig.pose.bones}
    ch = {}
    for fc in _act_fcurves(act):
        dp = fc.data_path
        if not dp.startswith('pose.bones["'):
            continue
        ch.setdefault(dp.split('"')[1], {}).setdefault(dp.rsplit(".", 1)[1], {})[fc.array_index] = fc
    out = []
    for f in range(1, n + 1):
        P_ = {}
        for bn, pr in ch.items():
            lc = pr.get("location", {})
            loc = Vector([lc[i].evaluate(f) if i in lc else 0.0 for i in range(3)])
            if "rotation_quaternion" in pr:
                qc = pr["rotation_quaternion"]
                q = Quaternion([qc[i].evaluate(f) if i in qc else (1.0 if i == 0 else 0.0) for i in range(4)])
                q.normalize()
            elif "rotation_euler" in pr:
                ec = pr["rotation_euler"]
                o_ = modes.get(bn, "XYZ")
                o_ = o_ if o_ in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX") else "XYZ"
                q = Euler([ec[i].evaluate(f) if i in ec else 0.0 for i in range(3)], o_).to_quaternion()
            else:
                q = Quaternion()
            P_[bn] = (loc, q)
        out.append(P_)
    return out


_Z0 = (Vector((0, 0, 0)), Quaternion())


def _blend(Pa, Pb, w):
    out = {}
    for bn in set(Pa) | set(Pb):
        la, qa = Pa.get(bn, _Z0)
        lb, qb = Pb.get(bn, _Z0)
        qb = qb.copy()
        qb.make_compatible(qa)
        out[bn] = (la.lerp(lb, w), qa.slerp(qb, w))
    return out


def _ease(t):
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _write_clip(rig, name, frames):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    assign(rig, act)

    def put(path, idx, vals, grp):
        fc = act.fcurve_ensure_for_datablock(rig, path, index=idx, group_name=grp)
        kp = fc.keyframe_points
        kp.add(len(vals))
        co = []
        for i, v in enumerate(vals):
            co += [float(i + 1), float(v)]
        kp.foreach_set("co", co)
        for k_ in kp:
            k_.interpolation = "LINEAR"
        fc.update()
    for bn in sorted(set().union(*[set(f) for f in frames])):
        if bn not in rig.pose.bones:
            continue
        locs = [fr.get(bn, _Z0)[0] for fr in frames]
        qs, prev = [], None
        for fr in frames:
            q = fr.get(bn, _Z0)[1].copy()
            if prev is not None:
                q.make_compatible(prev)
            prev = q
            qs.append(q)
        if any(l.length > 1e-7 for l in locs):
            for i in range(3):
                put(f'pose.bones["{bn}"].location', i, [l[i] for l in locs], bn)
        for i in range(4):
            put(f'pose.bones["{bn}"].rotation_quaternion', i, [q[i] for q in qs], bn)
    assign(rig, act)
    return act


def _bone_w(rig, nm, tail=False):
    pb = rig.pose.bones.get(nm)
    return None if pb is None else rig.matrix_world @ (pb.tail if tail else pb.head)


SEAT_HIP = 0.09          # 坐姿：髋关节（thigh_stretch 头）高出椅面 9 cm


def lamp_lit_toon(CH, floor=((0.24, 0.18, 0.18), (0.62, 0.50, 0.46)), toon_w=0.62, light_w=0.70):
    """夜里只有屏幕光：人物卡通材质原来暗部有一层固定的灰紫底色（0.34,0.32,0.50），关了灯脸还是亮的、发灰发白；
    这里只改这份人物用的 ToonCore：暗部压低、偏暖，真实光照（带灯光颜色）的比例 0.32 → 0.70，被暖光照到的地方才是暖的肤色"""
    groups = set()
    for o in CH.all_objects:
        if o.type != "MESH":
            continue
        for sl in o.material_slots:
            m = sl.material
            if m and m.node_tree:
                for n in m.node_tree.nodes:
                    if n.type == "GROUP" and n.node_tree and n.node_tree.name.startswith("ToonCore"):
                        groups.add(n.node_tree)
    for ng in groups:
        ramp = next((n for n in ng.nodes if n.type == "VALTORGB"), None)
        if ramp is not None and len(ramp.color_ramp.elements) >= 3:
            ramp.color_ramp.elements[0].color = (*lin(floor[0]), 1)
            ramp.color_ramp.elements[1].color = (*lin(floor[1]), 1)
        for n in ng.nodes:
            if n.type == "VECT_MATH" and n.operation == "SCALE":
                sc_in = n.inputs["Scale"]
                if abs(sc_in.default_value - 0.78) < 1e-3:
                    sc_in.default_value = toon_w
                elif abs(sc_in.default_value - 0.32) < 1e-3:
                    sc_in.default_value = light_w
    log(f"人物材质（屏幕光）：改了 {[g.name for g in groups]}，暗部 {floor}，卡通 / 真实光照比例 {toon_w} / {light_w}")
    # 模型自带的描边是一层包住全身的外壳（*_Line 材质），它会投影，把人物整个罩在自己的影子里，灯光照不到脸
    n_line = 0
    for o in CH.all_objects:
        if o.type != "MESH":
            continue
        for sl in o.material_slots:
            m = sl.material
            if not (m and m.node_tree and "_Line" in m.name) or m.get("gsd_noshadow"):
                continue
            nt = m.node_tree
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
            src = out.inputs["Surface"].links[0].from_socket if out and out.inputs["Surface"].links else None
            if src is None:
                continue
            lp = nt.nodes.new("ShaderNodeLightPath")
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            mx = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs["Fac"])
            nt.links.new(src, mx.inputs[1])
            nt.links.new(tr.outputs["BSDF"], mx.inputs[2])
            nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
            try:
                m.use_transparent_shadow = True
            except AttributeError:
                pass
            m["gsd_noshadow"] = 1
            n_line += 1
    log(f"人物描边外壳不再投影：{n_line} 个材质")


BREATH_N = 2                            # D2 睡觉循环：192 帧里呼吸 2 次（4 秒一次，约 15 次 / 分钟）
BREATH_LIFT = 0.008                     # 被子胸口最高抬 8 mm
BREATH_X, BREATH_W = 1.60, 0.24         # 胸口在床上的 x 位置和范围（头心 x≈2.02，往脚那头 0.4 m）


def breath_value(f):
    """0~1，按 192 帧整周期（第 193 帧 = 第 1 帧）"""
    return 0.5 - 0.5 * math.cos(2 * math.pi * BREATH_N * ((f - 1) % 192) / 192)


def add_breath(CH):
    """D2 睡觉循环：被子胸口一块随呼吸起伏（形状键），头和猫跟着微微动。睡着的人物是冻结的静态网格，只能这样做呼吸"""
    q = bpy.data.objects.get("cab_quilt_sleep")
    if q is None:
        return
    if q.data.shape_keys is None:
        q.shape_key_add(name="Basis", from_mix=False)
    kb = q.shape_key_add(name="breath", from_mix=False)
    n = 0
    for i, v in enumerate(q.data.vertices):
        w = math.exp(-((v.co.x - BREATH_X) / BREATH_W) ** 2) * min(1.0, max(0.0, (v.co.z - BED_TOP - 0.02) / 0.06))
        if w > 0.01:
            kb.data[i].co.z = v.co.z + BREATH_LIFT * w
            n += 1
    cat = bpy.data.objects.get("cab_cat_sleep")
    cat_w = math.exp(-((cat.location.x - BREATH_X) / BREATH_W) ** 2) if cat else 0.0
    cat_z = cat.location.z if cat else 0.0
    heads = [o for o in CH.all_objects if o.type == "MESH"]
    for f in range(1, 194):
        b = breath_value(f)
        kb.value = b
        kb.keyframe_insert("value", frame=f)
        if cat:
            cat.location.z = cat_z + BREATH_LIFT * cat_w * b
            cat.keyframe_insert("location", index=2, frame=f)
        for o in heads:                     # 头随呼吸极轻地起伏 1.5 mm
            o.location.z = 0.0015 * b
            o.keyframe_insert("location", index=2, frame=f)
    kb.value = 0.0
    log(f"D2 呼吸：被子 {n} 个顶点随呼吸起伏（最高 {BREATH_LIFT * 1000:.0f} mm，192 帧 {BREATH_N} 次），头 / 猫跟着动")


def hip_joint_z(rig):
    return sum(_bone_w(rig, f"thigh_stretch.{s_}").z for s_ in ("l", "r")) / 2


def build_b1(CH, rig, root):
    """B1：Typing 重定向 → 截 192 帧首尾交叉淡化闭合 → 手放到桌面上（据此定臀部和椅子位置）→ 斗篷摆动模拟"""
    old = CH.name
    CH.name = "CHAR_人物"                 # 重定向库按这个集合名找人物
    os.environ["GSD_OUT"] = OUT
    _argv = sys.argv
    sys.argv = [sys.argv[0], "--", "lib"]
    RT = {"__name__": "gsd_retarget", "__file__": RT_PATH}
    exec(compile(open(RT_PATH, encoding="utf-8").read(), RT_PATH, "exec"), RT)
    sys.argv = _argv
    CH.name = old
    globals()["B1_RT"] = RT                  # 之后 A4 等片段继续用同一个重定向库
    n = RT["retarget"](B1_CLIP, in_place=True)
    mx_scene = bpy.data.scenes.get("MX_SRC")
    if mx_scene:
        bpy.data.scenes.remove(mx_scene)
    src_act = rig.animation_data.action
    fr = _sample_act(src_act, n, rig)
    bpy.data.actions.remove(src_act)
    loop = []
    for i in range(B1_LOOP):
        p_ = fr[B1_S0 + i]
        if i >= B1_LOOP - B1_XF:
            p_ = _blend(p_, fr[i - (B1_LOOP - B1_XF)], _ease((i - (B1_LOOP - B1_XF) + 1) / (B1_XF + 1)))
        loop.append(p_)
    B = rig.data.bones
    up_ = (B["neck.x"].head_local - B["root.x"].head_local).normalized()
    left_ = B["arm_stretch.l"].head_local - B["arm_stretch.r"].head_local
    left_ = (left_ - up_ * left_.dot(up_)).normalized()
    for bn, deg in B1_HEAD_DOWN:
        if bn not in B:
            continue
        ax_ = (B[bn].matrix_local.to_3x3().inverted() @ left_).normalized()
        dq = Quaternion(ax_, math.radians(deg))
        for fr_ in loop:
            l_, q_ = fr_.get(bn, _Z0)
            fr_[bn] = (l_, dq @ q_)
    log(f"B1 低头：{B1_HEAD_DOWN}")
    act = _write_clip(rig, "CLIP_B1_study", loop)
    log(f"B1：{B1_CLIP} 重定向 {n} 帧，截第 {B1_S0 + 1}–{B1_S0 + B1_LOOP} 帧，末尾 {B1_XF} 帧交叉淡化回第 1 帧")

    def measure():
        pv, hands, knees, fingers = [], [], [], []
        for f in range(1, B1_LOOP + 1, 4):
            sc.frame_set(f)
            bpy.context.view_layer.update()
            pv.append(pelvis_w(rig))
            for s_ in ("l", "r"):
                h_ = _bone_w(rig, f"hand.{s_}")
                if h_ is not None:
                    hands.append(h_)
                k_ = _bone_w(rig, f"leg_stretch.{s_}")
                if k_ is not None:
                    knees.append(k_)
                for fn in ("index1", "middle1", "ring1", "pinky1"):
                    t_ = _bone_w(rig, f"{fn}.{s_}", tail=True)
                    if t_ is not None:
                        fingers.append(t_)
        return pv, hands, knees, fingers
    root.location = (0, 0, 0)
    bpy.context.view_layer.update()
    pv, hands, knees, fingers = measure()
    pm = sum(pv, Vector()) / len(pv)
    hm = sum(hands, Vector()) / len(hands)
    hj = hip_joint_z(rig)                       # 注意：root.x 在腰上，髋关节（thigh_stretch 头）比它低约 0.29 m
    desk_edge = DESK_C[1] + DESK_D / 2
    want_hand_y = desk_edge - 0.13              # 手腕落在桌面上、离桌边 13 cm
    root.location = Vector((CHAIR_C[0] - pm.x, want_hand_y - hm.y, CHAIR_SEAT + SEAT_HIP - hj))
    bpy.context.view_layer.update()
    pv, hands, knees, fingers = measure()
    pm = sum(pv, Vector()) / len(pv)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    hjy = sum((_bone_w(rig, f"thigh_stretch.{s_}") for s_ in ("l", "r")), Vector()) / 2
    dy = (hjy.y + 0.06) - CHAIR_C[1]            # 椅子跟着髋关节挪（髋关节在椅面中心前 6 cm，屁股在椅面中心）
    for o in list(COL["FURN"].all_objects) + list(COL["PROPS"].all_objects):
        if o.name.startswith("cab_chair"):
            o.location.y += dy
    bpy.context.view_layer.update()
    lo_f = min(p_.z for p_ in fingers) if fingers else 0
    fx0, fx1 = min(p_.x for p_ in fingers), max(p_.x for p_ in fingers)
    fy0, fy1 = min(p_.y for p_ in fingers), max(p_.y for p_ in fingers)
    kw_ = min(0.46, max(0.36, fx1 - fx0 + 0.08))
    kc_ = ((fx0 + fx1) / 2, (fy0 + fy1) / 2 + 0.01)
    kh_ = min(0.035, max(0.014, lo_f - 0.004 - DESK_TOP - 0.012))
    for o in [o for o in COL["PROPS"].all_objects if o.name.startswith("cab_kb_")]:
        bpy.data.objects.remove(o, do_unlink=True)
    build_keyboard(COL["PROPS"], kc_, kw_, DESK_TOP, h=kh_)
    log(f"B1 键盘：指尖 x [{fx0:.3f},{fx1:.3f}] y [{fy0:.3f},{fy1:.3f}] 最低 z {lo_f:.3f} → 键盘中心 {tuple(round(v, 3) for v in kc_)} 宽 {kw_:.2f} 高 {kh_:.3f}，键帽顶 {DESK_TOP + kh_ + 0.012:.3f}")
    feet = []
    for f in range(1, B1_LOOP + 1, 8):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        feet += [_bone_w(rig, f"foot.{s_}") for s_ in ("l", "r")]
    log(f"B1 髋关节 z {hip_joint_z(rig):.3f}（椅面 {CHAIR_SEAT} + {SEAT_HIP}）；脚踝最低 z {min(p_.z for p_ in feet):.3f}")
    B1_INFO.update(chair_y=round(CHAIR_C[1] + dy, 3), pelvis=[round(v, 3) for v in pm],
                   hand_y_mean=round(sum(h.y for h in hands) / len(hands), 3),
                   hand_z=[round(min(h.z for h in hands), 3), round(max(h.z for h in hands), 3)], finger_z_min=round(lo_f, 3),
                   knee_z_max=round(max(k.z for k in knees), 3), knee_y_min=round(min(k.y for k in knees), 3))
    log(f"B1 摆位：椅子 y {CHAIR_C[1]:.3f} → {CHAIR_C[1] + dy:.3f}；臀部 {tuple(round(v, 3) for v in pm)}；"
        f"手腕 z {B1_INFO['hand_z']}，指尖最低 z {lo_f:.3f}（桌面 {DESK_TOP}）；膝盖最高 z {B1_INFO['knee_z_max']}、最靠前 y {B1_INFO['knee_y_min']}"
        f"（桌裙底 {DESK_TOP - 0.13:.2f}，桌边 y {desk_edge:.3f}）")
    try:                                        # 斗篷摆动（cloth_sim v2，循环）
        import importlib.util
        spec = importlib.util.spec_from_file_location("cloth_sim", CLOTH_PATH)
        cs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cs)
        sc.frame_start, sc.frame_end = 1, B1_LOOP
        cs.simulate(rig, 1, B1_LOOP, loop=True, log=log)
    except Exception as e:
        log(f"B1 斗篷模拟失败：{e!r}")
    sc.frame_set(1)
    return act


def load_copy(tag):
    with bpy.data.libraries.load(CHAR_SRC, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == "CHAR_人物"]
    CH = dst.collections[0]
    CH.name = "CHAR_" + tag
    COL["CHARS"].children.link(CH)
    rig = next(o for o in CH.all_objects if o.type == "ARMATURE")
    top = rig
    while top.parent:
        top = top.parent
        if not top.users_collection:
            CH.objects.link(top)
    return CH, rig, top


def pelvis_w(rig):
    return rig.matrix_world @ rig.pose.bones["root.x"].head


def head_w(rig):
    pb = rig.pose.bones.get("head.x") or rig.pose.bones.get("head")
    return rig.matrix_world @ pb.head


def hat_parts(CH):
    return [o for o in CH.all_objects if o.type == "MESH" and o.name.split(".")[0] in ("hat01", "hat02", "hat03")]


def wbbox(obs):
    dg = bpy.context.evaluated_depsgraph_get()
    mn, mx = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in obs:
        oe = o.evaluated_get(dg)
        for c in oe.bound_box:
            p = oe.matrix_world @ Vector(c)
            mn = Vector((min(mn.x, p.x), min(mn.y, p.y), min(mn.z, p.z)))
            mx = Vector((max(mx.x, p.x), max(mx.y, p.y), max(mx.z, p.z)))
    return mn, mx


CAPE_CHAINS = [["Bone.075"], ["Bone.077", "Bone.082"], ["Bone.078", "Bone.084"],
               ["Bone.088"], ["Bone.093", "Bone.094"], ["Bone.096", "Bone.097"]]
CAPE_KEEP = 0.30      # 斗篷外张的水平分量只保留 30%（原来 40~50° 外张 → 约 13~17°，自然下垂）


def relax_cape(rig, keep=CAPE_KEEP):
    """把斗篷 6 条骨链往竖直方向收：保留水平朝向，只缩小外张角（从根到梢逐节处理）"""
    R = rig.matrix_world.to_3x3().normalized()
    Ri = R.inverted()
    n = 0
    for chain in CAPE_CHAINS:
        for bn in chain:
            pb = rig.pose.bones.get(bn)
            if pb is None:
                continue
            bpy.context.view_layer.update()
            d = (R @ (pb.tail - pb.head)).normalized()
            t = Vector((d.x * keep, d.y * keep, -abs(d.z))).normalized()
            q = (Ri @ d).rotation_difference(Ri @ t).to_matrix().to_4x4()
            h = pb.head.copy()
            pb.matrix = Matrix.Translation(h) @ q @ Matrix.Translation(-h) @ pb.matrix
            n += 1
    bpy.context.view_layer.update()
    return n


HAT_ON_STAND = []
HAT_INFO = {}         # 帽子：复制时的头骨矩阵 H0、帽子根矩阵 R0（G5 戴帽用）
RT_PATH = os.path.join(LIB_DIR, "retarget_mixamo.py")
SLEEP_CLIP = "Laying Sleeping"
HB_FACE = BED_X[1] - 0.04 - 0.035       # 床头柱内侧（x）
FB_FACE = BED_X[0] + 0.035 + 0.035      # 床尾柱内侧（x）
MAT_Y = (BED_Y[0] + 0.035, BED_Y[1] - 0.035)
SLEEP_REPORT = {}


COVERED_BONES = ("shoulder.", "arm_stretch.", "c_arm_twist_offset.", "forearm_stretch.", "spine_01.", "spine_02.", "spine_03.")


def hide_covered_skin(CH):
    """长袖长袍底下的手臂 / 肩膀 / 躯干皮肤本来就看不见：用 Mask 修改器隐藏（按主导骨骼选顶点），动作再大也不会从袖子里穿出来"""
    n = 0
    for o in [o for o in CH.all_objects if o.type == "MESH" and o.name.split(".")[0] == "body"]:
        vg = o.vertex_groups.new(name="GSD_covered")
        names = {g.index: g.name for g in o.vertex_groups}
        ids = []
        for v in o.data.vertices:
            if v.groups:
                g = max(v.groups, key=lambda g: g.weight)
                if names.get(g.group, "").startswith(COVERED_BONES):
                    ids.append(v.index)
        vg.add(ids, 1.0, "REPLACE")
        md = o.modifiers.new("GSD_hide_covered", "MASK")
        md.vertex_group = vg.name
        md.invert_vertex_group = True
        n += len(ids)
    bpy.context.view_layer.update()
    return n


def cloth_poke(CH):
    """统计里层顶点从长袍外侧穿出来的数量（距长袍 < 3 cm、在长袍法线外侧 > 2 mm）"""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    obs = [o for o in CH.all_objects if o.type == "MESH" and not o.hide_render]

    def W(o):
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        v = [oe.matrix_world @ x.co for x in me.vertices]
        pl = [tuple(f.vertices) for f in me.polygons]
        oe.to_mesh_clear()
        return v, pl
    out = {}
    for r in [o for o in obs if o.name.startswith("Robe")]:
        rv, rp = W(r)
        t = BVHTree.FromPolygons(rv, rp)
        for o in obs:
            if o is r or o.name.startswith(("Robe", "Hair_", "hat")):
                continue
            n = 0
            for q in W(o)[0]:
                loc, nrm, _, d = t.find_nearest(q)
                if loc is not None and d < 0.03 and (q - loc).dot(nrm) > 0.002:
                    n += 1
            if n:
                out[f"{o.name.split('.')[0]}→{r.name.split('.')[0]}"] = n
    return out


def bake_pose(rig):
    keep = {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones}
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis = keep[pb.name]
    bpy.context.view_layer.update()


def visible_meshes(CH):
    return [o for o in CH.all_objects if o.type == "MESH" and not o.hide_render]


def world_pts(obs, step=1):
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in obs:
        oe = o.evaluated_get(dg)
        mw = oe.matrix_world
        vs = oe.data.vertices
        for i in range(0, len(vs), step):
            out.append((mw @ vs[i].co, o.name))
    return out


def bvh_world(o):
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    m = oe.matrix_world
    me = oe.to_mesh()
    vs = [m @ v.co for v in me.vertices]
    ps = [tuple(p.vertices) for p in me.polygons]
    oe.to_mesh_clear()
    return BVHTree.FromPolygons(vs, ps)


HEAD_PREFIX = ("Hair_", "eye", "eyebrow", "headband")


def split_head(rig, pts):
    """头部点：头发 / 眼睛 / 眉毛网格的全部点 + 身体网格里离头心 0.13 m 以内的点；其余算身体（必须盖在被子里）"""
    hb = rig.pose.bones["head.x"]
    hc = rig.matrix_world @ (hb.head + (hb.tail - hb.head) * 0.55)
    head, body = [], []
    for p, nm in pts:
        base = nm.split(".")[0]
        if base.startswith(HEAD_PREFIX) or (p - hc).length < 0.155:
            head.append(p)
        else:
            body.append(p)
    return head, body, hc


def build_sleep():
    """D2 侧躺：Mixamo Laying Sleeping 重定向 → 摆到床上 → 枕头被头压出凹陷 → 被子用布料物理盖上去 → 穿模检查"""
    with bpy.data.libraries.load(CHAR_SRC, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == "CHAR_人物"]
    CH = dst.collections[0]
    COL["CHARS"].children.link(CH)
    rig = next(o for o in CH.all_objects if o.type == "ARMATURE")
    root = rig
    while root.parent:
        root = root.parent
        if not root.users_collection:
            CH.objects.link(root)
    root.animation_data_clear()
    root.rotation_mode = "XYZ"
    root.location = (0, 0, 0)
    root.rotation_euler = (0, 0, 0)
    for h in hat_parts(CH):
        h.hide_render = True
        h.hide_viewport = True
    bpy.context.view_layer.update()
    # 重定向库按集合名 CHAR_人物 找人物；日志写进本次输出目录
    os.environ["GSD_OUT"] = OUT
    _argv = sys.argv
    sys.argv = [sys.argv[0], "--", "lib"]
    RT = {"__name__": "gsd_retarget", "__file__": RT_PATH}
    exec(compile(open(RT_PATH, encoding="utf-8").read(), RT_PATH, "exec"), RT)
    sys.argv = _argv
    n = RT["retarget"](SLEEP_CLIP, in_place=True)
    mx_scene = bpy.data.scenes.get("MX_SRC")
    if mx_scene:
        bpy.data.scenes.remove(mx_scene)
    sc.frame_set(min(40, n))               # 重定向库在第 40 帧闭眼（眨眼峰值），睡觉取这一帧
    bpy.context.view_layer.update()
    bake_pose(rig)
    sc.frame_set(1)
    la = RT["left_a"]
    for s_ in ("l", "r"):
        for nm_, deg in ((f"eyelid_top.{s_}", 16.0), (f"eyelid_bot.{s_}", -4.0)):
            pb = rig.pose.bones.get(nm_)
            if pb is not None:
                qa = Quaternion(la, math.radians(deg)).to_matrix().to_4x4()
                h_ = pb.head.copy()
                pb.matrix = Matrix.Translation(h_) @ qa @ Matrix.Translation(-h_) @ pb.matrix
    bpy.context.view_layer.update()
    CH.name = "CHAR_lie"
    log(f"睡姿：{SLEEP_CLIP} 重定向 {n} 帧，取第 {min(40, n)} 帧（闭眼）")

    # --- 朝向：身体轴（骨盆→头）转到 +x（头朝床头），脸朝屋里（−y）
    pv, hd = pelvis_w(rig), head_w(rig)
    ax = hd - pv
    root.rotation_euler = (0, 0, -math.atan2(ax.y, ax.x))
    bpy.context.view_layer.update()
    eyes = [p for p, nm in world_pts([o for o in visible_meshes(CH) if o.name.split(".")[0] == "eye"])]
    hb = rig.pose.bones["head.x"]
    hc = rig.matrix_world @ (hb.head + (hb.tail - hb.head) * 0.55)
    if eyes:
        ec = sum(eyes, Vector()) / len(eyes)
        log(f"睡姿脸朝向：眼睛相对头心 y {ec.y - hc.y:+.3f}，z {ec.z - hc.z:+.3f}")
        if ec.y - hc.y > 0:            # 脸朝墙 → 绕身体长轴转 180°，换另一侧躺，脸朝屋里
            root.matrix_world = Matrix.Rotation(math.pi, 4, "X") @ root.matrix_world
            bpy.context.view_layer.update()
            log("睡姿：原本脸朝墙，绕身体长轴转 180°")
    # --- 斗篷受重力：侧躺时朝上翘的斗篷片往下落、贴到身上（和站姿收拢同一函数）
    def _hi_log(tag_):
        _pts = world_pts([o for o in visible_meshes(CH) if not o.name.split(".")[0].startswith(HEAD_PREFIX)], step=4)
        lo = min(q.z for q, _ in _pts)
        _hi = max(_pts, key=lambda t: t[0].z)
        log(f"睡姿{tag_}：身体高 {_hi[0].z - lo:.3f} m，最高点属于 {_hi[1]}")
    _hi_log("（斗篷处理前）")
    # 侧躺时斗篷片顺着腿往脚的方向平铺（只留一点上下起伏），不再朝天翘
    R3c = rig.matrix_world.to_3x3().normalized()
    for chain in CAPE_CHAINS:
        for bn in chain:
            pb = rig.pose.bones.get(bn)
            if pb is None:
                continue
            bpy.context.view_layer.update()
            d_ = (R3c @ (pb.tail - pb.head)).normalized()
            t_ = Vector((-1.0, d_.y * 0.35, d_.z * 0.12)).normalized()
            qa = (R3c.inverted() @ d_.rotation_difference(t_).to_matrix() @ R3c).to_4x4()
            h_ = pb.head.copy()
            pb.matrix = Matrix.Translation(h_) @ qa @ Matrix.Translation(-h_) @ pb.matrix
    bpy.context.view_layer.update()
    _hi_log("（斗篷顺腿平铺后）")
    # 上面那只手的袖口受重力垂下来贴在身侧（重定向库是按站姿"向下"摆的，躺下后就朝天了）
    ft = {s_: (rig.matrix_world @ rig.pose.bones[f"forearm_twist.{s_}"].head).z for s_ in ("l", "r")}
    top_s = max(ft, key=ft.get)
    sleeve = [b_.name for b_ in rig.data.bones if b_.name.startswith("Bone") and b_.parent and
              (b_.parent.name == f"forearm_twist.{top_s}" or (b_.parent.parent and b_.parent.parent.name == f"forearm_twist.{top_s}"))]
    for bn in sleeve:
        pb = rig.pose.bones[bn]
        bpy.context.view_layer.update()
        d_ = (R3c @ (pb.tail - pb.head)).normalized()
        t_ = Vector((d_.x * 0.3, d_.y * 0.3, -1.0)).normalized()
        qa = (R3c.inverted() @ d_.rotation_difference(t_).to_matrix() @ R3c).to_4x4()
        h_ = pb.head.copy()
        pb.matrix = Matrix.Translation(h_) @ qa @ Matrix.Translation(-h_) @ pb.matrix
    bpy.context.view_layer.update()
    _hi_log(f"（上侧 {top_s} 袖口垂下 {len(sleeve)} 节后）")
    # --- 平移：最低点贴床垫顶面；头离床头柱 3.5 cm；身体在床垫宽度里居中
    pts = world_pts(visible_meshes(CH), step=2)
    allp = [p for p, _ in pts]
    zmin = min(p.z for p in allp)
    xmax = max(p.x for p in allp)
    ymin, ymax = min(p.y for p in allp), max(p.y for p in allp)
    d = Vector((HB_FACE - 0.035 - xmax, (MAT_Y[0] + MAT_Y[1]) / 2 - (ymin + ymax) / 2, BED_TOP + 0.003 - zmin))
    root.matrix_world = Matrix.Translation(d) @ root.matrix_world
    bpy.context.view_layer.update()
    # 手原来缩在下巴前面：整条手臂绕肩转一点，手往胸口下移 20 cm，好让被子只盖到脖子
    neck0 = rig.matrix_world @ rig.pose.bones["neck.x"].head
    R3 = rig.matrix_world.to_3x3().normalized()
    for s_ in ("l", "r"):
        ab = rig.pose.bones.get(f"arm_stretch.{s_}")
        hb2 = rig.pose.bones.get(f"hand.{s_}")
        if ab is None or hb2 is None:
            continue
        S_ = rig.matrix_world @ ab.head
        Hh = rig.matrix_world @ hb2.head
        if Hh.x < neck0.x - 0.08:
            continue
        v_ = Hh - S_
        w_ = (Hh - Vector((0.20, 0, 0)) - S_).normalized() * v_.length
        qa = (R3.inverted() @ v_.rotation_difference(w_).to_matrix() @ R3).to_4x4()
        h_ = ab.head.copy()
        ab.matrix = Matrix.Translation(h_) @ qa @ Matrix.Translation(-h_) @ ab.matrix
        bpy.context.view_layer.update()
        log(f"睡姿：{s_} 手从 x={Hh.x:.3f} 移到 x={(rig.matrix_world @ hb2.head).x:.3f}")
    pts = world_pts(visible_meshes(CH), step=1)
    head, body, hc = split_head(rig, pts)
    hb_ = rig.pose.bones["head.x"]
    _hc = rig.matrix_world @ (hb_.head + (hb_.tail - hb_.head) * 0.55)
    body_names = [nm for p, nm in pts if not (nm.split(".")[0].startswith(HEAD_PREFIX) or (p - _hc).length < 0.155)]
    allp = [p for p, _ in pts]
    bb = (min(p.x for p in allp), max(p.x for p in allp), min(p.y for p in allp), max(p.y for p in allp),
          min(p.z for p in allp), max(p.z for p in allp))
    log(f"睡姿包围盒 x[{bb[0]:.3f},{bb[1]:.3f}] y[{bb[2]:.3f},{bb[3]:.3f}] z[{bb[4]:.3f},{bb[5]:.3f}]；"
        f"床尾内侧 {FB_FACE:.3f}，床头内侧 {HB_FACE:.3f}，床垫 y {MAT_Y}")
    if bb[0] < FB_FACE + 0.02 or bb[2] < MAT_Y[0] or bb[3] > MAT_Y[1]:
        log("⚠ 睡姿超出床垫范围")
    # --- 只露头：整个人下沉到头枕在 10 cm 高的枕头上；脖子以下的网格遮掉（在被子里，看不见也就不会穿模）
    #     被子形状仍按身体轮廓来，但高度只取 1/4（她没那么"厚"）
    from mathutils.bvhtree import BVHTree
    LOWER = max(0.0, hc.z - (BED_TOP + 0.10 + 0.085))       # 按头骨（头心）算，不按垂到床上的发梢算
    root.matrix_world = Matrix.Translation(Vector((0, 0, -LOWER))) @ root.matrix_world
    bpy.context.view_layer.update()
    pts = world_pts(visible_meshes(CH), step=1)
    head, body, hc = split_head(rig, pts)
    dg = bpy.context.evaluated_depsgraph_get()
    bv, bp, hp_ = [], [], []
    for o in visible_meshes(CH):              # 先建身体 / 头的形状树（遮罩之前）
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        off = len(bv)
        isk = o.name.split(".")[0].startswith(HEAD_PREFIX)
        wv = [oe.matrix_world @ v.co for v in me.vertices]
        hv = [isk or (q - hc).length < 0.155 for q in wv]
        bv += wv
        bp += [tuple(i + off for i in pl.vertices) for pl in me.polygons if not any(hv[i] for i in pl.vertices)]
        hp_ += [tuple(i + off for i in pl.vertices) for pl in me.polygons if all(hv[i] for i in pl.vertices)]
        oe.to_mesh_clear()
    PRE_TREES = (BVHTree.FromPolygons(bv, bp), BVHTree.FromPolygons(bv, hp_))
    # 把这份躺姿冻结成静态网格（白模只要这一帧），然后直接按重力规则处理头和头发
    CLOTH_PREFIX = ("Robe", "Blouse", "tie", "LeatedSkirt", "boots")
    SC_ = bpy.data.collections.new("CHAR_lie_static")
    COL["CHARS"].children.link(SC_)
    LIE_OBJS = []
    for o in list(visible_meshes(CH)):
        base_ = o.name.split(".")[0]
        if base_.startswith(CLOTH_PREFIX):          # 衣服全在被子里
            continue
        oe = o.evaluated_get(dg)
        me_ = bpy.data.meshes.new_from_object(oe, preserve_all_data_layers=True, depsgraph=dg)
        me_.transform(oe.matrix_world)
        ob_ = bpy.data.objects.new("lie_" + base_, me_)
        SC_.objects.link(ob_)
        if not base_.startswith(HEAD_PREFIX):       # 身体皮肤只留脸和脖子
            bm_ = bmesh.new()
            bm_.from_mesh(me_)
            dels = [v for v in bm_.verts if (v.co - hc).length >= 0.155]
            bmesh.ops.delete(bm_, geom=dels, context="VERTS")
            bm_.to_mesh(me_)
            bm_.free()
        LIE_OBJS.append(ob_)
    CH.hide_render = True
    for o in list(CH.all_objects):
        o.hide_render = True
        o.hide_viewport = True
    bpy.context.view_layer.update()
    head = [v.co.copy() for o in LIE_OBJS for v in o.data.vertices]
    allp = list(head)
    log(f"睡姿：冻结成静态网格 {len(LIE_OBJS)} 个（衣服去掉，皮肤只留脸和脖子）")
    QS = 0.25
    log(f"睡姿：下沉 {LOWER:.3f} m，头枕在 10 cm 枕头上；被子高度取身体的 {QS:.0%}")
    neck = rig.matrix_world @ rig.pose.bones["neck.x"].head

    # --- 枕头：头的最低点下沉 3 cm 的高度做枕面，再按头 / 头发 / 肩膀的实际位置压出凹陷
    P = COL["PROPS"]
    skin = [v.co.copy() for o in LIE_OBJS if not o.name[4:].startswith("Hair_") for v in o.data.vertices]
    near = list(skin)                         # 枕头只被脸 / 头骨压出凹陷；头发之后搭在枕面上
    hz_bot = min(p.z for p in near)
    top = max(BED_TOP + 0.08, hz_bot + 0.02)
    hh = (top - BED_TOP) / 2 + 0.004
    pc = Vector((min(hc.x, HB_FACE - 0.19), hc.y, BED_TOP + hh - 0.004))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0,
                              matrix=Matrix.Translation(pc) @ D(0.18, 0.31, hh))
    for v in bm.verts:                  # 压扁成方枕：四角饱满、上下面平
        c = v.co - pc
        f = 1 - abs(c.z) / hh
        v.co.x = pc.x + c.x * (1.0 + 0.12 * f)
        v.co.y = pc.y + c.y * (1.0 + 0.08 * f)
        k = max(abs(c.x) / 0.18, abs(c.y) / 0.31) ** 3
        v.co.z = pc.z + c.z * (1.0 - 0.15 * k)
    from mathutils.kdtree import KDTree
    kd = KDTree(len(skin))
    for i, p in enumerate(skin):
        kd.insert((p.x, p.y, 0.0), i)
    kd.balance()
    bm.verts.ensure_lookup_table()
    req = {}
    for v in bm.verts:
        if v.co.z < pc.z:
            continue
        hits = kd.find_range((v.co.x, v.co.y, 0.0), 0.022)
        if hits:
            mz = min(skin[i].z for _, i, _ in hits)
            if v.co.z > mz - 0.008:
                req[v.index] = mz - 0.008 - v.co.z
    disp = {v.index: req.get(v.index, 0.0) for v in bm.verts}
    nb = {v.index: [e.other_vert(v).index for e in v.link_edges] for v in bm.verts}
    for _ in range(8):                  # 凹陷向四周柔和过渡，但每个点至少压到需要的深度
        new = {}
        for i, dv in disp.items():
            avg = (dv + sum(disp[j] for j in nb[i])) / (1 + len(nb[i]))
            new[i] = min(req[i], avg) if i in req else min(0.0, avg * 0.9)
        disp = new
    for i, dv in disp.items():
        if bm.verts[i].co.z >= pc.z - hh * 0.3:
            bm.verts[i].co.z += dv
    pillow = smooth(mk("cab_pillow_sleep", bm, P, mat("sheet")))
    show_at(pillow, ("dawn", "late", "wb"))
    log(f"枕头：顶面 {top:.3f}，被头 / 头发 / 肩压下 {len(req)} 个顶点，最深 {-min(req.values(), default=0) * 100:.1f} cm")

    # --- 被子：程序生成（不用物理引擎）。按身体每处的实际高度鼓起 → 向外扩 7 cm → 柔化，
    #     并保证被子底面处处高于身体 2 cm；靠屋里一侧沿床垫边垂下去，靠墙一侧塞进去
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    bv, bp, hp_ = [], [], []
    for o in visible_meshes(CH):            # 只用身体（不含头、头发）的面算被子高度
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        off = len(bv)
        isk = o.name.split(".")[0].startswith(HEAD_PREFIX)
        wv = [oe.matrix_world @ v.co for v in me.vertices]
        hv = [isk or (q - hc).length < 0.155 for q in wv]
        bv += wv
        bp += [tuple(i + off for i in pl.vertices) for pl in me.polygons if not any(hv[i] for i in pl.vertices)]
        hp_ += [tuple(i + off for i in pl.vertices) for pl in me.polygons if all(hv[i] for i in pl.vertices)]
        oe.to_mesh_clear()
    body_tree = PRE_TREES[0]
    _hv, _hp = [], []
    for o in LIE_OBJS:
        off = len(_hv)
        _hv += [v.co.copy() for v in o.data.vertices]
        _hp += [tuple(i + off for i in pl.vertices) for pl in o.data.polygons]
    head_tree = BVHTree.FromPolygons(_hv, _hp)
    # 被子形状只看脸 / 脖子 / 头骨皮肤，不看头发：头发是软的，压在被子下面（看不见，后面删掉），不能把被子顶起来
    _sv, _sp = [], []
    for o in LIE_OBJS:
        if o.name[4:].startswith(HEAD_PREFIX):      # 头发 / 头带 / 眉眼都不算：只用身体皮肤（脸、脖子）
            continue
        off = len(_sv)
        _sv += [v.co.copy() for v in o.data.vertices]
        _sp += [tuple(i + off for i in pl.vertices) for pl in o.data.polygons]
    skin_tree = BVHTree.FromPolygons(_sv, _sp)
    # 只有脖子：被子上沿盖到脖子为止（靠身体那一截皮肤），后脑勺 / 脸不算
    _np = [pl for pl in _sp if all(_sv[k].x < neck.x + 0.01 for k in pl)]
    neck_tree = BVHTree.FromPolygons(_sv, _np) if _np else None
    body_xmax = max(p.x for p in body)
    _top = max(body, key=lambda q: q.z)
    log(f"身体最高点 z={_top.z:.3f} @ x={_top.x:.3f} y={_top.y:.3f}（床垫顶 {BED_TOP}）")
    edge_x = min(neck.x - 0.03, hc.x - 0.05)                 # 主体上沿：脖子下方 3 cm
    ext_x = max(edge_x, body_xmax + 0.03)    # 脸那一侧只盖到脖子 +8 cm；背后（靠墙一侧）可以盖过肩膀和后脑
    log(f"被子上沿 x={edge_x:.3f}，局部延伸到 {ext_x:.3f}（脖子 {neck.x:.3f}，身体最靠头 {body_xmax:.3f}，头心 {hc.x:.3f}）")
    xq0, xq1 = FB_FACE + 0.005, ext_x
    ya_, yb_ = MAT_Y[0] - 0.01, IY - 0.015          # 靠墙一侧一直盖到墙边（塞在墙和床之间）
    pill_tree = bvh_world(pillow)
    step = 0.016
    ny = int((yb_ - ya_) / step)
    nx = int((xq1 - xq0) / step)

    def XE(y):
        """被子上沿是一条平滑曲线：脸那一侧在脖子下 3 cm，绕到背后慢慢升高盖过肩膀"""
        return ext_x

    YS = [ya_ + (yb_ - ya_) * j / ny for j in range(ny + 1)]
    XS = [[xq0 + (XE(YS[j]) - xq0) * i / nx for j in range(ny + 1)] for i in range(nx + 1)]
    H = [[BED_TOP] * (ny + 1) for _ in range(nx + 1)]
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = XS[i][j], YS[j]
            h = body_tree.ray_cast(Vector((x, y, 3.0)), Vector((0, 0, -1)))
            if h[0] is not None:
                H[i][j] = BED_TOP + QS * max(0.0, h[0].z + LOWER - BED_TOP)
            if x > edge_x:                    # 上沿附近在枕头上：被子不能钻进枕头；背后越过后脑头发（脸那侧从下巴底下过）
                for tree in (pill_tree,):          # 只让枕头托起被子，后脑勺 / 头发都不顶被子
                    hh_ = tree.ray_cast(Vector((x, y, 3.0)), Vector((0, 0, -1)))
                    if hh_[0] is not None:
                        H[i][j] = max(H[i][j], hh_[0].z)
    # 头附近：被子从下巴底下塞进去；塞不进去的地方盖在皮肤上面（头发不算，压在被子下面）
    def head_fix(x, y, z):
        h_up = skin_tree.ray_cast(Vector((x, y, z - 0.03)), Vector((0, 0, 1)))
        if h_up[0] is None or h_up[0].z > z + 0.03:
            return z
        hu = skin_tree.ray_cast(Vector((x, y, BED_TOP)), Vector((0, 0, 1)))
        if hu[0] is not None and hu[0].z - 0.028 >= BED_TOP + 0.015:
            return hu[0].z - 0.028
        ht = skin_tree.ray_cast(Vector((x, y, 3.0)), Vector((0, 0, -1)))
        return (ht[0].z + 0.006) if ht[0] is not None else z
    R_ = 2
    Hd = [[max(H[a_][b_] for a_ in range(max(0, i - R_), min(nx, i + R_) + 1) for b_ in range(max(0, j - R_), min(ny, j + R_) + 1))
           for j in range(ny + 1)] for i in range(nx + 1)]
    Z = [[Hd[i][j] + 0.015 for j in range(ny + 1)] for i in range(nx + 1)]
    for _ in range(4):                        # 柔化，但不低于"身体 + 1.2 cm"
        Zn = [[0.0] * (ny + 1) for _ in range(nx + 1)]
        for i in range(nx + 1):
            for j in range(ny + 1):
                acc, cnt = 0.0, 0
                for a_ in (i - 1, i, i + 1):
                    for b_ in (j - 1, j, j + 1):
                        if 0 <= a_ <= nx and 0 <= b_ <= ny:
                            acc += Z[a_][b_]; cnt += 1
                Zn[i][j] = max(acc / cnt, H[i][j] + 0.012, BED_TOP + 0.02)
        Z = Zn
    # 下巴底下：被沿拉到脖子顶面，做成一道平滑的被卷（x 方向从脖子下 15 cm 慢慢升起，y 方向高斯落下），不按单点顶出尖角
    _nk = [v for v in _sv if v.x < neck.x + 0.04]; log(f"脖子顶点 {len(_nk)}，皮肤最靠身体 x={min(v.x for v in _sv):.3f}")
    if _nk:
        Nz = max(v.z for v in _nk) + 0.010
        Ny = sum(v.y for v in _nk) / len(_nk)
        Wy = max(0.12, (max(v.y for v in _nk) - min(v.y for v in _nk)) * 0.5 + 0.06)
        x0r, x1r = neck.x - 0.28, neck.x - 0.01
        for i in range(nx + 1):
            for j in range(ny + 1):
                x, y = XS[i][j], YS[j]
                t = min(1.0, max(0.0, (x - x0r) / (x1r - x0r)))
                t = t * t * (3 - 2 * t)
                g = math.exp(-((y - Ny) / Wy) ** 2)
                Z[i][j] = max(Z[i][j], BED_TOP + (Nz - BED_TOP) * t * g)
        log(f"被沿：拉到脖子顶面 z={Nz:.3f}，y 中心 {Ny:.3f} 半宽 {Wy:.3f}")
    nfix = 0
    for i in range(nx + 1):
        for j in range(ny + 1):
            if XS[i][j] > edge_x - 0.06:
                z2 = head_fix(XS[i][j], YS[j], Z[i][j])
                if abs(z2 - Z[i][j]) > 1e-4:
                    Z[i][j] = z2
                    nfix += 1
    log(f"被子在头附近调整 {nfix} 个点（塞到下巴下 / 盖过头发）")
    DR = 8                                    # 靠屋里一侧沿床垫边垂下去的 8 排
    verts = []
    for i in range(nx + 1):
        x0_ = XS[i][0]
        for k in range(DR):
            sfr = 1 - k / DR
            verts.append((x0_, ya_ - 0.05 * math.sin(sfr * math.pi / 2), Z[i][0] - (Z[i][0] - (BED_TOP - 0.15)) * sfr + 0.003 * math.sin(x0_ * 31)))
        for j in range(ny + 1):
            verts.append((XS[i][j], YS[j], Z[i][j] + 0.003 * math.sin(XS[i][j] * 23 + j * 0.7) * math.sin(j * 1.3)))
    W_ = DR + ny + 1
    faces, fmat = [], []
    for i in range(nx):
        for j in range(W_ - 1):
            faces.append((i * W_ + j, (i + 1) * W_ + j, (i + 1) * W_ + j + 1, i * W_ + j + 1))
            fmat.append(1 if i >= nx - 5 else (2 if i < 14 else 0))     # 上沿翻出白被头；脚那头搭一条毯子
    qm = bpy.data.meshes.new("cab_quilt_sleep")
    qm.from_pydata(verts, [], faces)
    qm.update()
    quilt = bpy.data.objects.new("cab_quilt_sleep", qm)
    P.objects.link(quilt)
    for m in (QUILT, mat("sheet"), mat("throw")):
        qm.materials.append(m)
    for pl, mi in zip(qm.polygons, fmat):
        pl.material_index = mi
    sd = quilt.modifiers.new("厚度", "SOLIDIFY")
    sd.thickness = 0.022
    sd.offset = 1.0
    smooth(quilt)
    show_at(quilt, ("dawn", "late", "wb"))
    log(f"被子：程序生成 {nx}×{W_} 格")

    # --- 橘猫：落在被面上（向下射线找被面）
    qt = bvh_world(quilt)
    cx, cy = BED_X[0] + 0.30, MAT_Y[1] - 0.20
    hit = qt.ray_cast(Vector((cx, cy, 2.0)), Vector((0, 0, -1)))
    cz = (hit[0].z if hit[0] else BED_TOP + 0.05) + 0.004
    cr, cparts = build_cat("cab_cat_sleep", (cx, cy, cz))
    for o in cparts:
        show_at(o, ("dawn", "late", "wb"))

    # --- 头发按重力：在被子底下的删掉（看不见）；插进被子边的搭在被面上；陷进枕头 / 床垫的抬到表面上
    pt = bvh_world(pillow)
    mt = bvh_world(bpy.data.objects["cab_mattress"])
    n_del = n_up = n_pil = n_mat = 0
    for o in LIE_OBJS:
        is_hair = o.name[4:].startswith(HEAD_PREFIX)
        bm_ = bmesh.new()
        bm_.from_mesh(o.data)
        dels = []
        for v in bm_.verts:
            q = v.co
            up_ = qt.ray_cast(q + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))
            dn_ = qt.ray_cast(q - Vector((0, 0, 0.0005)), Vector((0, 0, -1)))
            in_slab = up_[0] is not None and dn_[0] is not None and up_[0].z - dn_[0].z < 0.03
            if (not is_hair) and (q - hc).length > 0.09 and (in_slab or up_[0] is not None):
                dels.append(v); n_del += 1        # 脖子伸进被子里的那一截皮肤：在被子下面，删掉
                continue
            if is_hair and ((up_[0] is not None and not in_slab) or ((q - hc).length > 0.14 and q.x < ext_x)):
                dels.append(v); n_del += 1        # 在被子底下 / 顺着背的长发：整根塞在被子里，看不见
                continue
            for _it in range(3):                  # 床垫 → 枕头 → 被面，依次推到表面外，重复 3 遍
                moved = False
                for tree, tag_ in ((mt, "m"), (pt, "p")):
                    loc, nrm, _, dist = tree.find_nearest(v.co)
                    if loc is not None and dist < 0.3 and (v.co - loc).dot(nrm) < 0.0015:
                        v.co = loc + nrm * 0.003; moved = True
                        if tag_ == "m":
                            n_mat += 1
                        else:
                            n_pil += 1
                if is_hair:
                    up_ = qt.ray_cast(v.co + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))
                    dn_ = qt.ray_cast(v.co - Vector((0, 0, 0.0005)), Vector((0, 0, -1)))
                    if up_[0] is not None and dn_[0] is not None and up_[0].z - dn_[0].z < 0.03:
                        v.co.z = up_[0].z + 0.004; moved = True; n_up += 1
                if not moved:
                    break
            else:
                pass
            bad = False                           # 三遍后还卡在任何表面里：删掉这个点
            for tree in (mt, pt):
                loc, nrm, _, dist = tree.find_nearest(v.co)
                if loc is not None and dist < 0.3 and (v.co - loc).dot(nrm) < -0.001:
                    bad = True
            if is_hair:
                up_ = qt.ray_cast(v.co + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))
                dn_ = qt.ray_cast(v.co - Vector((0, 0, 0.0005)), Vector((0, 0, -1)))
                if up_[0] is not None and dn_[0] is not None and up_[0].z - dn_[0].z < 0.03:
                    bad = True
            if bad and is_hair:
                dels.append(v); n_del += 1
        if dels:
            bmesh.ops.delete(bm_, geom=dels, context="VERTS")
        bm_.to_mesh(o.data)
        bm_.free()
        o.data.update()
    log(f"头发：被子下删 {n_del}、搭到被面上 {n_up}、抬出枕头 {n_pil}、抬出床垫 {n_mat} 个顶点")
    head = [v.co.copy() for o in LIE_OBJS for v in o.data.vertices]
    allp = list(head)

    # --- 穿模检查（全部顶点）
    pt = bvh_world(pillow)
    mt = bvh_world(bpy.data.objects["cab_mattress"])
    exposed = inside_p = inside_m = near_q = 0
    ex_by = {}
    ex_pts = []
    ring = []
    for o in LIE_OBJS:
        if o.name[4:].startswith(HEAD_PREFIX):
            continue
        bm_ = bmesh.new()
        bm_.from_mesh(o.data)
        ring += [(v.co.copy(), o.name) for v in bm_.verts if v.is_boundary and (v.co - hc).length > 0.12]
        bm_.free()
    for p, nm in ring:                        # 脖子切口：必须盖在被子下面
        if qt.ray_cast(p + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))[0] is None:
            exposed += 1
            ex_by[nm] = ex_by.get(nm, 0) + 1
            ex_pts.append(p)
    if ex_by:
        log(f"露出的点按网格：{sorted(ex_by.items(), key=lambda t: -t[1])[:8]}")
        log(f"露出的点范围 x[{min(q.x for q in ex_pts):.3f},{max(q.x for q in ex_pts):.3f}] y[{min(q.y for q in ex_pts):.3f},{max(q.y for q in ex_pts):.3f}] "
            f"z[{min(q.z for q in ex_pts):.3f},{max(q.z for q in ex_pts):.3f}]；头心 {tuple(round(c, 3) for c in hc)}，脖子 {tuple(round(c, 3) for c in neck)}")
    for p in allp:
        for tree, kind in ((pt, "p"), (mt, "m")):
            loc, nrm, _, dist = tree.find_nearest(p)
            if loc is not None and dist < 0.3 and (p - loc).dot(nrm) < -0.001:
                if kind == "p":
                    inside_p += 1
                else:
                    inside_m += 1
        loc, nrm, _, dist = qt.find_nearest(p)
        if loc is not None and dist < 0.006:
            near_q += 1
    head_in_q = 0
    for p in head:
        up_ = qt.ray_cast(p + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))
        dn_ = qt.ray_cast(p - Vector((0, 0, 0.0005)), Vector((0, 0, -1)))
        if up_[0] is not None and dn_[0] is not None and (up_[0].z - dn_[0].z) < 0.03:
            head_in_q += 1                    # 夹在被子上下两面之间 = 头 / 头发插进被子里
    log(f"头 / 头发插进被子：{head_in_q}")
    SLEEP_REPORT["head_inside_quilt"] = head_in_q
    hb_hit = sum(1 for p in allp if p.x > HB_FACE - 0.005)
    fb_hit = sum(1 for p in allp if p.x < FB_FACE + 0.005)
    SLEEP_REPORT.update(body_vertices=len(body), head_vertices=len(head), exposed_body=exposed,
                        in_pillow=inside_p, in_mattress=inside_m, quilt_closer_than_6mm=near_q,
                        past_headboard=hb_hit, past_footboard=fb_hit)
    log(f"穿模检查：身体 {len(body)} 点，露在被子外 {exposed}；进枕头 {inside_p}；进床垫 {inside_m}；"
        f"被子离人物 <6mm {near_q}；碰床头 {hb_hit}；碰床尾 {fb_hit}")
    return SC_, rig, root


try:
    with bpy.data.libraries.load(CHAR_SRC, link=False) as (src, dst):
        dst.actions = [a for a in src.actions if a in ("CLIP_A1_idle", "CLIP_C3_fire_loop")]
    ACT = {a.name.split(".")[0]: a for a in dst.actions}
    log(f"动作：{list(ACT)}")
    CH, rig, root = build_sleep()
    CH_INFO["lie"] = dict(coll=CH, rig=rig, root=root)
    lamp_lit_toon(CH)
    add_breath(CH)
    sc.frame_set(1)
    for tag in ("stand", "seat"):
        CH, rig, root = load_copy(tag)
        root.animation_data_clear()
        root.rotation_mode = "XYZ"
        root.location = (0, 0, 0)
        root.rotation_euler = (0, 0, 0)
        assign(rig, ACT["CLIP_C3_fire_loop" if tag == "seat" else "CLIP_A1_idle"])
        sc.frame_set(1)
        bpy.context.view_layer.update()
        if tag == "stand":
            root.rotation_euler = (0, 0, math.radians(-28))
            root.location = (0.05, -0.45, 0.0)
        elif B1:
            build_b1(CH, rig, root)
            lamp_lit_toon(CH)
        else:
            p = pelvis_w(rig)
            root.location = (CHAIR_C[0] - p.x, CHAIR_C[1] + 0.02 - p.y, CHAIR_SEAT + SEAT_HIP - hip_joint_z(rig))
        bpy.context.view_layer.update()
        if not (B1 and tag == "seat"):
            bake_pose(rig)
        _k = 1.0 if (B1 and tag == "seat") else float(os.environ.get("GSD_CAPE_KEEP", CAPE_KEEP))   # B1 带动画，斗篷交给摆动模拟
        log(f"人物 {tag}：斗篷收拢 {relax_cape(rig, _k) if _k < 1 else 0} 节骨骼（保留 {_k}）")
        log(f"人物 {tag}：隐藏袖子 / 衣服底下的皮肤 {hide_covered_skin(CH)} 个顶点；里层穿出长袍 {cloth_poke(CH)}")
        mn, mx = wbbox([o for o in CH.all_objects if o.type == "MESH" and o.visible_get()])
        log(f"人物 {tag}：骨架 {rig.name}，包围盒 {tuple(round(v, 2) for v in mn)} → {tuple(round(v, 2) for v in mx)}")
        hats = hat_parts(CH)
        if tag == "stand" and hats:
            dg = bpy.context.evaluated_depsgraph_get()
            for h in hats:
                he = h.evaluated_get(dg)
                me = bpy.data.meshes.new_from_object(he, preserve_all_data_layers=True, depsgraph=dg)
                o = bpy.data.objects.new("cab_hat_" + h.name.split(".")[0], me)
                COL["PROPS"].objects.link(o)
                o.matrix_world = he.matrix_world.copy()
                HAT_ON_STAND.append(o)
            bpy.context.view_layer.update()
            hmn, hmx = wbbox(HAT_ON_STAND)
            hroot = empty("cab_hat_root", ((hmn.x + hmx.x) / 2, (hmn.y + hmx.y) / 2, hmn.z), COL["PROPS"])
            bpy.context.view_layer.update()
            # 记下复制帽子那一刻头骨的世界矩阵和帽子根的世界矩阵：之后任意一帧「帽子戴在头上」= H(f) @ H0⁻¹ @ R0（G5 戴帽用）
            HAT_INFO["H0"] = (rig.matrix_world @ rig.pose.bones["head.x"].matrix).copy()
            HAT_INFO["R0"] = hroot.matrix_world.copy()
            HAT_INFO["root"] = hroot
            for o in HAT_ON_STAND:
                parent_keep(o, hroot)
            hroot.location = (COATSTAND_C[0], COATSTAND_C[1], 1.79 * CS_K - (hmx.z - hmn.z) * 0.62)
            hroot.rotation_euler = (math.radians(7), math.radians(-5), math.radians(40))
        for h in hats:
            h.hide_render = True
            h.hide_viewport = True
        CH_INFO[tag] = dict(coll=CH, rig=rig, root=root)
    show_at(CH_INFO["seat"]["coll"], ("night", "wb"))
    show_at(CH_INFO["stand"]["coll"], ("day", "wb"))
    show_at(CH_INFO["lie"]["coll"], ("dawn", "late", "wb"))
except Exception as e:
    import traceback
    log("人物追加失败：" + repr(e) + "\n" + traceback.format_exc())

# ============================================================ 标注（只在俯视图出现）
FONT = None
try:
    FONT = bpy.data.fonts.load(FONT_PATH)
except Exception as e:
    log(f"字体载入失败：{e}")
MK = COL["MARKS"]
M_TXT = flat("M_text", (0.10, 0.09, 0.12))
M_PLATE = flat("M_plate", (1.0, 1.0, 0.98))
M_GRID = flat("M_grid", (0.25, 0.25, 0.30))


def label(text, x, y, size=0.095, z=2.62, plate=True, rot=0.0):
    cu = bpy.data.curves.new("lbl", "FONT")
    cu.body = text
    cu.size = size
    if FONT:
        cu.font = FONT
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new("mk_lbl", cu)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, rot)
    MK.objects.link(ob)
    cu.materials.append(M_TXT)
    if plate:
        bpy.context.view_layer.update()
        d = ob.dimensions
        pw, ph = (d.x + 0.06, d.y + 0.04) if abs(rot) < 0.1 else (d.y + 0.04, d.x + 0.06)
        box("mk_plate", MK, M_PLATE, (x, y, z - 0.01), (pw, ph, 0.004), bv=0.0)
    return ob


SPOTS = {
    "door":      dict(pos=(-1.55, 1.40, 0.0), h=180, col=(0.90, 0.30, 0.28), txt="门口 · 进出门 G7", off=(0.0, -0.32)),
    "hatstand":  dict(pos=(-1.95, 1.12, 0.0), h=-152, col=(0.95, 0.60, 0.20), txt="衣帽架 · 摘 / 戴帽 G5", off=(-0.05, -0.30)),
    "desk_seat": dict(pos=(CHAIR_C[0], CHAIR_C[1], CHAIR_SEAT), h=0, col=(0.25, 0.48, 0.90), txt="书桌坐 · 学习 B1", off=(0.0, 0.0)),
    "desk_front": dict(pos=(-0.45, 1.17, 0.0), h=0, col=(0.45, 0.65, 0.95), txt="坐下 / 起身 A4", off=(0.55, 0.05)),
    "center":    dict(pos=(0.05, -0.45, 0.0), h=-28, col=(0.30, 0.70, 0.35), txt="中央站位 · 挥手 B2 / 欢呼 B3 / 哈欠 C4", off=(0.0, -0.36)),
    "bed":       dict(pos=(1.55, BED_CY, BED_TOP), h=0, col=(0.55, 0.35, 0.75), txt="床 · 睡觉 D2 / 赖床 G1 / 揉眼坐起 G3", off=(0.0, 0.0)),
    "bed_edge":  dict(pos=(1.30, 0.42, 0.0), h=0, col=(0.70, 0.45, 0.85), txt="床边 · 上床 D1 / 坐床边伸懒腰 G4", off=(0.0, -0.30)),
    "window_e":  dict(pos=(1.98, -0.55, 0.0), h=90, col=(0.20, 0.70, 0.75), txt="东窗 · 拉窗帘 G6", off=(-0.62, 0.0)),
    "stove":     dict(pos=(1.50, -1.38, 0.0), h=85, col=(0.65, 0.40, 0.25), txt="火炉（夜里的暖光）", off=(-0.55, -0.20)),
}
PATHS = {
    "进门 → 中央": [(-1.55, 1.40), (-1.40, 0.55), (-1.05, -0.10), (-0.45, -0.40), (0.05, -0.45)],
    "进门 → 书桌": [(-1.55, 1.40), (-1.10, 1.25), (-0.45, 1.17)],
    "书桌 → 床边": [(-0.45, 1.17), (-1.20, 1.15), (-1.32, 0.62), (-1.12, 0.08), (0.30, 0.04), (1.00, 0.28), (1.30, 0.50)],   # 绕书桌西、南边走（桌子和床之间只有 35 cm，穿不过去）
    "床边 → 东窗": [(1.30, 0.50), (1.80, 0.05), (1.98, -0.55)],
    "东窗 → 衣帽架": [(1.98, -0.55), (0.90, -0.78), (-0.50, -0.25), (-1.35, 0.45), (-1.95, 1.12)],
    "衣帽架 → 门": [(-1.95, 1.12), (-1.55, 1.40)],
}
PATH_COL = [(0.30, 0.70, 0.35), (0.25, 0.48, 0.90), (0.70, 0.45, 0.85), (0.20, 0.70, 0.75), (0.95, 0.60, 0.20), (0.90, 0.30, 0.28)]


def build_marks():
    for name, s in SPOTS.items():
        x, y, z = s["pos"]
        m = flat("M_" + name, s["col"])
        cyl("mk_disc_" + name, MK, m, (x, y, z + 0.03), 0.15, 0.012, seg=28, sm=False)
        h = math.radians(s["h"])
        fx, fy = math.sin(h), -math.cos(h)
        o = cyl("mk_arrow_" + name, MK, m, (x + fx * 0.2, y + fy * 0.2, z + 0.04), 0.07, 0.16, seg=3, r2=0.0, sm=False)
        o.rotation_euler = (math.pi / 2, 0, math.atan2(fy, fx) - math.pi / 2)
        o.rotation_euler = Euler((math.pi / 2, 0, 0)).to_matrix().to_4x4().to_euler()
        o.rotation_mode = "XYZ"
        o.rotation_euler = (-math.pi / 2, 0, math.atan2(fy, fx) - math.pi / 2)
        label(s["txt"], x + s["off"][0], y + s["off"][1])
    for i, (nm, pts) in enumerate(PATHS.items()):
        m = flat(f"M_path{i}", PATH_COL[i])
        tube(f"mk_path{i}", MK, m, [(px, py, 0.05) for px, py in pts], 0.02)
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        o = cyl(f"mk_path_arrow{i}", MK, m, (bx, by, 0.06), 0.05, 0.12, seg=3, r2=0.0, sm=False)
        o.rotation_euler = (-math.pi / 2, 0, math.atan2(by - ay, bx - ax) - math.pi / 2)
    # 1 米网格
    g = []
    for gx in range(-2, 3):
        g.append(((gx, 0, 0.022), (0.012, 2 * IY, 0.003), 0.0))
    for gy in range(-1, 2):
        g.append(((0, gy, 0.022), (2 * IX, 0.012, 0.003), 0.0))
    boxes("mk_grid", MK, M_GRID, g)
    for gx in range(-2, 3):
        label(f"x={gx}", gx, -IY - 0.42, size=0.08)
    for gy in range(-1, 2):
        label(f"y={gy}", -IX - 0.55, gy, size=0.08)
    label("北墙 = 木屋正面（门 + 两扇窗）", -0.2, IY + 0.40, size=0.10)
    label("东墙 = 山墙（两扇窗）", IX + 0.46, 0.0, size=0.10, rot=math.pi / 2)
    label("近处两面墙切到地板高度（剖面）· 1 格 = 1 米", 0.0, -IY - 0.72, size=0.09)
    # 主镜头方向
    m = flat("M_cam", (0.15, 0.15, 0.18))
    tube("mk_cam_dir", MK, m, [(-3.15, -2.45, 0.1), (-2.65, -1.52, 0.1)], 0.02, smooth_curve=False)
    o = cyl("mk_cam_arrow", MK, m, (-2.6, -1.43, 0.1), 0.06, 0.14, seg=3, r2=0.0, sm=False)
    o.rotation_euler = (-math.pi / 2, 0, math.atan2(0.88, 0.47) - math.pi / 2)
    label("主镜头视线", -2.75, -2.55, size=0.085)


build_marks()
MK.hide_render = True

# ============================================================ 镜头
def cam_basis(az, el):
    az, el = math.radians(az), math.radians(el)
    back = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    f = -back
    r = f.cross(Vector((0, 0, 1))).normalized()
    u = r.cross(f).normalized()
    return back, f, r, u


def fit_main():
    back, f, r, u = cam_basis(CAM_AZ, CAM_EL)
    obs = [o for c in ("ROOM", "FURN", "BASE") for o in COL[c].all_objects if o.type == "MESH" and not o.name.startswith(("cab_backdrop", "cab_deskonly"))]   # 窗外背景板、近景专用西墙不算进主镜头取景
    dg = bpy.context.evaluated_depsgraph_get()
    rs, us, who = [], [], []
    for o in obs:
        oe = o.evaluated_get(dg)
        pts = [v.co for v in oe.data.vertices] if o.name == "cab_island" else [Vector(c) for c in oe.bound_box]
        for c in pts:
            p = oe.matrix_world @ c
            rs.append(p.dot(r)); us.append(p.dot(u)); who.append(o.name)
    r0, r1, u0, u1 = min(rs), max(rs), min(us), max(us)
    log(f"取景边界物体：左 {who[rs.index(r0)]} 右 {who[rs.index(r1)]} 下 {who[us.index(u0)]} 上 {who[us.index(u1)]}")
    shift = 0.035
    width = max((r1 - r0) * 1.06 / (1 - 2 * shift), (u1 - u0) * 1.06 / (RES_Y / RES_X))
    cr, cu = (r0 + r1) / 2, (u0 + u1) / 2
    T = r * cr + u * cu
    cd = bpy.data.cameras.new("CAM_main")
    cd.type = "ORTHO"
    cd.ortho_scale = width
    cd.shift_x = shift
    cd.clip_end = 200
    cam = bpy.data.objects.new("CAM_main", cd)
    sc.collection.objects.link(cam)
    cam.location = T + back * 40
    cam.rotation_euler = (-f).to_track_quat("Z", "Y").to_euler()
    log(f"主镜头：正交 {width:.2f} m，画面中心 {tuple(round(v, 2) for v in T)}，范围 r[{r0:.2f},{r1:.2f}] u[{u0:.2f},{u1:.2f}]")
    return cam, width, T


CAM_MAIN, CAM_W, CAM_T = fit_main()
cdt = bpy.data.cameras.new("CAM_top")
cdt.type = "ORTHO"
cdt.ortho_scale = 7.2
CAM_TOP = bpy.data.objects.new("CAM_top", cdt)
CAM_TOP.location = (-0.05, 0.0, 20.0)
sc.collection.objects.link(CAM_TOP)

# --- 书桌镜头候选：桌子前侧方、对着坐在椅子上的伊蕾娜（透视），学习 B1 用
DESK_LOOK = Vector((CHAIR_C[0], CHAIR_C[1] - 0.12, CHAIR_SEAT + 0.55))     # 胸口偏上，脸和桌面都在画里
DESK_CAMS = {
    "A_right34": dict(loc=(0.30, -0.10, 1.55), lens=38, look=(-0.45, 1.05, 0.98)),   # 桌前偏右一点、略高，基本正对她，从显示器上方看到脸
    "B_left34":  dict(loc=(-1.65, 0.35, 1.20), lens=38),    # 左前侧，从台灯外侧看过去，不挡脸
    "C_front":   dict(loc=(-0.25, -0.55, 1.45), lens=45),   # 正前方略偏右，稍俯
    "D_high_desk": dict(loc=(0.20, 0.00, 1.80), lens=35),   # 右前上方，俯看桌面 + 脸（书、手都在画里）
    "E_monitor": dict(loc=(MON_C[0], -0.60, 1.42), lens=40, look=(MON_C[0], 1.13, 0.95)),   # 显示器正对的方向、在显示器背后：屏幕上沿挡到她胸口
}
DESK_CAM_OBJS = {}
for nm_, cfg_ in DESK_CAMS.items():
    cd_ = bpy.data.cameras.new("CAM_desk_" + nm_)
    cd_.lens = cfg_["lens"]
    cd_.clip_start, cd_.clip_end = 0.05, 60
    co_ = bpy.data.objects.new("CAM_desk_" + nm_, cd_)
    sc.collection.objects.link(co_)
    co_.location = cfg_["loc"]
    co_.rotation_euler = (Vector(cfg_.get("look", DESK_LOOK)) - Vector(cfg_["loc"])).to_track_quat("-Z", "Y").to_euler()
    DESK_CAM_OBJS[nm_] = co_


# ================================================================== B6 完成任务后对着镜头笑（一次性，首尾 = B1 第 1 帧）
B6_N, B6_IN, B6_OUT = 96, 18, 16
B6_NECK = 0.40                          # 转头：脖子分 40%，头 60%
B6_MAX_TURN = 55.0                      # 最多转 55°
SMILE_JAW = -4.0                        # 下巴往上合 4°（打字时嘴微张）
SMILE_LOC = {"c_lips_smile.l": (0.004, 0.002, 0.011), "c_lips_smile.r": (-0.004, 0.002, 0.011)}   # 嘴角往外、往后、往上（骨架空间，下面换算到各骨骼本地轴；.r 的本地轴是镜像的）
SMILE_ROT = (("eyelid_bot.l", -13.0), ("eyelid_bot.r", -13.0), ("eyelid_top.l", 5.0), ("eyelid_top.r", 5.0),
             ("jawbone.x", SMILE_JAW))   # 温柔的笑：眼睛微微弯、嘴合上（11-25 用户：原来笑得太诡异）
B6_TILT = 14.0                          # 看镜头时可爱地歪一下头（绕脸朝向的轴；原作截图歪得比较明显）
B6_INFO = {}


def _eye_center(CH):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in CH.all_objects:
        if o.type == "MESH" and o.name.split(".")[0] == "eye" and not o.hide_render:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            pts += [oe.matrix_world @ v.co for v in me.vertices]
            oe.to_mesh_clear()
    return sum(pts, Vector()) / len(pts) if pts else None


def _head_center(rig):
    hb = rig.pose.bones["head.x"]
    return rig.matrix_world @ (hb.head + (hb.tail - hb.head) * 0.55)


def build_smile(cam_nm):
    info = CH_INFO.get("seat")
    if not info:
        return
    CH, rig = info["coll"], info["rig"]
    cam = DESK_CAM_OBJS[cam_nm]
    b1 = bpy.data.actions["CLIP_B1_study"]
    assign(rig, b1)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    P0 = _sample_act(b1, 1, rig)[0]
    # --- 解出「看镜头」的脖子 / 头姿势：在 B1 第 1 帧的姿势上，绕骨骼头部在骨架空间里转
    keep = {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones}
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis = keep[pb.name]
    bpy.context.view_layer.update()
    hc, ec = _head_center(rig), _eye_center(CH)
    fwd = (ec - hc).normalized()
    tgt = (cam.matrix_world.translation - hc).normalized()
    ang0 = math.degrees(fwd.angle(tgt))
    rot = fwd.rotation_difference(tgt)
    axis, ang = rot.to_axis_angle()
    ang = min(ang, math.radians(B6_MAX_TURN))
    A3i = rig.matrix_world.to_3x3().normalized().inverted()
    ax_a = (A3i @ axis).normalized()
    for bn, frac in (("neck.x", B6_NECK), ("head.x", 1.0 - B6_NECK)):
        pb = rig.pose.bones[bn]
        pb.rotation_mode = "QUATERNION"
        h_ = pb.head.copy()
        pb.matrix = Matrix.Translation(h_) @ Quaternion(ax_a, ang * frac).to_matrix().to_4x4() @ Matrix.Translation(-h_) @ pb.matrix
        bpy.context.view_layer.update()
    look = {bn: rig.pose.bones[bn].rotation_quaternion.copy() for bn in ("neck.x", "head.x")}
    hc2, ec2 = _head_center(rig), _eye_center(CH)
    ang1 = math.degrees((ec2 - hc2).normalized().angle((cam.matrix_world.translation - hc2).normalized()))
    for pb in rig.pose.bones:
        pb.matrix_basis = keep[pb.name]
    bpy.context.view_layer.update()
    # --- 表情：嘴角上扬 + 眯眼（骨骼本地空间）
    B = rig.data.bones
    up_ = (B["neck.x"].head_local - B["root.x"].head_local).normalized()
    left_ = B["arm_stretch.l"].head_local - B["arm_stretch.r"].head_local
    left_ = (left_ - up_ * left_.dot(up_)).normalized()
    frames = []
    hold = B6_N - B6_IN - B6_OUT
    for i in range(B6_N):
        if i < B6_IN:
            w = _ease(i / B6_IN)
        elif i >= B6_N - B6_OUT:
            w = _ease((B6_N - 1 - i) / B6_OUT)
        else:
            w = 1.0
        P = dict(P0)
        for bn in ("neck.x", "head.x"):
            l_, q0 = P0.get(bn, _Z0)
            q1 = look[bn].copy()
            q1.make_compatible(q0)
            P[bn] = (l_, q0.slerp(q1, w))
        # 停住看镜头时轻轻点一下头（整数个周期，进出时为 0）
        if B6_IN <= i < B6_N - B6_OUT:
            t_ = (i - B6_IN) / hold
            nod = 1.5 * math.sin(2 * math.pi * t_) * math.sin(math.pi * t_)
            if "head.x" in B:
                ax_ = (B["head.x"].matrix_local.to_3x3().inverted() @ left_).normalized()
                l_, q_ = P["head.x"]
                P["head.x"] = (l_, Quaternion(ax_, math.radians(nod)) @ q_)
        if "head.x" in B and w > 0:          # 歪头
            front_ = left_.cross(up_).normalized()
            ax_ = (B["head.x"].matrix_local.to_3x3().inverted() @ front_).normalized()
            l_, q_ = P["head.x"]
            P["head.x"] = (l_, Quaternion(ax_, math.radians(B6_TILT * w)) @ q_)
        ws = _ease(min(1.0, i / (B6_IN + 8))) if i < B6_N - B6_OUT else _ease((B6_N - 1 - i) / B6_OUT)
        for bn, d in SMILE_LOC.items():
            if bn in B:
                l_, q_ = P0.get(bn, _Z0)
                d_loc = B[bn].matrix_local.to_3x3().inverted() @ Vector(d)      # 骨架空间 → 骨骼本地
                P[bn] = (l_ + d_loc * ws, q_)
        for bn, deg in SMILE_ROT:
            if bn in B:
                ax_ = (B[bn].matrix_local.to_3x3().inverted() @ left_).normalized()
                l_, q_ = P0.get(bn, _Z0)
                P[bn] = (l_, Quaternion(ax_, math.radians(deg * ws)) @ q_)
        frames.append(P)
    act = _write_clip(rig, f"CLIP_B6_smile_{cam_nm}", frames)
    assign(rig, b1)
    sc.frame_set(1)
    B6_INFO[cam_nm] = dict(turn_needed=round(ang0, 1), turn_used=round(math.degrees(ang), 1), gaze_error_after=round(ang1, 1))
    log(f"B6 对镜头笑（{cam_nm}）：{B6_N} 帧；视线要转 {ang0:.1f}°，实际转 {math.degrees(ang):.1f}°，转完视线偏差 {ang1:.1f}°；首尾 = B1 第 1 帧")
    return act


# ================================================================== B6 v2（11-25 用户给的描述）：双手合十在下巴下、开心地紧闭眼 → 睁大眼、眼里星光、大大的笑；身边金色 / 黄绿色星光
B6_N = 120
# B6 v3：按用户给的原作截图一比一（11-26）：双手合掌贴在右脸颊旁、张大嘴的 D 形大笑、眉毛上扬、
# 瞳孔中央一颗黄色四角星 + 左上白色高光、脸颊红晕、身边几颗饱和黄色四角星
B6_EYE_SPARK = (1.0, 1.0, 1.0)            # 眼睛左上的小白高光
B6_EYE_STAR = (1.0, 0.84, 0.12)           # 瞳孔中央的黄色四角星
B6_SPARK_COLS = ((1.0, 0.86, 0.16), (1.0, 0.92, 0.34), (1.0, 0.80, 0.10))
B6_BLUSH = (1.0, 0.38, 0.45)
B6_HAND = dict(up=-0.05, fwd=0.11, side=0.11, gap=0.035)   # 合掌中心：head.x 起点（≈下巴高）往下 / 往前 / 往右多少；两手腕间距
B6_MOUTH = dict(jaw=16.0, cx=0.016, cy=0.008, top=0.002, bot=0.004, out=0.005, lid=-8.0)   # 微张的开心笑（用户 11-26：嘴别张那么大）
B6_BROW = (("c_eyebrow_01", 0.004), ("c_eyebrow_03", 0.006), ("c_eyebrow_01_end", 0.003))
B6_FX = {}             # 相机名 → 特效集合（只在渲这个相机的 B6 时打开）


def _ramp(i, a, b):
    """i 在 [a, b] 之间从 0 缓到 1"""
    return _ease((i - a) / max(1e-6, b - a))


def _win(i, a0, a1, b0, b1):
    """a0→a1 缓入，b0→b1 缓出"""
    return min(_ramp(i, a0, a1), 1.0 - _ramp(i, b0, b1))


def _two_bone_ik(rig, side, target_a, pole_a):
    """骨架空间两节 IK：arm_stretch / forearm_stretch，手腕（hand 头）到 target_a；pole_a = 手肘朝向"""
    pa, pf, ph = (rig.pose.bones[f"{n}.{side}"] for n in ("arm_stretch", "forearm_stretch", "hand"))
    S = pa.head.copy()
    L1 = (pf.head - pa.head).length
    L2 = (ph.head - pf.head).length
    d_ = target_a - S
    dist = min(max(d_.length, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    dir_ = d_.normalized()
    a_ = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist)
    h_ = math.sqrt(max(0.0, L1 * L1 - a_ * a_))
    p_ = (pole_a - dir_ * pole_a.dot(dir_)).normalized()
    E = S + dir_ * a_ + p_ * h_
    T_ = S + dir_ * dist
    for pb, want in ((pa, E), (pf, T_)):
        bpy.context.view_layer.update()
        head_ = pb.head.copy()
        child = pf if pb is pa else ph
        cur = child.head - head_
        q = cur.rotation_difference(want - head_)
        pb.matrix = Matrix.Translation(head_) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head_) @ pb.matrix
    bpy.context.view_layer.update()
    return (ph.head - target_a).length


def _orient_hand(rig, side, dir_want, palm_want):
    """把手转到：手指方向 dir_want、掌心朝 palm_want（骨架空间）"""
    bpy.context.view_layer.update()
    ph = rig.pose.bones[f"hand.{side}"]
    P_ = lambda n: rig.pose.bones[f"{n}.{side}"].head.copy() if f"{n}.{side}" in rig.pose.bones else None
    mid, idx, pk = P_("middle1"), P_("index1"), P_("pinky1")
    if mid is None or idx is None or pk is None:
        return
    tips = [rig.pose.bones[f"c_{n}3.{side}"].tail for n in ("index", "middle", "ring", "pinky") if f"c_{n}3.{side}" in rig.pose.bones]   # 指尖（第三节）：弯向掌心的方向最明显
    hd = (mid - ph.head).normalized()
    across = (idx - pk)
    across = (across - hd * across.dot(hd)).normalized()
    nrm = hd.cross(across).normalized()
    curl = sum(tips, Vector()) / len(tips) - (idx + mid + pk) / 3
    if nrm.dot(curl) < 0:
        nrm = -nrm
    Mc = Matrix((hd, nrm, hd.cross(nrm))).transposed()
    dw = dir_want.normalized()
    pw = (palm_want - dw * palm_want.dot(dw)).normalized()
    Mt = Matrix((dw, pw, dw.cross(pw))).transposed()
    R = (Mt @ Mc.transposed()).to_4x4()
    h_ = ph.head.copy()
    ph.matrix = Matrix.Translation(h_) @ R @ Matrix.Translation(-h_) @ ph.matrix
    bpy.context.view_layer.update()


def _star_mesh(name, r_out, r_in, n=4):
    vs = [(0.0, 0.0, 0.0)]
    for k in range(2 * n):
        r = r_out if k % 2 == 0 else r_in
        a = math.pi * k / n + math.pi / 2
        vs.append((r * math.cos(a), r * math.sin(a), 0.0))
    fs = [(0, 1 + k, 1 + (k + 1) % (2 * n)) for k in range(2 * n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    return me


def _spark_mat(name, rgb, strength):
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(rgb), 1)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    return m


def _disc_mesh(name, n=32):
    vs = [(0.0, 0.0, 0.0)] + [(math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n), 0.0) for k in range(n)]
    fs = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    return me


def _blush_mat(name, rgb):
    """粉色红晕：中心不透明度 0.5、往边缘渐隐到 0（物体坐标半径 1）"""
    m = _new_material(name)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.15
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = 0.7
    mr.inputs["To Max"].default_value = 0.0
    mr.interpolation_type = "SMOOTHSTEP"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(rgb), 1)
    em.inputs["Strength"].default_value = 1.1
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tc.outputs["Object"], ln.inputs[0])
    nt.links.new(ln.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mx.inputs[1])
    nt.links.new(em.outputs["Emission"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    try:
        m.surface_render_method = "BLENDED"
    except (AttributeError, TypeError):
        pass
    m.diffuse_color = (*lin(rgb), 0.4)
    return m


def _key_obj(ob, frames):
    """frames: [(帧号, location, rotation_euler, scale)]，每帧一个关键帧（线性）"""
    for f_, loc, rot, scl in frames:
        ob.location, ob.rotation_euler, ob.scale = loc, rot, scl
        for path in ("location", "rotation_euler", "scale"):
            ob.keyframe_insert(path, frame=f_)


def build_b6_magic(cam_nm):
    info = CH_INFO.get("seat")
    if not info:
        return
    CH, rig = info["coll"], info["rig"]
    cam = DESK_CAM_OBJS[cam_nm]
    bpy.context.view_layer.update()            # 相机刚建好，不刷新的话 matrix_world 还是原点（第一版 E 就因此看向地板）
    camp = cam.matrix_world.translation.copy()
    b1 = bpy.data.actions["CLIP_B1_study"]
    assign(rig, b1)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    P0 = _sample_act(b1, 1, rig)[0]
    keep = {pb.name: pb.matrix_basis.copy() for pb in rig.pose.bones}
    rig.animation_data.action = None

    def reset():
        for pb in rig.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.matrix_basis = keep[pb.name]
        bpy.context.view_layer.update()
    reset()
    A3i = rig.matrix_world.to_3x3().normalized().inverted()
    Aw_i = rig.matrix_world.inverted()
    B = rig.data.bones
    # --- 1) 看镜头（脖子 40% + 头 60%）
    hc, ec = _head_center(rig), _eye_center(CH)
    fwd = (ec - hc).normalized()
    rot = fwd.rotation_difference((camp - hc).normalized())
    axis, ang = rot.to_axis_angle()
    ang = min(ang, math.radians(B6_MAX_TURN))
    ax_a = (A3i @ axis).normalized()
    for bn, frac in (("neck.x", B6_NECK), ("head.x", 1.0 - B6_NECK)):
        pb = rig.pose.bones[bn]
        h_ = pb.head.copy()
        pb.matrix = Matrix.Translation(h_) @ Quaternion(ax_a, ang * frac).to_matrix().to_4x4() @ Matrix.Translation(-h_) @ pb.matrix
        bpy.context.view_layer.update()
    # --- 2) 双手合在下巴下（IK）：手腕在脖子前下方，手指朝上、掌心相对
    pbn = rig.pose.bones
    M3 = rig.matrix_world.to_3x3()
    up_w = Vector((0, 0, 1))                                   # 用世界的上 / 水平前方：打字时身体前倾，用身体自己的「上」会把手放得太低
    left_w = M3 @ (pbn["arm_stretch.l"].head - pbn["arm_stretch.r"].head)
    left_w.z = 0
    left_w.normalize()
    front_w = left_w.cross(up_w).normalized()
    head_w = rig.matrix_world @ pbn["head.x"].head
    # 合掌：两手掌心相对贴在一起，举到她右脸颊旁（手腕约在下巴高度），手指朝上、往脸那边斜
    ctr_w = head_w + up_w * B6_HAND["up"] + front_w * B6_HAND["fwd"] - left_w * B6_HAND["side"]
    dir_w = (up_w * 0.88 + left_w * 0.20 + front_w * 0.12).normalized()
    n_pair = (left_w - dir_w * left_w.dot(dir_w)).normalized()     # 两手相对的方向（指向她左边）
    to_a = lambda v: (A3i @ v)
    err = {}
    for side, sg in (("l", 1.0), ("r", -1.0)):
        tgt = Aw_i @ (ctr_w + n_pair * sg * B6_HAND["gap"] * 0.5)
        pole = to_a(-up_w * 1.0 + left_w * sg * 0.7 - front_w * 0.2)
        err[side] = _two_bone_ik(rig, side, tgt, pole)
        _orient_hand(rig, side, to_a(dir_w), to_a(-n_pair * sg))   # 掌心朝向另一只手
    left_p = to_a(left_w).normalized()
    # 袖子：举手后前臂竖起来，袖子骨骼还是打字时的角度，会被拧成扁片穿过手腕 → 按重力重新算，让宽袖子往下垂、顺着前臂滑向手肘
    sleeve = []
    for side, sg in (("l", 1.0), ("r", -1.0)):
        roots = [pb for pb in rig.pose.bones if pb.name.startswith("Bone") and pb.parent and pb.parent.name == f"forearm_twist.{side}"]
        want = to_a(-up_w + front_w * 0.15 + left_w * sg * 0.10).normalized()
        for pb in roots:
            bpy.context.view_layer.update()
            h_ = pb.head.copy()
            q = (pb.tail - pb.head).normalized().rotation_difference(want)
            pb.matrix = Matrix.Translation(h_) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h_) @ pb.matrix
            sleeve.append(pb.name)
    bpy.context.view_layer.update()
    look_clasp = {pb.name: pb.matrix_basis.to_quaternion() for pb in rig.pose.bones
                  if pb.name in ("neck.x", "head.x") or pb.name in sleeve
                  or pb.name.split(".")[0] in ("arm_stretch", "forearm_stretch", "hand")}
    # 量合手后的手腕距离 & 视线偏差
    wl, wr = rig.matrix_world @ pbn["hand.l"].head, rig.matrix_world @ pbn["hand.r"].head
    hc2, ec2 = _head_center(rig), _eye_center(CH)
    gaze = math.degrees((ec2 - hc2).normalized().angle((camp - hc2).normalized()))
    # --- 3) 特效：眼里星光（挂在头骨上）、身边星光、只照她的暖光 —— 在「看镜头 + 合手」的姿势下摆
    fx = bpy.data.collections.new(f"FX_B6_{cam_nm}")
    COL["CHARS"].children.link(fx)
    B6_FX[cam_nm] = fx
    to_cam = (camp - ec2).normalized()
    cam_up = (cam.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
    cam_rt = (cam.matrix_world.to_3x3() @ Vector((1, 0, 0))).normalized()
    eye_pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in CH.all_objects:
        if o.type == "MESH" and o.name.split(".")[0] == "eye":
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            eye_pts += [oe.matrix_world @ v.co for v in me.vertices]
            oe.to_mesh_clear()
    sideax = (rig.matrix_world.to_3x3() @ left_p).normalized()
    eyes2, eye_front, eye_h = [], [], []
    for sg in (1, -1):
        pts_ = [p_ for p_ in eye_pts if (p_ - hc2).dot(sideax) * sg > 0]
        if pts_:
            c_ = sum(pts_, Vector()) / len(pts_)
            eyes2.append(c_)
            ds = sorted(pts_, key=lambda q: q.dot(to_cam), reverse=True)
            fr_ = ds[:max(3, len(ds) // 4)]                   # 最靠镜头的四分之一顶点 = 眼球前表面（虹膜）
            eye_front.append(sum(fr_, Vector()) / len(fr_))
            ups = [q.dot(cam_up) for q in pts_]
            eye_h.append(max(ups) - min(ups))
    eye_w = (eyes2[0] - eyes2[1]).length if len(eyes2) == 2 else 0.05
    m_eye = _spark_mat(f"FX_eye_{cam_nm}", B6_EYE_SPARK, 6.0)
    m_star = _spark_mat(f"FX_eyestar_{cam_nm}", B6_EYE_STAR, 2.5)
    eye_obs = []
    for k, e_ in enumerate(eye_front):
        eh = eye_h[k]
        bone_ = "c_eye.l" if k == 0 else "c_eye.r"
        for j, (du, dv, rr, ri, mat_) in enumerate(((0.0, 0.0, 0.42, 0.30, m_star), (-0.24, 0.26, 0.10, 0.45, m_eye))):
            me = _star_mesh(f"FX_eyestar_{cam_nm}_{k}{j}", eh * rr, eh * rr * ri)
            me.materials.append(mat_)
            ob = bpy.data.objects.new(me.name, me)
            fx.objects.link(ob)
            ob.parent = rig
            ob.parent_type = "BONE"
            ob.parent_bone = bone_ if bone_ in B else "head.x"
            pos = e_ + to_cam * (0.0015 + 0.0005 * j) + cam_rt * eh * du + cam_up * eh * dv
            ob.matrix_world = Matrix.Translation(pos) @ (camp - pos).to_track_quat("Z", "Y").to_matrix().to_4x4()
            eye_obs.append((ob, j))
    # 脸颊红晕：眼睛下方贴在皮肤上的粉色渐隐椭圆（挂在头骨上）
    blush_obs = []
    body_o = next((o for o in CH.all_objects if o.type == "MESH" and o.name.split(".")[0] == "body"), None)
    if body_o is not None:
        from mathutils.bvhtree import BVHTree
        be = body_o.evaluated_get(dg)
        bm_ = be.to_mesh()
        bvh = BVHTree.FromPolygons([be.matrix_world @ v.co for v in bm_.vertices], [tuple(pp.vertices) for pp in bm_.polygons])
        be.to_mesh_clear()
        m_bl = _blush_mat(f"FX_blush_{cam_nm}", B6_BLUSH)
        for k, e_ in enumerate(eye_front):
            sg = 1 if k == 0 else -1
            aim = e_ - cam_up * eye_h[k] * 0.95 + sideax * sg * eye_w * 0.10
            dr = (aim - camp).normalized()
            hit, nrm, _i, _d = bvh.ray_cast(camp, dr, 5.0)
            if hit is None:
                continue
            me = _disc_mesh(f"FX_blush_{cam_nm}_{k}")
            me.materials.append(m_bl)
            ob = bpy.data.objects.new(me.name, me)
            fx.objects.link(ob)
            ob.parent = rig
            ob.parent_type = "BONE"
            ob.parent_bone = "head.x"
            nz = (nrm.normalized() + (-dr)).normalized()
            q = nz.to_track_quat("Z", "Y")
            rx, ry = eye_w * 0.36, eye_w * 0.18
            ob.matrix_world = Matrix.Translation(hit + nz * 0.0015) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((rx, ry, 1.0, 1.0))
            blush_obs.append(ob)
    # 身边星光：在镜头画面里围着头 / 肩膀一圈，往上飘、一闪一闪
    rng = random.Random(7 + len(cam_nm))
    m_sp = [_spark_mat(f"FX_spark_{cam_nm}_{c}", col, 3.0) for c, col in enumerate(B6_SPARK_COLS)]
    head_r = eye_w * 2.6
    spark_obs = []
    for k in range(12):
        a = rng.uniform(-0.15 * math.pi, 1.15 * math.pi)          # 主要在头的上半圈和两侧（E 镜头下面被显示器挡）
        rr = head_r * rng.uniform(1.1, 2.3)
        pos = hc2 + to_cam * rng.uniform(0.04, 0.14) + cam_rt * math.cos(a) * rr * 1.3 + cam_up * (math.sin(a) * rr - head_r * 0.2)
        size = eye_w * rng.uniform(0.28, 0.55)
        me = _star_mesh(f"FX_spark_{cam_nm}_{k}", size, size * rng.uniform(0.20, 0.26), n=4)
        me.materials.append(m_sp[k % len(m_sp)])
        ob = bpy.data.objects.new(me.name, me)
        fx.objects.link(ob)
        spark_obs.append((ob, pos, rng.uniform(0, 2 * math.pi), rng.uniform(1.6, 3.2), rng.uniform(38, 52), rng.uniform(0.6, 1.0)))
    # 只照她的暖光（灯光链接：接收者 = 这份人物的集合）
    kl = bpy.data.lights.new(f"FX_warm_{cam_nm}", "AREA")
    kl.shape = "DISK"
    kl.size = 0.5
    kl.color = lin((1.0, 0.82, 0.60))
    kl.use_shadow = False
    klo = bpy.data.objects.new(kl.name, kl)
    fx.objects.link(klo)
    kpos = hc2 + to_cam * 0.55 + cam_up * 0.30
    klo.location = kpos
    klo.rotation_euler = (hc2 - kpos).to_track_quat("-Z", "Y").to_euler()
    try:
        klo.light_linking.receiver_collection = CH
    except AttributeError:
        log("B6：这个版本没有灯光链接，暖光会照到整个场景")
    reset()
    # --- 4) 逐帧：姿势
    up_r = (B["neck.x"].head_local - B["root.x"].head_local).normalized()
    left_r = B["arm_stretch.l"].head_local - B["arm_stretch.r"].head_local
    left_r = (left_r - up_r * left_r.dot(up_r)).normalized()
    front_r = left_r.cross(up_r).normalized()

    def local_rot(bn, axis_r, deg):
        return Quaternion((B[bn].matrix_local.to_3x3().inverted() @ axis_r).normalized(), math.radians(deg))
    frames = []
    N = B6_N
    for i in range(N):
        w = _win(i, 0, 16, 96, 117)                      # 合手 + 看镜头
        closed = _win(i, 5, 15, 37, 42)                  # 开心地紧闭眼
        wide = _win(i, 39, 45, 96, 112)                  # 睁大眼
        small = _win(i, 6, 18, 38, 44) * 0.45            # 闭眼时的小笑
        big = _win(i, 38, 48, 96, 112)                   # 大大的笑
        jaw = _win(i, 40, 48, 94, 110)                   # 张一点嘴
        tilt = _win(i, 40, 52, 94, 112)                  # 歪头
        P = dict(P0)
        for bn, q1 in look_clasp.items():
            l_, q0 = P0.get(bn, _Z0)
            q1 = q1.copy()
            q1.make_compatible(q0)
            P[bn] = (l_, q0.slerp(q1, w))
        # 闭眼阶段开心地点两下头；睁眼后歪头 + 轻轻摇
        bob = 2.5 * math.sin(2 * math.pi * 2 * (i - 16) / 22) * _win(i, 16, 20, 34, 38)
        sway = 2.0 * math.sin(2 * math.pi * (i - 52) / 44) * _win(i, 52, 60, 88, 96)
        l_, q_ = P["head.x"]
        q_ = local_rot("head.x", left_r, bob) @ q_
        q_ = local_rot("head.x", front_r, B6_TILT * tilt + sway) @ q_
        P["head.x"] = (l_, q_)
        # 眼睛：紧闭 → 睁大（上眼皮转正 = 闭，负 = 睁；不抬脸颊，抬脸颊会把下眼皮顶上来、眼睛变小）
        for s_ in ("l", "r"):
            for bn, deg in ((f"eyelid_top.{s_}", 48.0 * closed + B6_MOUTH["lid"] * wide), (f"eyelid_bot.{s_}", -14.0 * closed + 3.0 * wide)):
                if bn in B:
                    l0, q0 = P0.get(bn, _Z0)
                    P[bn] = (l0, local_rot(bn, left_r, deg) @ q0)
        L3 = lambda bn: B[bn].matrix_local.to_3x3().inverted()
        # 眉毛上扬（中间最高）
        for s_ in ("l", "r"):
            for bn0, h_ in B6_BROW:
                bn = f"{bn0}.{s_}"
                if bn in B:
                    l0, q0 = P0.get(bn, _Z0)
                    P[bn] = (l0 + L3(bn) @ (up_r * h_ * wide), q0)
        # 嘴：闭眼时小笑 → 睁眼后张大嘴的 D 形大笑（嘴角往外拉、略上提；上唇上提、下唇下拉；下巴张开）
        Mo = B6_MOUTH
        for s_, sg in (("l", 1.0), ("r", -1.0)):
            bn = f"c_lips_smile.{s_}"
            if bn in B:
                l0, q0 = P0.get(bn, _Z0)
                d_ = left_r * sg * (Mo["cx"] * big + 0.010 * small) + up_r * (Mo["cy"] * big + 0.005 * small)
                P[bn] = (l0 + L3(bn) @ d_, q0)
            for bn, d_ in ((f"c_lips_top_01.{s_}", up_r * Mo["top"] + left_r * sg * Mo["out"]),
                           (f"c_lips_bot_01.{s_}", -up_r * Mo["bot"] + left_r * sg * Mo["out"])):
                if bn in B:
                    l0, q0 = P0.get(bn, _Z0)
                    P[bn] = (l0 + L3(bn) @ (d_ * big), q0)
        if "jawbone.x" in B:
            l0, q0 = P0.get("jawbone.x", _Z0)
            P["jawbone.x"] = (l0, local_rot("jawbone.x", left_r, -3.0 * small + Mo["jaw"] * jaw) @ q0)
        frames.append(P)
    act = _write_clip(rig, f"CLIP_B6_smile_{cam_nm}", frames)
    # --- 5) 逐帧：特效（缩放 0 = 看不见）
    for ob, j in eye_obs:
        base = ob.matrix_basis.copy()
        loc0, rot0, _ = base.decompose()
        kf = []
        for i in range(N):
            f_ = i + 1
            pop = _ramp(i, 42, 46) * (1.0 + 0.25 * math.sin(math.pi * min(1.0, max(0.0, (i - 46) / 6.0)))) * (1.0 - _ramp(i, 98, 110))
            tw = 1.0 + 0.15 * math.sin(i * 0.9 + j * 2.0)
            s_ = max(0.0, pop * tw)
            kf.append((f_, loc0, rot0.to_euler(), (s_, s_, s_)))
        _key_obj(ob, kf)
    for ob in blush_obs:
        loc0, rot0, scl0 = ob.matrix_basis.decompose()
        kf = []
        for i in range(N):
            life = _win(i, 38, 50, 98, 112)
            kf.append((i + 1, loc0, rot0.to_euler(), (scl0.x * life, scl0.y * life, scl0.z)))
        _key_obj(ob, kf)
    for ob, pos, ph0, freq, t0, amp in spark_obs:
        kf = []
        for i in range(N):
            f_ = i + 1
            life = _ramp(i, t0, t0 + 6) * (1.0 - _ramp(i, 100, 112))
            tw = 0.35 + 0.65 * abs(math.sin(ph0 + i * freq * 2 * math.pi / 24.0 * 0.5))
            s_ = max(0.0, life * tw * amp)
            p_ = pos + cam_up * eye_w * 0.012 * max(0.0, i - t0)
            rq = (camp - p_).to_track_quat("Z", "Y").to_euler()
            rq.rotate_axis("Z", ph0 + i * 0.05)
            kf.append((f_, p_, rq, (s_, s_, s_)))
        _key_obj(ob, kf)
    for i in range(N):
        kl.energy = 18.0 * _win(i, 38, 48, 96, 112)
        kl.keyframe_insert("energy", frame=i + 1)
    # 平时整个特效集合都藏起来，只有渲 B6 时 fx_on 才打开
    # （注意：不能一边遍历 all_objects 一边改 hide_render，Blender 会提前停止遍历——第一版只藏了 23 个里的 2 个，睡觉画面里也有星光）
    fx.hide_render = True
    for o in list(fx.all_objects):
        o.hide_render = False
    assign(rig, b1)
    sc.frame_set(1)
    B6_INFO[cam_nm] = dict(gaze_err=round(gaze, 1), wrist_err=[round(err["l"], 4), round(err["r"], 4)], wrist_gap=round((wl - wr).length, 3))
    log(f"B6 v2（{cam_nm}）：{N} 帧；视线偏差 {gaze:.1f}°；合手 IK 误差 左 {err['l']:.4f} 右 {err['r']:.4f}，两手腕相距 {(wl - wr).length:.3f} m；"
        f"眼里星光 {len(eye_obs)} 个、脸颊红晕 {len(blush_obs)} 个、身边星光 {len(spark_obs)} 个、暖光 1 盏（只照人物）")
    return act


def fx_on(cam_nm, on=True):
    for cn, coll in B6_FX.items():
        coll.hide_render = not (on and cn == cam_nm)


if B1:
    for _cn in ("E_monitor", "A_right34"):
        build_b6_magic(_cn)


# ================================================================== A4 书桌坐下 / 起身（主镜头）：N_stand ⇄ N_desk（= B1 第 1 帧）
A4_RAMP, A4_SCOOT, A4_HOLD = 12, 26, 4
A4_CHAIR_OUT = 1.66                     # 坐下前把椅子拉开到这里（椅背离北墙墙裙还有 ~0.04 m；再近长袍后摆会碰到椅垫）
CHAIR_PARK = (0.15, 1.45)               # 魔法椅子让路时停的地方：书桌东北边、床西边靠墙的空地（她走进书桌前那块空地时椅子不挡路）
A4_CHAIR_IN = 16                        # A4 开头椅子从停靠位滑到她身后用的帧数
A4_INFO = {}
CHAIR_ROOT = None


def _chair_root():
    """椅子所有零件挂到一个空物体上，按片段换动作（A4 要拉椅子）。椅子会动 → 渲染时属于人物层，背景里不放椅子"""
    global CHAIR_ROOT
    if CHAIR_ROOT is not None:
        return CHAIR_ROOT
    parts = [o for c in ("FURN", "PROPS") for o in COL[c].all_objects if o.name.startswith("cab_chair")]
    bpy.context.view_layer.update()
    cy = sum(o.matrix_world.translation.y for o in parts) / len(parts)
    e = empty("cab_chair_root", (CHAIR_C[0], cy, 0.0), COL["FURN"])
    bpy.context.view_layer.update()
    for o in parts:
        parent_keep(o, e)
    CHAIR_ROOT = e
    return e


def _hip_joint_w(rig):
    return sum((_bone_w(rig, f"thigh_stretch.{s_}") for s_ in ("l", "r")), Vector()) / 2


def _ankle_z(rig):
    return min(_bone_w(rig, f"foot.{s_}").z for s_ in ("l", "r"))


def relax_cape_action(rig, act, n, keep_fn=lambda i: CAPE_KEEP):
    """斗篷收窄逐帧做一遍：动画会覆盖斗篷骨骼，静止姿势里的 relax_cape 不起作用 → 每帧求值后收窄、再打关键帧。
    keep_fn(i) 给每帧的保留比例（1.0 = 不收）。返回第 1 帧收窄后的斗篷四元数（给斗篷模拟钉头尾用）"""
    assign(rig, act)
    names = [bn for ch_ in CAPE_CHAINS for bn in ch_ if bn in rig.pose.bones]
    first = {}
    for i in range(n):
        sc.frame_set(i + 1)
        bpy.context.view_layer.update()
        k_ = keep_fn(i)
        if k_ < 0.999:
            relax_cape(rig, k_)
        for bn in names:
            pb = rig.pose.bones[bn]
            pb.rotation_mode = "QUATERNION"
            pb.keyframe_insert("rotation_quaternion", frame=i + 1, group=bn)
            if i == 0:
                first[bn] = pb.rotation_quaternion.copy()
    return first



def build_a4():
    info = CH_INFO.get("seat")
    RT = globals().get("B1_RT")
    if not info or RT is None:
        return
    rig = info["rig"]
    B = rig.data.bones
    b1 = bpy.data.actions["CLIP_B1_study"]
    P0 = _sample_act(b1, 1, rig)[0]                       # N_desk
    a1 = bpy.data.actions.get("CLIP_A1_idle")
    PS = _sample_act(a1, 1, rig)[0] if a1 else dict(P0)   # N_stand（岛屿 A1 第 1 帧）
    # 站着时脚踝离地多高：用站姿那份人物量
    st = CH_INFO.get("stand")
    ankle_ref = 0.07
    if st:
        sc.frame_set(1)
        bpy.context.view_layer.update()
        ankle_ref = _ankle_z(st["rig"])
    chair = _chair_root()
    chair_y_b1 = chair.location.y
    b1_xy = Vector((chair.location.x, chair_y_b1))
    out_xy = Vector((chair.location.x, A4_CHAIR_OUT))
    park = Vector(CHAIR_PARK)
    # --- Mixamo Stand To Sit（保留臀部位移）
    n = RT["retarget"]("Stand To Sit", in_place=False)
    mx = bpy.data.scenes.get("MX_SRC")
    if mx:
        bpy.data.scenes.remove(mx)
    src = rig.animation_data.action
    MX = _sample_act(src, n, rig)
    bpy.data.actions.remove(src)
    # 头 A4_RAMP 帧从 N_stand 混进来
    raw = []
    for i, p_ in enumerate(MX):
        w = _ease(i / A4_RAMP) if i < A4_RAMP else 1.0
        raw.append(_blend(PS, p_, w) if w < 1 else p_)
    # --- 量：根物体停在 B1 的位置，逐帧量髋关节和脚踝
    tmp = _write_clip(rig, "TMP_A4_raw", raw)
    M3 = rig.matrix_world.to_3x3()
    Rb = B["root.x"].matrix_local.to_3x3()
    to_loc = (M3 @ Rb).inverted()
    H, AZ = [], []
    for i in range(len(raw)):
        sc.frame_set(i + 1)
        bpy.context.view_layer.update()
        H.append(_hip_joint_w(rig))
        AZ.append(_ankle_z(rig))
    bpy.data.actions.remove(tmp)
    seat_tgt = Vector((CHAIR_C[0], A4_CHAIR_OUT - 0.06, CHAIR_SEAT + SEAT_HIP))
    stand_y = max(seat_tgt.y - (H[-1].y - H[0].y), DESK_C[1] + DESK_D / 2 + 0.22)   # Mixamo 坐下时臀部往后移 ~0.46 m，照搬会站进桌子里；站位至少在桌边后 22 cm（袖子不碰桌面），剩下的差距坐下过程中补（脚会滑一点）
    stand_al = Vector((CHAIR_C[0] - H[0].x, stand_y - H[0].y, ankle_ref - AZ[0]))
    seat_al = seat_tgt - H[-1]
    z0, z1 = H[0].z + stand_al.z, H[-1].z + seat_al.z
    frames, chair_y = [], []                  # chair_y 存的是 (x, y)
    for i, p_ in enumerate(raw):
        hz = H[i].z + stand_al.z
        prog = min(1.0, max(0.0, (z0 - hz) / max(1e-4, z0 - z1)))
        c = stand_al.lerp(seat_al, _ease(prog))
        P = dict(p_)
        l_, q_ = P.get("root.x", _Z0)
        P["root.x"] = (l_ + to_loc @ c, q_)
        frames.append(P)
        chair_y.append(park.lerp(out_xy, _ease(i / A4_CHAIR_IN)) if i < A4_CHAIR_IN else out_xy.copy())
    # --- 坐稳后连人带椅子挪到桌前，同时手放到键盘上：最后一帧 = B1 第 1 帧
    last = frames[-1]
    for j in range(1, A4_SCOOT + 1):
        w = _ease(j / A4_SCOOT)
        frames.append(_blend(last, P0, w))
        chair_y.append(out_xy.lerp(b1_xy, w))
    for _ in range(A4_HOLD):
        frames.append(dict(P0))
        chair_y.append(b1_xy.copy())
    sit = _write_clip(rig, "CLIP_A4_sit", frames)
    up = _write_clip(rig, "CLIP_A4_up", list(reversed(frames)))
    # 斗篷收窄：站着 / 坐下时收（不碰椅子），挪到桌前那段慢慢放回原样，末帧 = B1 第 1 帧
    nF, s0 = len(frames), len(raw)
    kf_sit = lambda i: CAPE_KEEP + (1.0 - CAPE_KEEP) * _ease((i - s0) / max(1, nF - A4_HOLD - s0)) if i >= s0 else CAPE_KEEP
    relax_cape_action(rig, sit, nF, kf_sit)
    relax_cape_action(rig, up, nF, lambda i: kf_sit(nF - 1 - i))
    # 椅子动作（按片段换）
    for nm, ys in (("CHR_A4_sit", chair_y), ("CHR_A4_up", list(reversed(chair_y)))):
        old = bpy.data.actions.get(nm)
        if old:
            bpy.data.actions.remove(old)
        a = bpy.data.actions.new(nm)
        a.use_fake_user = True
        chair.animation_data_create()
        chair.animation_data.action = a
        try:
            chair.animation_data.action_slot = a.slots[0] if a.slots else None
        except Exception:
            pass
        for i, xy in enumerate(ys):
            chair.location.x, chair.location.y = xy.x, xy.y
            chair.keyframe_insert("location", index=0, frame=i + 1)
            chair.keyframe_insert("location", index=1, frame=i + 1)
    chair.animation_data.action = None
    chair.location.x, chair.location.y = b1_xy.x, b1_xy.y
    globals()["B1_CHAIR_XY"] = (b1_xy.x, b1_xy.y)
    # --- 检查：站着时脚踝高度、坐下时髋关节离椅面、末帧和 B1 第 1 帧的差
    assign(rig, sit)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    a_start = _ankle_z(rig)
    h_start = _hip_joint_w(rig)
    sc.frame_set(len(raw))
    bpy.context.view_layer.update()
    h_sit = _hip_joint_w(rig)
    sc.frame_set(len(frames))
    bpy.context.view_layer.update()
    h_end = _hip_joint_w(rig)
    assign(rig, b1)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    h_b1 = _hip_joint_w(rig)
    A4_INFO.update(frames=len(frames), mixamo=n, stand_xy=[round(h_start.x, 3), round(h_start.y, 3)], ankle_start=round(a_start, 3),
                   ankle_ref=round(ankle_ref, 3), hip_above_seat=round(h_sit.z - CHAIR_SEAT, 3), end_vs_b1_mm=round((h_end - h_b1).length * 1000, 2))
    log(f"A4 坐下：{len(frames)} 帧（Stand To Sit {n} 帧 + 挪椅子 {A4_SCOOT} + 停 {A4_HOLD}）；站位 ({h_start.x:.2f}, {h_start.y:.2f})，"
        f"站着脚踝 z {a_start:.3f}（参考 {ankle_ref:.3f}）；坐稳时髋关节高出椅面 {h_sit.z - CHAIR_SEAT:.3f}；末帧和 B1 第 1 帧差 {(h_end - h_b1).length * 1000:.2f} mm；"
        f"A4 起身 = 倒放（白模）")
    return sit, up


def a4_play(name):
    """切到某个 A4 片段：人物 + 椅子同时换动作；name=None 回到 B1"""
    rig = CH_INFO["seat"]["rig"]
    ch = CHAIR_ROOT
    if name is None:
        assign(rig, bpy.data.actions["CLIP_B1_study"])
        if ch and ch.animation_data:
            ch.animation_data.action = None
        return B1_LOOP
    assign(rig, bpy.data.actions[f"CLIP_{name}"])
    if ch:
        ca = bpy.data.actions[f"CHR_{name}"]
        ch.animation_data_create()
        ch.animation_data.action = ca
        try:
            ch.animation_data.action_slot = ca.slots[0]
        except Exception:
            pass
    return A4_INFO.get("frames", 1)


if B1:
    build_a4()


# ================================================================== 屋里走路（主镜头）：W_door_desk、W_desk_bed —— 站姿那份人物，根物体沿路径走
W_RAMP = 16                       # 起步 / 停步 + 转身的帧数
W_SPEED = 1.1                     # 屋里走路速度 m/s
W_ARM_DAMP = 0.5                  # 屋里走路手臂 / 袖子的摆动只留一半
W_ARM_BONES = ("shoulder.", "arm_stretch.", "c_arm_twist_offset.", "forearm_stretch.", "forearm_twist.", "hand.")


def _furn_dist(p_):
    """髋关节离书桌 / 床 / 床头柜（俯视矩形）最近的距离"""
    rects = [(DESK_C[0] - DESK_W / 2, DESK_C[0] + DESK_W / 2, DESK_C[1] - DESK_D / 2, DESK_C[1] + DESK_D / 2),
             (BED_X[0], BED_X[1], BED_Y[0], BED_Y[1])]
    d = 9.0
    for x0, x1, y0, y1 in rects:
        dx = max(x0 - p_.x, 0.0, p_.x - x1)
        dy = max(y0 - p_.y, 0.0, p_.y - y1)
        d = min(d, math.hypot(dx, dy))
    return d
W_INFO = {}


def _chaikin(pts, it=2):
    for _ in range(it):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        q.append(pts[-1])
        pts = q
    return pts


def _resample(pts, ds=0.01):
    """折线 → 按弧长等距采样，返回 (点列表, 总长)"""
    out, acc = [pts[0]], 0.0
    seg = [(a, b, (b - a).length) for a, b in zip(pts[:-1], pts[1:])]
    total = sum(l for _, _, l in seg)
    s_ = ds
    while s_ < total:
        acc = 0.0
        for a, b, l in seg:
            if acc + l >= s_:
                out.append(a.lerp(b, (s_ - acc) / max(l, 1e-9)))
                break
            acc += l
        s_ += ds
    out.append(pts[-1])
    return out, total


def _heading(d):
    return math.atan2(d.x, -d.y)


def _ang_lerp(a, b, w):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * w


COLL_MARGIN = 0.04                      # 斗篷离家具至少 4 cm


def _furn_boxes():
    """碰撞盒（世界空间 AABB）：书桌桌面 + 桌裙、床架 + 床垫、椅子（跟着椅子根物体动）"""
    bx = [((DESK_C[0] - DESK_W / 2, DESK_C[1] - DESK_D / 2, DESK_TOP - 0.13), (DESK_C[0] + DESK_W / 2, DESK_C[1] + DESK_D / 2, DESK_TOP)),
          ((BED_X[0], BED_Y[0], 0.0), (BED_X[1], BED_Y[1], BED_TOP + 0.05))]
    ch = CHAIR_ROOT
    if ch is not None:
        cx, cy = ch.matrix_world.translation.x, ch.matrix_world.translation.y
        bx.append(((cx - 0.22, cy - 0.21, 0.0), (cx + 0.22, cy + 0.21, CHAIR_SEAT + 0.05)))      # 椅面以下
        bx.append(((cx - 0.21, cy + 0.12, CHAIR_SEAT), (cx + 0.21, cy + 0.24, CHAIR_SEAT + 0.50)))  # 椅背
    return bx


def _push_out(p_, boxes, m=COLL_MARGIN):
    """点在某个（外扩 m 的）盒子里 → 推到最近的面外；返回新点或 None"""
    hit = None
    for (x0, y0, z0), (x1, y1, z1) in boxes:
        x0, y0, z0, x1, y1, z1 = x0 - m, y0 - m, z0 - m, x1 + m, y1 + m, z1 + m
        if x0 < p_.x < x1 and y0 < p_.y < y1 and z0 < p_.z < z1:
            cand = [(p_.x - x0, Vector((x0, p_.y, p_.z))), (x1 - p_.x, Vector((x1, p_.y, p_.z))),
                    (p_.y - y0, Vector((p_.x, y0, p_.z))), (y1 - p_.y, Vector((p_.x, y1, p_.z))),
                    (z1 - p_.z, Vector((p_.x, p_.y, z1)))]                      # 不往下推（地板）
            q = min(cand, key=lambda c: c[0])[1]
            hit = q if hit is None else hit
            p_ = q
    return hit


def cape_collide(rig, act, n, chair_act=None):
    """斗篷碰撞：逐帧沿每条斗篷链从根到梢，梢端进了家具碰撞盒就绕根部把这节转出来（子骨骼跟着走），再打关键帧"""
    assign(rig, act)
    ch = CHAIR_ROOT
    if ch is not None and chair_act is not None:
        ch.animation_data_create()
        ch.animation_data.action = chair_act
    chains = [[bn for bn in c_ if bn in rig.pose.bones] for c_ in CAPE_CHAINS]
    chains += [[b.name] for b in rig.data.bones if b.name.startswith("Bone") and b.parent and b.parent.name.startswith("forearm_twist.")]   # 宽袖子也挡开
    # 链上所有骨骼（含 CAPE_CHAINS 没列出的末梢子骨骼）
    full = []
    for c_ in chains:
        if not c_:
            continue
        seq = list(c_)
        tip = rig.pose.bones[seq[-1]]
        while tip.children:
            tip = tip.children[0]
            seq.append(tip.name)
        full.append(seq)
    Mw = rig.matrix_world
    Mi = Mw.inverted()
    fixed = 0
    for i in range(n):
        sc.frame_set(i + 1)
        bpy.context.view_layer.update()
        boxes = _furn_boxes()
        for seq in full:
            for bn in seq:
                pb = rig.pose.bones[bn]
                bpy.context.view_layer.update()
                h_w, t_w = Mw @ pb.head, Mw @ pb.tail
                q_w = _push_out(t_w, boxes)
                if q_w is None:
                    continue
                h_a, t_a, q_a = pb.head.copy(), pb.tail.copy(), Mi @ q_w
                rot = (t_a - h_a).rotation_difference((q_a - h_a).normalized() * (t_a - h_a).length)
                pb.matrix = Matrix.Translation(h_a) @ rot.to_matrix().to_4x4() @ Matrix.Translation(-h_a) @ pb.matrix
                fixed += 1
        bpy.context.view_layer.update()
        for seq in full:
            for bn in seq:
                pb = rig.pose.bones[bn]
                pb.rotation_mode = "QUATERNION"
                pb.keyframe_insert("rotation_quaternion", frame=i + 1, group=bn)
    if ch is not None and chair_act is not None:
        ch.animation_data.action = None
    return fixed



def build_walk(name, pts2d, h_start, h_end, chair_from=None, chair_to=None, chair_when=(0.5, 0.9)):
    st = CH_INFO.get("stand")
    RT = globals().get("B1_RT")
    if not st or RT is None:
        return None
    rig, root = st["rig"], st["root"]
    seat_rig = CH_INFO["seat"]["rig"]
    # Happy Walk 原地化（在书桌那份上重定向，取局部姿势；两份骨架一样）
    n = RT["retarget"]("Happy Walk", in_place=True)
    drift = RT["LAST"].get("drift") or Vector((0, 0.6, 0))
    mx = bpy.data.scenes.get("MX_SRC")
    if mx:
        bpy.data.scenes.remove(mx)
    src = seat_rig.animation_data.action
    WK = _sample_act(src, n, seat_rig)
    bpy.data.actions.remove(src)
    assign(seat_rig, bpy.data.actions["CLIP_B1_study"])
    v_src = drift.length / max(1, n - 1)              # Happy Walk 原速（一帧走多少米，约 1.6 m/s，屋里像小跑）
    v = min(v_src, W_SPEED / 24.0)                    # 屋里放慢到 W_SPEED；相位仍按距离推进（步子放慢，不滑步）
    a1 = bpy.data.actions.get("CLIP_A1_idle")
    PS = _sample_act(a1, 1, rig)[0]
    # 站姿下髋关节相对根物体的偏移（根在原点、不转）
    root.animation_data_clear()
    root.location, root.rotation_euler = (0, 0, 0), (0, 0, 0)
    tmp = _write_clip(rig, "TMP_W_stand", [PS])
    sc.frame_set(1)
    bpy.context.view_layer.update()
    off = _hip_joint_w(rig)
    off = Vector((off.x, off.y, 0.0))
    bpy.data.actions.remove(tmp)
    # 路径：平滑 + 等距
    P = _chaikin([Vector((x, y, 0.0)) for x, y in pts2d])
    S, L = _resample(P, 0.01)
    cruise = max(0.0, L - v * W_RAMP)                 # 两头各 W_RAMP 帧加 / 减速，各走 v*W_RAMP/2
    nc = int(math.ceil(cruise / v))
    N = 2 * W_RAMP + nc
    vel = []
    for i in range(N):
        if i < W_RAMP:
            vel.append(v * _ease((i + 0.5) / W_RAMP))
        elif i >= N - W_RAMP:
            vel.append(v * _ease((N - i - 0.5) / W_RAMP))
        else:
            vel.append(v)
    scale = L / sum(vel)
    vel = [x * scale for x in vel]
    frames, locs, heads, phase, s_ = [], [], [], 0.0, 0.0
    for i in range(N):
        s_ = min(L, s_ + vel[i]) if i > 0 else 0.0
        k = min(len(S) - 1, int(round(s_ / 0.01)))
        p_ = S[k]
        d_ = S[min(len(S) - 1, k + 3)] - S[max(0, k - 3)]
        h_path = _heading(d_) if d_.length > 1e-6 else h_end
        # 转身：头 W_RAMP 帧从起始朝向转到路径方向，尾 W_RAMP 帧转到结束朝向
        h = h_path
        if i < W_RAMP:
            h = _ang_lerp(h_start, h_path, _ease(i / W_RAMP))
        if i >= N - W_RAMP:
            h = _ang_lerp(h_path, h_end, _ease((i - (N - W_RAMP)) / W_RAMP))
        # 步伐相位按实际走的距离推进：不会滑步
        phase += (vel[i] / v_src) if i > 0 else 0.0
        fi = phase % (n - 1)
        a_, b_ = int(fi), min(n - 1, int(fi) + 1)
        pw = _blend(WK[a_], WK[b_], fi - a_)
        # 手臂少摆：整体只留一半；离书桌 / 床半米以内时收得更紧（宽袖子不甩进家具）
        near = min(1.0, max(0.0, (0.55 - _furn_dist(p_)) / 0.30))
        aw = W_ARM_DAMP + (0.95 - W_ARM_DAMP) * near
        sleeve_names = [b.name for b in rig.data.bones if b.name.startswith("Bone") and b.parent and b.parent.name.startswith("forearm_twist.")]
        for bn in list(pw.keys()):
            if bn.startswith(W_ARM_BONES) or bn in sleeve_names:
                l0, q0 = PS.get(bn, _Z0)
                l1, q1 = pw[bn]
                q1 = q1.copy()
                q1.make_compatible(q0)
                pw[bn] = (l1.lerp(l0, aw), q1.slerp(q0, aw))
        w_ = vel[i] / v
        pose = _blend(PS, pw, _ease(w_)) if w_ < 0.999 else pw
        frames.append(pose)
        hip = p_
        root_xy = hip - Matrix.Rotation(h, 3, "Z") @ off
        locs.append(Vector((root_xy.x, root_xy.y, 0.0)))
        heads.append(h)
    frames[0], frames[-1] = dict(PS), dict(PS)            # 首尾严格 = 站姿
    act = _write_clip(rig, f"CLIP_{name}", frames)
    # 根物体动作
    old = bpy.data.actions.get(f"CLIPR_{name}")
    if old:
        bpy.data.actions.remove(old)
    ra = bpy.data.actions.new(f"CLIPR_{name}")
    ra.use_fake_user = True
    root.animation_data_create()
    root.animation_data.action = ra
    root.rotation_mode = "XYZ"
    un, prev = [], None
    for h in heads:
        if prev is not None:
            while h - prev > math.pi:
                h -= 2 * math.pi
            while h - prev < -math.pi:
                h += 2 * math.pi
        un.append(h)
        prev = h
    for i, (l_, h) in enumerate(zip(locs, un)):
        root.location = l_
        root.rotation_euler = (0, 0, h)
        root.keyframe_insert("location", frame=i + 1)
        root.keyframe_insert("rotation_euler", frame=i + 1)
    # 椅子自己滑开 / 滑回（魔女的椅子）
    chair = _chair_root()
    cys = []
    for i in range(N):
        if chair_from is None:
            cys.append(Vector((chair.location.x, chair.location.y)))
        else:
            t_ = _ramp(i / (N - 1), chair_when[0], chair_when[1])
            cys.append(Vector(chair_from).lerp(Vector(chair_to), t_))
    ca_old = bpy.data.actions.get(f"CHR_{name}")
    if ca_old:
        bpy.data.actions.remove(ca_old)
    ca = bpy.data.actions.new(f"CHR_{name}")
    ca.use_fake_user = True
    keep_xy = (chair.location.x, chair.location.y)
    chair.animation_data_create()
    chair.animation_data.action = ca
    for i, xy in enumerate(cys):
        chair.location.x, chair.location.y = xy.x, xy.y
        chair.keyframe_insert("location", index=0, frame=i + 1)
        chair.keyframe_insert("location", index=1, frame=i + 1)
    chair.animation_data.action = None
    chair.location.x, chair.location.y = keep_xy
    # 斗篷摆动
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cloth_sim", CLOTH_PATH)
        cs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cs)
        sc.frame_start, sc.frame_end = 1, N
        root.animation_data.action = ra
        relaxed = relax_cape_action(rig, act, N)        # 斗篷先逐帧收窄（否则又张到 40~50°，甩进桌子 / 椅子），头尾钉到收窄后的站姿
        sc.frame_set(1)
        bpy.context.view_layer.update()
        pin = {nm: rig.pose.bones[nm].rotation_quaternion.copy() for c_ in cs.chains(rig) for nm in c_}
        pin.update(relaxed)
        cs.simulate(rig, 1, N, loop=False, log=log, pin_start=pin, pin_end=pin)
    except Exception as e:
        log(f"{name} 斗篷模拟失败：{e!r}")
    nfix = cape_collide(rig, act, N, ca)
    log(f"{name} 斗篷碰撞：推出家具 {nfix} 次（骨骼·帧）")
    # 检查：起止点的髋关节位置、路径离家具最近距离
    sc.frame_set(1)
    bpy.context.view_layer.update()
    h0 = _hip_joint_w(rig)
    sc.frame_set(N)
    bpy.context.view_layer.update()
    h1 = _hip_joint_w(rig)
    W_INFO[name] = dict(frames=N, length=round(L, 2), speed=round(v * 24, 2), hip_start=[round(h0.x, 3), round(h0.y, 3)], hip_end=[round(h1.x, 3), round(h1.y, 3)])
    log(f"走路 {name}：{N} 帧，路长 {L:.2f} m，步速 {v * 24:.2f} m/s；髋关节 起 ({h0.x:.3f}, {h0.y:.3f}) → 止 ({h1.x:.3f}, {h1.y:.3f})")
    root.animation_data.action = None
    return act


def walk_play(name):
    """切到某段走路：站姿那份人物 + 根物体 + 椅子一起换动作；书桌 / 床上那两份藏起来"""
    st = CH_INFO["stand"]
    for k, info in CH_INFO.items():
        if k in ("stand", "seat", "lie"):
            info["coll"].hide_render = k != "stand"
    assign(st["rig"], bpy.data.actions[f"CLIP_{name}"])
    st["root"].animation_data_create()
    st["root"].animation_data.action = bpy.data.actions[f"CLIPR_{name}"]
    ch = CHAIR_ROOT
    ca = bpy.data.actions.get(f"CHR_{name}")
    if ch:
        ch.animation_data_create()
        ch.animation_data.action = ca                 # 没有椅子动作的片段：椅子停在桌下
        if ca is None:
            ch.location.x, ch.location.y = B1_CHAIR_XY
    return W_INFO[name]["frames"]


if B1:
    _sp = {k: list(v) for k, v in PATHS.items()}
    _a4 = tuple(A4_INFO.get("stand_xy", (-0.45, 1.17)))
    _sp["进门 → 书桌"] = [(-1.55, 1.40), (-1.05, 1.42), (-0.66, 1.38), _a4]          # 从北边进来，离桌边 40 cm 以上（椅子已经让到东北边）
    _sp["书桌 → 床边"] = [_a4, (-0.50, 1.40), (-1.18, 1.40), (-1.32, 0.62), (-1.12, 0.08), (0.30, 0.04), (1.00, 0.24), (1.30, 0.42)]   # 床边站位 y 0.42：背对床时斗篷后摆不碰床沿
    _b1c = (_chair_root().location.x, _chair_root().location.y)
    build_walk("W_door_desk", _sp["进门 → 书桌"], h_start=math.radians(100), h_end=0.0,
               chair_from=_b1c, chair_to=CHAIR_PARK, chair_when=(0.0, 0.45))
    build_walk("W_desk_bed", _sp["书桌 → 床边"], h_start=0.0, h_end=0.0,
               chair_from=CHAIR_PARK, chair_to=_b1c, chair_when=(0.40, 0.75))


# ================================================================== 早上（起床转场之后）：床边 → 东窗拉窗帘 G6 → 衣帽架戴帽 G5 → 门口淡出 G7
G_SPOT_WIN = (1.98, -0.55)              # 东窗 win_l2 前，面向窗（heading 90°）
G_SPOT_HAT = (-1.86, 0.985)             # 衣帽架前 0.72 m，面向衣帽架：帽檐半径 0.43 m，再近帽檐就插进辫子和肩膀（G5 改成魔法取帽，不用伸手够）
G_SPOT_DOOR = (-1.55, 1.40)             # 门口（heading 180°，面向门）
G_N = 76                                # G6 / G5 每段帧数
G5_CLEAR = 0.10                         # G5（魔法）：帽子飘过头顶时，帽子最低点比头顶高多少
G5_HEADTOP = 0.24                       # head.x 骨头起点到头顶（含头发）的高度（实测 1.347 → 1.585）
G5_POINT = 0.30                         # G5：指向帽子时手腕在肩前方多远（手臂约 34 cm）
G5_BRIM_R = 0.48                        # G5：帽檐半径 0.43 + 手的余量
G5_LOOK = 0.5                           # G5：抬头看帽子 = 反向低头 G5_BOW 的一半
G5_GRIP_R, G5_GRIP_DOWN = (0.22, 0.25, 0.28), 0.09   # G5：右手扶帽檐的半径候选 / 手腕在帽檐下表面下方多少
G5_BOW = (("neck.x", 12.0), ("head.x", 14.0))   # G5：抬头用（取反、乘 G5_LOOK）
CLIP_EXTRA = {}                         # 片段名 → {"curtain": 动作, "hat": "stand" / "carry" / "head"}


def _stand_root(rig, root, PS, hip_xy, h):
    """站姿下让髋关节落在 hip_xy、朝向 h：返回根物体位置"""
    root.animation_data_clear()
    root.location, root.rotation_euler = (0, 0, 0), (0, 0, 0)
    tmp = _write_clip(rig, "TMP_stand", [PS])
    sc.frame_set(1)
    bpy.context.view_layer.update()
    off = _hip_joint_w(rig)
    bpy.data.actions.remove(tmp)
    o2 = Matrix.Rotation(h, 3, "Z") @ Vector((off.x, off.y, 0.0))
    return Vector((hip_xy[0] - o2.x, hip_xy[1] - o2.y, 0.0))


def _key_root_static(root, name, loc, h, n):
    old = bpy.data.actions.get(f"CLIPR_{name}")
    if old:
        bpy.data.actions.remove(old)
    ra = bpy.data.actions.new(f"CLIPR_{name}")
    ra.use_fake_user = True
    root.animation_data_create()
    root.animation_data.action = ra
    root.rotation_mode = "XYZ"
    for f in (1, n):
        root.location = loc
        root.rotation_euler = (0, 0, h)
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", frame=f)
    return ra


def _ik_pose(rig, PS, targets_w, palm_dirs_w=None, hand_dirs_w=None, pole_w=None):
    """在站姿 PS 上，给一只或两只手解 IK（世界坐标目标），返回这些手臂骨骼的局部四元数"""
    _apply_pose(rig, PS)
    A3i = rig.matrix_world.to_3x3().normalized().inverted()
    Aw_i = rig.matrix_world.inverted()
    out = {}
    for side, tw in targets_w.items():
        sg = 1.0 if side == "l" else -1.0
        pole = (pole_w or {}).get(side, Vector((0, 0, -1)))
        _two_bone_ik(rig, side, Aw_i @ tw, (A3i @ pole).normalized())
        if hand_dirs_w and side in hand_dirs_w:
            _orient_hand(rig, side, (A3i @ hand_dirs_w[side]).normalized(), (A3i @ palm_dirs_w[side]).normalized())
        for bn in (f"arm_stretch.{side}", f"forearm_stretch.{side}", f"hand.{side}"):
            out[bn] = rig.pose.bones[bn].matrix_basis.to_quaternion()
    return out


def _apply_pose(rig, P):
    rig.animation_data_create()
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        l_, q_ = P.get(pb.name, _Z0)
        pb.location = l_
        pb.rotation_quaternion = q_
    bpy.context.view_layer.update()


def _mix_arm(P, Q, w):
    """P 是整套姿势，Q 是手臂骨骼的四元数：按 w 混合"""
    out = dict(P)
    for bn, q1 in Q.items():
        l0, q0 = P.get(bn, _Z0)
        q1 = q1.copy()
        q1.make_compatible(q0)
        out[bn] = (l0, q0.slerp(q1, w))
    return out


def _curtain_open_key(win="win_l2"):
    """给合上的窗帘加「拉开」形状键（拉开那套网格顶点数一样）"""
    res = []
    for side in ("L", "R"):
        cl = bpy.data.objects.get(f"cab_{win}_cur_closed_{side}")
        op = bpy.data.objects.get(f"cab_{win}_cur_open_{side}")
        if not cl or not op or len(cl.data.vertices) != len(op.data.vertices):
            continue
        if cl.data.shape_keys is None:
            cl.shape_key_add(name="Basis", from_mix=False)
        kb = cl.data.shape_keys.key_blocks.get("open") or cl.shape_key_add(name="open", from_mix=False)
        for i, v in enumerate(op.data.vertices):
            kb.data[i].co = v.co.copy()
        res.append(cl)
    return res


def build_g6():
    st = CH_INFO["stand"]
    rig, root = st["rig"], st["root"]
    PS = _sample_act(bpy.data.actions["CLIP_A1_idle"], 1, rig)[0]
    h = math.radians(90)
    rloc = _stand_root(rig, root, PS, G_SPOT_WIN, h)
    ra = _key_root_static(root, "G6_curtain", rloc, h, G_N)
    sc.frame_set(1)
    bpy.context.view_layer.update()
    cu = EAST_OPEN[0][1] if EAST_OPEN[0][0] == "win_l2" else -0.55
    xw, zc = IX - 0.12, 1.28
    up, front = Vector((0, 0, 1)), Vector((1, 0, 0))
    # 抓的位置（窗帘中缝两边）→ 拉开后的位置（窗两侧）
    def tg(p):
        return {"l": Vector((xw, cu + 0.06 + 0.32 * p, zc)), "r": Vector((xw, cu - 0.06 - 0.32 * p, zc))}
    poles = {"l": Vector((0, 0.6, -1)), "r": Vector((0, -0.6, -1))}
    hd = {"l": up * 0.6 + front * 0.6, "r": up * 0.6 + front * 0.6}
    palm = {"l": front, "r": front}
    frames, prog = [], []
    for i in range(G_N):
        reach = _win(i, 0, 18, 56, 74)
        pull = _ramp(i, 24, 48)
        Q = _ik_pose(rig, PS, tg(pull), palm, hd, poles)
        frames.append(_mix_arm(PS, Q, reach))
        prog.append(pull)
    frames[0], frames[-1] = dict(PS), dict(PS)
    act = _write_clip(rig, "CLIP_G6_curtain", frames)
    # 窗帘形状键：跟手同步滑开
    cls = _curtain_open_key()
    for cl in cls:
        key = cl.data.shape_keys
        key.animation_data_clear()
        kb = key.key_blocks["open"]
        for i, p in enumerate(prog):
            kb.value = p
            kb.keyframe_insert("value", frame=i + 1)
        a = key.animation_data.action
        a.name = f"KEY_G6_{cl.name}"
        a.use_fake_user = True
        key.animation_data.action = None
        kb.value = 0.0
    CLIP_EXTRA["G6_curtain"] = dict(curtain="play", hat="stand")
    relax_cape_action(rig, act, G_N)
    root.animation_data.action = ra
    sc.frame_set(G_N // 2)
    bpy.context.view_layer.update()
    err = max((rig.matrix_world @ rig.pose.bones[f"hand.{s_}"].head - tg(prog[G_N // 2])[s_]).length for s_ in ("l", "r"))
    W_INFO["G6_curtain"] = dict(frames=G_N)
    log(f"G6 拉窗帘：{G_N} 帧；双手 IK 误差最大 {err * 100:.1f} cm；窗帘 {len(cls)} 片随手滑开（第 24–48 帧）")
    root.animation_data.action = None
    return act


def _g5_bow(PS, w):
    """在站姿 PS 上叠加 G5 的低头（权重 w）"""
    B = CH_INFO["stand"]["rig"].data.bones
    up_ = (B["neck.x"].head_local - B["root.x"].head_local).normalized()
    left_ = B["arm_stretch.l"].head_local - B["arm_stretch.r"].head_local
    left_ = (left_ - up_ * left_.dot(up_)).normalized()
    out = dict(PS)
    if abs(w) < 1e-6:                 # w < 0 = 反方向（抬头）
        return out
    for bn, deg in G5_BOW:
        if bn not in B:
            continue
        ax_ = (B[bn].matrix_local.to_3x3().inverted() @ left_).normalized()
        l_, q_ = out.get(bn, _Z0)
        out[bn] = (l_, Quaternion(ax_, math.radians(deg * w)) @ q_)
    return out


def build_g5():
    """G5 戴帽 v5（魔法）：她抬右手指向衣帽架，帽子自己飘起来戴到头上，手最后扶一下帽檐。没有任何光效（光效只在 B6）。
    为什么不用手拿：伊蕾娜手臂约 34 cm、帽檐半径 43 cm，举不过头顶，帽檐一定会扫过脸和头发（v4 实测第 31 帧约 8000 条边穿过帽子）。
    路径：衣帽架上竖直升起（同时转到戴好的角度），升到帽子最低点比头顶高 G5_CLEAR → 水平飘到头顶正上方 → 沿帽锥轴线笔直落下。
    帽子最低点始终高于头顶，落下时头顶始终在帽腔更宽处，所以全程不穿模；最终姿态和她自己头上的帽子完全重合。"""
    st = CH_INFO["stand"]
    rig, root = st["rig"], st["root"]
    hroot = HAT_INFO.get("root")
    if hroot is None:
        return None
    PS = _sample_act(bpy.data.actions["CLIP_A1_idle"], 1, rig)[0]
    h = _H_HAT
    rloc = _stand_root(rig, root, PS, G_SPOT_HAT, h)
    ra = _key_root_static(root, "G5_hat", rloc, h, G_N)
    sc.frame_set(1)
    _apply_pose(rig, PS)
    if "R_stand0" not in HAT_INFO:
        HAT_INFO["R_stand0"] = hroot.matrix_world.copy()
    R_stand = HAT_INFO["R_stand0"].copy()
    HAT_INFO["R_stand"] = R_stand.copy()
    hroot.matrix_world = R_stand
    H0i = HAT_INFO["H0"].inverted()
    R0 = HAT_INFO["R0"]
    fw = Vector((math.sin(h), -math.cos(h), 0.0))
    side_r = Vector((-fw.y, fw.x, 0.0)) * -1.0                # 她的右手边
    up = Vector((0, 0, 1))
    P0, UP0, UP1, TR1, DN1, GR0, GR1, R1 = 14, 14, 28, 42, 54, 42, 52, 58

    def look_w(i):                                            # 抬头看帽子：14→26 抬起，26→40 保持，40→52 放下（落帽前回正）
        if i < 14 or i >= 52:
            return 0.0
        if i < 26:
            return _ease((i - 14) / 12)
        if i < 40:
            return 1.0
        return 1.0 - _ease((i - 40) / 12)

    def head_state(P):
        _apply_pose(rig, P)
        Hd = rig.matrix_world @ rig.pose.bones["head.x"].matrix
        oh = Hd @ H0i @ R0                                    # 戴好时帽子根的世界矩阵
        ax = (oh.to_3x3() @ Vector((0, 0, 1))).normalized()  # 帽锥轴线
        return oh, ax, Hd, rig.matrix_world @ rig.pose.bones["arm_stretch.r"].head

    # 扶帽檐的点：戴好时右前方帽檐下表面再往下 G5_GRIP_DOWN，离肩最近
    Ri = R_stand.inverted()
    loc_v = [Ri @ (o.matrix_world @ v.co) for o in HAT_ON_STAND for v in o.data.vertices]
    hat_top = max(q.z for q in loc_v)
    oh0, ax0, Hd0, sh0 = head_state(PS)
    best = None
    for k in range(72):
        a = 2 * math.pi * k / 72
        d = Vector((math.cos(a), math.sin(a), 0.0))
        rad_on = (oh0.to_3x3() @ d).normalized()
        if rad_on.dot(side_r) < 0.0 or rad_on.dot(fw) < 0.0:
            continue
        for r in G5_GRIP_R:
            c = d * r
            zs = [q.z for q in loc_v if (q.x - c.x) ** 2 + (q.y - c.y) ** 2 < 0.02 ** 2]
            if not zs:
                continue
            wl = Vector((c.x, c.y, min(zs) - G5_GRIP_DOWN))
            dd = ((oh0 @ wl) - sh0).length
            if best is None or dd < best[0]:
                best = (dd, wl, d.copy(), r)
    _, grip_l, rad_l, grip_r = best
    # 帽子要升到的高度：帽子根（= 帽子最低点）比头顶高 G5_CLEAR
    z_hi = Hd0.translation.z + G5_HEADTOP + G5_CLEAR
    l_st, q_st, _ = R_stand.decompose()
    poles = {"r": Vector((0, 0, -1)) + side_r * 0.6}
    frames, mats, hand_tg = [], [], []
    for i in range(G_N):
        Pi = _g5_bow(PS, -look_w(i) * G5_LOOK)
        oh, ax, Hd, sh = head_state(Pi)
        L_hi = max(0.0, (z_hi - oh.translation.z) / max(ax.z, 0.3))
        above = Matrix.Translation(ax * L_hi) @ oh
        l_ab, q_ab, _ = above.decompose()
        q_ab.make_compatible(q_st)
        if i < UP0:
            M = R_stand
        elif i < UP1:                                         # 竖直升起，同时转到戴好的角度
            t = _ease((i - UP0) / (UP1 - UP0))
            M = Matrix.LocRotScale(Vector((l_st.x, l_st.y, l_st.z + (z_hi - l_st.z) * t)), q_st.slerp(q_ab, t), None)
        elif i < TR1:                                         # 水平飘到头顶正上方（高度不变）
            t = _ease((i - UP1) / (TR1 - UP1))
            a_ = Vector((l_st.x, l_st.y, z_hi))
            M = Matrix.LocRotScale(a_.lerp(l_ab, t), q_ab, None)
        elif i < DN1:                                         # 沿帽锥轴线笔直落下
            t = _ease((i - TR1) / (DN1 - TR1))
            M = Matrix.Translation(ax * (L_hi * (1.0 - t))) @ oh
        else:
            M = oh
        mats.append(M.copy())
        # 右手：先指向帽子（手在肩前方 G5_POINT 处），GR0→GR1 移到扶帽檐的位置（按戴好的姿态，帽子落下来正好落到手上），R1 后放下
        hc = M @ Vector((0, 0, (hat_top) * 0.35))
        dir_ = (hc - sh).normalized()
        # 指向时手不能进帽檐：要么在帽檐圆柱外（水平离帽轴 ≥ G5_BRIM_R），要么比帽檐低 6 cm 以上
        for ln in [G5_POINT - 0.01 * k for k in range(21)]:
            pt = sh + dir_ * ln
            tip = sh + dir_ * (ln + 0.12)                     # 手指尖比手腕再远约 12 cm
            if (tip - M.translation).xy.length >= G5_BRIM_R or tip.z < M.translation.z - 0.06:
                break
        gw = oh @ grip_l
        if i < GR0:
            tw, w = pt, _ramp(i, 0, P0)
            palm, hd_ = -up, dir_
        elif i < GR1:
            u = _ease((i - GR0) / (GR1 - GR0))
            tw, w = pt.lerp(gw, u), 1.0
            palm = (-up).lerp((oh.to_3x3() @ Vector((0, 0, 1))), u).normalized()
            hd_ = dir_.lerp((oh.to_3x3() @ rad_l).normalized(), u).normalized()
        else:
            tw = gw
            w = 1.0 if i < R1 else 1.0 - _ramp(i, R1, G_N - 2)
            palm, hd_ = (oh.to_3x3() @ Vector((0, 0, 1))).normalized(), (oh.to_3x3() @ rad_l).normalized()
        Q = _ik_pose(rig, Pi, {"r": tw}, {"r": palm}, {"r": hd_}, poles)
        frames.append(_mix_arm(Pi, Q, w))
        hand_tg.append((tw, w))
    frames[0], frames[-1] = dict(PS), dict(PS)
    act = _write_clip(rig, "CLIP_G5_hat", frames)
    relax_cape_action(rig, act, G_N)
    assign(rig, act)
    root.animation_data.action = ra
    old = bpy.data.actions.get("HAT_G5")
    if old:
        bpy.data.actions.remove(old)
    hroot.animation_data_clear()
    errs = []
    for i in range(G_N):
        tw, w = hand_tg[i]
        if w > 0.999:
            sc.frame_set(i + 1)
            bpy.context.view_layer.update()
            errs.append((i + 1, (rig.matrix_world @ rig.pose.bones["hand.r"].head - tw).length))
    for i, M in enumerate(mats):
        hroot.matrix_world = M
        hroot.keyframe_insert("location", frame=i + 1)
        hroot.keyframe_insert("rotation_euler", frame=i + 1)
    ha = hroot.animation_data.action
    ha.name = "HAT_G5"
    ha.use_fake_user = True
    for fc in _act_fcurves(ha):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    hroot.animation_data.action = None
    hroot.matrix_world = R_stand
    CLIP_EXTRA["G5_hat"] = dict(hat="g5")
    W_INFO["G5_hat"] = dict(frames=G_N)
    worst = max(errs, key=lambda e: e[1]) if errs else (0, 0.0)
    log(f"G5 戴帽 v5（魔法）：{G_N} 帧；帽子升到 {z_hi:.2f} m（帽子最低点比头顶高 {G5_CLEAR * 100:.0f} cm）→ 飘到头顶 → 沿轴线落下；"
        f"扶帽檐半径 {grip_r * 100:.0f} cm；手的 IK 误差 最大 {worst[1] * 100:.1f} cm（第 {worst[0]} 帧）")
    root.animation_data.action = None
    return act


def hat_mode(mode):
    """stand：帽子挂在衣帽架上；g5：G5 动作驱动帽子；head：戴在头上（用人物自己的帽子网格）"""
    st = CH_INFO["stand"]
    hroot = HAT_INFO.get("root")
    own = hat_parts(st["coll"])
    for o in HAT_ON_STAND:
        o.hide_render = mode == "head"
    for o in own:
        o.hide_render = mode != "head"
        o.hide_viewport = mode != "head"
    if hroot is not None:
        hroot.animation_data_create()
        hroot.animation_data.action = bpy.data.actions.get("HAT_G5") if mode == "g5" else None
        if mode != "g5" and "R_stand" in HAT_INFO:
            hroot.matrix_world = HAT_INFO["R_stand"]


def curtain_mode(mode):
    """closed：合上；play：G6 动作驱动；open：拉开（形状键 = 1）"""
    for side in ("L", "R"):
        cl = bpy.data.objects.get(f"cab_win_l2_cur_closed_{side}")
        if not cl or not cl.data.shape_keys:
            continue
        key = cl.data.shape_keys
        key.animation_data_create()
        key.animation_data.action = bpy.data.actions.get(f"KEY_G6_{cl.name}") if mode == "play" else None
        if mode != "play":
            key.key_blocks["open"].value = 1.0 if mode == "open" else 0.0


MORNING = [("W_bed_window", "closed", "stand"), ("G6_curtain", "play", "stand"), ("W_window_hat", "open", "stand"),
           ("G5_hat", "open", "g5"), ("W_hat_door", "open", "head")]


_H_HAT = math.atan2(COATSTAND_C[0] - G_SPOT_HAT[0], -(COATSTAND_C[1] - G_SPOT_HAT[1]))   # 面向衣帽架


if B1:
    _sp2 = {k: list(v) for k, v in PATHS.items()}
    build_walk("W_bed_window", [(1.30, 0.42), (1.75, 0.10), (1.92, -0.25), G_SPOT_WIN], h_start=0.0, h_end=math.radians(90))
    build_g6()
    build_walk("W_window_hat", [G_SPOT_WIN, (1.50, -0.70), (0.90, -0.80), (-0.50, -0.25), (-1.30, 0.30), (-1.68, 0.72), G_SPOT_HAT],
               h_start=math.radians(90), h_end=_H_HAT)
    build_g5()
    build_walk("W_hat_door", [G_SPOT_HAT, (-1.80, 1.22), G_SPOT_DOOR], h_start=_H_HAT, h_end=math.radians(180))


def morning_play(name, cm, hm):
    """早上各段：白天的床（铺好的被子）+ 东窗 win_l2 窗帘按片段状态；人物用站姿那份"""
    set_state("day")
    for side in ("L", "R"):
        for st_, vis in (("closed", True), ("open", False), ("gap", False)):
            o = bpy.data.objects.get(f"cab_win_l2_cur_{st_}_{side}")
            if o:
                o.hide_render = not vis
    nf = walk_play(name)
    curtain_mode(cm)
    hat_mode(hm)
    return nf



# ============================================================ 时段切换
def set_state(t):
    for ob, ts in SHOW:
        vis = t in ts
        if isinstance(ob, bpy.types.Collection):
            ob.hide_render = not vis
        else:
            ob.hide_render = not vis
            ob.hide_viewport = not vis


def apply_time(t):
    cfg = TIME_CFG[t]
    dx, dy = cfg["dir"]
    az = math.atan2(-dx, dy)
    SUN.rotation_euler = Euler((math.radians(90 - cfg["el"]), 0, az), "XYZ")
    SUN.data.color = lin(cfg["sun"])
    SUN.data.energy = cfg["power"]
    nt = sc.world.node_tree
    nt.nodes["BG_light"].inputs["Color"].default_value = (*lin(cfg["world"]), 1)
    nt.nodes["BG_light"].inputs["Strength"].default_value = cfg["wpow"]
    nt.nodes["BG_cam"].inputs["Strength"].default_value = 1.0
    rp = nt.nodes["SkyRamp"].color_ramp
    rp.elements[0].color = (*lin(cfg["sky"][0]), 1)
    rp.elements[1].color = (*lin(cfg["sky"][1]), 1)
    for m, st in GLOW:
        em = next(n for n in m.node_tree.nodes if n.type == "EMISSION")
        em.inputs["Strength"].default_value = st.get(t, 0)
    for ob, pw in LIGHTS:
        ob.data.energy = pw.get(t, 0)
        ob.hide_render = pw.get(t, 0) <= 0
    fob.data.color = lin(FILL_COL[t])
    for ng in bpy.data.node_groups:
        n = ng.nodes.get("TimeTint") if hasattr(ng, "nodes") else None
        if n is not None:
            n.outputs[0].default_value = (*lin(cfg["tint"]), 1)
    g = glare_node()
    if g is not None:
        g.inputs["Strength"].default_value = cfg["bloom"]
    om = bpy.data.materials.get("GSD_outline")
    if om is not None:
        em = next(n for n in om.node_tree.nodes if n.type == "EMISSION")
        em.inputs["Color"].default_value = (*lin(cfg["line"]), 1)
    sc.view_settings.exposure = cfg["exposure"]
    set_state(t)
    screen_flicker(t == "late")


FLICKER_DIPS = ((70, 0.30, 4.0), (151, 0.22, 3.0))     # (帧, 变暗比例, 半宽帧数)：每 192 帧暗两下


def flicker_factor(f):
    """深夜屏幕光的明暗系数：整数频率的轻微起伏 + 两次短暂变暗；按 192 帧整周期（第 193 帧 = 第 1 帧）"""
    x = (f - 1) % 192
    k = 1.0 + 0.025 * math.sin(2 * math.pi * 3 * x / 192) + 0.015 * math.sin(2 * math.pi * 7 * x / 192 + 1.3)
    for c, depth, hw in FLICKER_DIPS:
        d = min(abs(x - (c - 1)), 192 - abs(x - (c - 1)))
        if d < hw * 2:
            k -= depth * 0.5 * (1 + math.cos(math.pi * d / (hw * 2)))
    return k


def screen_flicker(on):
    """睡觉时显示器的光微弱地闪：屏幕自发光 + 两盏屏幕灯一起按 flicker_factor 打关键帧；其它时段清掉动画"""
    targets = [(L_MON.data, "energy", None), (L_SPILL.data, "energy", None), (L_ROOM.data, "energy", None)]
    for m in (G_SCREEN, G_SCREEN_UI):
        em = next(n for n in m.node_tree.nodes if n.type == "EMISSION")
        targets.append((m.node_tree, f'nodes["{em.name}"].inputs[1].default_value', em.inputs[1]))
    for idb, path, sock in targets:
        if idb.animation_data:
            idb.animation_data_clear()
    if not on:
        return
    for idb, path, sock in targets:
        base = getattr(idb, path) if sock is None else sock.default_value
        for f in range(1, 194):
            v = base * flicker_factor(f)
            if sock is None:
                setattr(idb, path, v)
                idb.keyframe_insert(path, frame=f)
            else:
                sock.default_value = v
                idb.keyframe_insert(path, frame=f)
        if sock is None:
            setattr(idb, path, base)
        else:
            sock.default_value = base


def glare_node():
    ng = getattr(sc, "compositing_node_group", None)
    return ng.nodes.get("Bloom") if ng else None


def setup_eevee():
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    try:
        sc.view_settings.view_transform = "AgX"
    except Exception:
        pass
    for look in ("AgX - Punchy", "Punchy", "None"):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            continue
    ee = sc.eevee
    for a, v in (("taa_render_samples", SAMPLES), ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 10),
                 ("use_raytracing", True), ("ray_tracing_method", "SCREEN"), ("fast_gi_method", "GLOBAL_ILLUMINATION"),
                 ("fast_gi_distance", 1.5)):
        try:
            setattr(ee, a, v)
        except Exception:
            pass
    sc.render.use_freestyle = False
    if hasattr(sc, "compositing_node_group") and sc.compositing_node_group is None:
        ng = bpy.data.node_groups.new("木屋_后期", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        sc.compositing_node_group = ng
        out = ng.nodes.new("NodeGroupOutput")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.name = "Bloom"
        if "Type" in gl.inputs:
            gl.inputs["Type"].default_value = "Bloom"
            gl.inputs["Threshold"].default_value = 0.9
            gl.inputs["Size"].default_value = 0.7
            gl.inputs["Strength"].default_value = 0.6
        else:
            gl.glare_type = "BLOOM"
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs["Image"], out.inputs["Image"])
        sc.render.use_compositing = True


def hull_outline():
    """人物描边：和 render_island.py 相同的反转外壳（1 cm、背面剔除）"""
    m = bpy.data.materials.get("GSD_outline") or bpy.data.materials.new("GSD_outline")
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.01, 0.01, 0.02, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.use_backface_culling = True
    try:
        m.use_backface_culling_shadow = True
    except Exception:
        pass
    obs = list(HAT_ON_STAND)
    for t in CH_INFO.values():
        obs += [o for o in t["coll"].all_objects if o.type == "MESH" and o.data.polygons]
    n = 0
    for o in obs:
        if any(md.name == "GSD_outline" for md in o.modifiers):
            continue
        if "GSD_outline" not in [mm.name for mm in o.data.materials if mm]:
            o.data.materials.append(m)
        k = len(o.data.materials) - 1
        sca = max(o.matrix_world.to_scale())
        md = o.modifiers.new("GSD_outline", "SOLIDIFY")
        md.thickness = 0.010 / max(sca, 1e-6)
        md.offset = 1.0
        md.use_flip_normals = True
        md.use_rim = False
        md.material_offset = k
        md.material_offset_rim = k
        n += 1
    return n


def render(path, cam, rx, ry, pct):
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.resolution_percentage = pct
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log(f"渲染 {os.path.basename(path)}：{time.time() - t:.1f} 秒")


# ============================================================ 输出
def layout_json():
    d = {
        "version": "cabin_whitebox_v1",
        "units": "m, z up, floor top z=0",
        "room": {"inner_x": [-IX, IX], "inner_y": [-IY, IY], "wall_thickness": WT, "wall_height": WH, "ground_z": GROUND},
        "camera_main": {"type": "ORTHO", "az_deg": CAM_AZ, "el_deg": CAM_EL, "ortho_scale": round(CAM_W, 3),
                        "target": [round(v, 3) for v in CAM_T], "shift_x": 0.035, "resolution": [RES_X, RES_Y]},
        "openings_north_wall_u_is_x": [dict(name=n, center=c, width=w, bottom=z0, top=z1) for n, c, w, z0, z1 in NORTH_OPEN],
        "openings_east_wall_u_is_y": [dict(name=n, center=c, width=w, bottom=z0, top=z1) for n, c, w, z0, z1 in EAST_OPEN],
        "furniture": {
            "desk": dict(center=list(DESK_C), size=[DESK_W, DESK_D], top_z=DESK_TOP),
            "chair": dict(center=list(CHAIR_C), seat_z=CHAIR_SEAT, faces="-y"),
            "bed": dict(x=list(BED_X), y=list(BED_Y), mattress_top_z=BED_TOP, head="+x"),
            "nightstand": dict(center=list(NIGHTSTAND_C), top_z=0.53),
            "coatstand": dict(center=list(COATSTAND_C), top_z=round(1.79 * CS_K, 2)),
            "stove": dict(center=list(STOVE_C)), "rug": dict(center=list(RUG_C), radius=1.0),
            "trunk": dict(center=list(TRUNK_C)),
        },
        "spots": {k: dict(pos=list(v["pos"]), heading_deg=v["h"], use=v["txt"]) for k, v in SPOTS.items()},
        "heading_formula": "heading = atan2(dx, -dy); character faces (sin h, -cos h)",
        "paths": {k: v for k, v in PATHS.items()},
        "curtains": CURTAIN,
        "times": {k: {kk: vv for kk, vv in v.items()} for k, v in TIME_CFG.items()},
    }
    with open(os.path.join(OUT, "layout.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)


layout_json()

# --- Workbench 白模
sc.render.engine = "BLENDER_WORKBENCH"
shd = sc.display.shading
shd.light = "STUDIO"
shd.color_type = "MATERIAL"
shd.show_shadows = True
shd.show_cavity = True
shd.show_object_outline = True
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.view_settings.exposure = 0
sc.render.film_transparent = False
COL["HIDDEN"].hide_render = True
set_state("wb")
if "--render-only" not in ARGV:
    render(os.path.join(OUT, "wb_main.jpg"), CAM_MAIN, RES_X, RES_Y, 75)
    MK.hide_render = False
    render(os.path.join(OUT, "wb_top.jpg"), CAM_TOP, 2000, 1600, 100)
MK.hide_render = True

# ============================================================ 片段清单 + 统一切换入口（给 Windows 正式渲染用）
# 渲染脚本的用法：exec 本脚本（带 --b1 --wb-only），然后
#   for c in CLIPS_CABIN: for cam in c["cams"]: nf = play_clip(c["name"], cam); 渲 1..nf 帧
# play_clip 会设好：时段光照、镜头、显示哪份人物、骨架 / 根物体 / 椅子 / 帽子 / 窗帘动作、B6 特效、窗外背景板。
# 背景层：按 c["bg"] 渲（见 BG_VARIANTS）；c["props"] 里的道具在这个片段里会动，必须归人物层（背景里藏掉）。
BG_VARIANTS = {
    "night": dict(time="night", curtain_l2="closed", hat="stand", chair="under_desk"),
    "late": dict(time="late", curtain_l2="closed", hat="stand", chair="under_desk"),
    "dawn_closed": dict(time="dawn", curtain_l2="closed", hat="stand", chair="under_desk", note="G6 之前：东窗窗帘合着"),
    "dawn_open": dict(time="dawn", curtain_l2="open", hat="stand", chair="under_desk", note="G6 之后、G5 之前：东窗拉开，帽子还在衣帽架上"),
    "dawn_open_nohat": dict(time="dawn", curtain_l2="open", hat="head", chair="under_desk", note="G5 之后：衣帽架空着"),
}
CLIPS_CABIN = [
    dict(name="W_door_desk", kind="walk", time="night", cams=["main"], bg="night", props=["chair"], fade_in=12,
         note="从岛上进门（转场淡入）走到书桌前；椅子自己滑到书桌东北边"),
    dict(name="A4_sit", kind="a4", time="night", cams=["main"], bg="night", props=["chair"], note="坐下，椅子滑到她身后"),
    dict(name="B1_study", kind="b1", time="night", cams=["E_monitor", "A_right34"], bg="night", loop=True,
         note="打字学习循环（192 帧）；书桌两个机位都要"),
    dict(name="B6_smile", kind="b6", time="night", cams=["E_monitor", "A_right34"], bg="night", trigger="task_done", next="B1_study",
         props=["fx"], note="用户完成任务时播放；首尾 = B1 第 1 帧；星光 / 眼里星星 / 红晕在 FX_B6_<机位> 集合里，遮罩必须算进人物层"),
    dict(name="A4_up", kind="a4", time="night", cams=["main"], bg="night", props=["chair"], note="起身"),
    dict(name="W_desk_bed", kind="walk", time="night", cams=["main"], bg="night", props=["chair"], fade_out=12,
         note="走到床边，最后淡出转场（上床不做动画）"),
    dict(name="D2_sleep", kind="d2", time="late", cams=["main"], bg="late", loop=True, fade_in=12, fade_out=12,
         note="深夜睡觉循环（192 帧）：被子呼吸、屏幕光微闪都在背景里，也是 192 帧整周期"),
    dict(name="W_bed_window", kind="morning", time="dawn", cams=["main"], bg="dawn_closed", fade_in=12, curtain="closed", hat="stand",
         note="起床转场后在床边站着淡入，走到东窗"),
    dict(name="G6_curtain", kind="morning", time="dawn", cams=["main"], bg="dawn_closed", props=["curtain_l2"], curtain="play", hat="stand",
         note="拉开东窗窗帘（形状键）：这段东窗窗帘归人物层"),
    dict(name="W_window_hat", kind="morning", time="dawn", cams=["main"], bg="dawn_open", curtain="open", hat="stand", note="走到衣帽架"),
    dict(name="G5_hat", kind="morning", time="dawn", cams=["main"], bg="dawn_open_nohat", props=["hat"], curtain="open", hat="g5",
         note="魔法戴帽：帽子从衣帽架飘到头上（这段帽子归人物层，背景用衣帽架空着的版本）"),
    dict(name="W_hat_door", kind="morning", time="dawn", cams=["main"], bg="dawn_open_nohat", curtain="open", hat="head", fade_out=12,
         note="戴着帽子走到门口，淡出回岛上"),
]


def _cam_obj(cam):
    return CAM_MAIN if cam == "main" else DESK_CAM_OBJS[cam]


def _show_char(which):
    for k, info in CH_INFO.items():
        info["coll"].hide_render = k != which
        info["coll"].hide_viewport = k != which


def clip_frames(c):
    k = c["kind"]
    if k in ("walk", "morning"):
        return W_INFO[c["name"]]["frames"]
    if k == "a4":
        return A4_INFO.get("frames", 1)
    if k == "b1":
        return B1_LOOP
    if k == "b6":
        return B6_N
    return 192


def play_clip(name, cam="main"):
    """把场景切到某个片段（某个机位）：返回帧数。渲染从第 1 帧到返回值。"""
    c = next(x for x in CLIPS_CABIN if x["name"] == name)
    apply_time(c["time"])
    backdrops_on(c["time"], on=(cam != "main"))      # 窗外背景板只给书桌机位用；主镜头剖面视角看不到窗外
    if cam != "main" and not (L_ROOM.data.animation_data and L_ROOM.data.animation_data.action):
        # 书桌机位离这盏照全屋的点光太近：照满会把台灯罩、墙照成一片亮、脸变平（11-27 Codex 复验）→ 只留一部分
        L_ROOM.data.energy *= float(os.environ.get("GSD_ROOM_DESK_K", ROOM_DESK_K))
    sc.camera = _cam_obj(cam)
    sc.render.use_border = False
    fx_on(None, False)
    hat_mode("stand")
    curtain_mode("closed")
    k = c["kind"]
    if k == "walk":
        nf = walk_play(name)
        _show_char("stand")
    elif k == "morning":
        nf = morning_play(name, c.get("curtain", "closed"), c.get("hat", "stand"))
        _show_char("stand")
    elif k == "a4":
        _show_char("seat")
        nf = a4_play(name)
    elif k in ("b1", "b6"):
        _show_char("seat")
        a4_play(None)
        if CHAIR_ROOT:
            CHAIR_ROOT.location.x, CHAIR_ROOT.location.y = B1_CHAIR_XY
        if k == "b6":
            assign(CH_INFO["seat"]["rig"], bpy.data.actions[f"CLIP_B6_smile_{cam}"])
            fx_on(cam)
        nf = clip_frames(c)
    else:                                              # d2
        _show_char("lie")
        nf = 192
    sc.frame_start, sc.frame_end = 1, nf
    sc.frame_set(1)
    return nf


def clips_json():
    d = dict(version="cabin_clips_v1", fps=24, resolution=[RES_X, RES_Y], loop_frames=192,
             cameras={"main": CAM_MAIN.name, **{k: v.name for k, v in DESK_CAM_OBJS.items()}},
             backgrounds=BG_VARIANTS, flow=["W_door_desk", "A4_sit", "B1_study", "(B6_smile 任务完成时)", "A4_up", "W_desk_bed",
                                           "(淡出转场)", "D2_sleep", "(淡出转场)", "W_bed_window", "G6_curtain", "W_window_hat",
                                           "G5_hat", "W_hat_door", "(淡出回岛)"],
             clips=[])
    for c in CLIPS_CABIN:
        e = dict(c)
        e["frames"] = clip_frames(c)
        e.setdefault("loop", False)
        e.setdefault("fade_in", 0)
        e.setdefault("fade_out", 0)
        e.setdefault("props", [])
        e["files"] = {cam: f"{c['name']}_{cam}.webm" if len(c["cams"]) > 1 else f"{c['name']}.webm" for cam in c["cams"]}
        d["clips"].append(e)
    with open(os.path.join(OUT, "clips_cabin.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    log(f"片段清单 clips_cabin.json：{len(d['clips'])} 段")


if B1:
    clips_json()
    hat_mode("stand")
    curtain_mode("closed")
    fx_on(None, False)
    for _k, _info in CH_INFO.items():
        _info["coll"].hide_render = False
    set_state("wb")
    sc.frame_set(1)

if "--render-only" not in ARGV:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "cabin_whitebox.blend"), compress=True)
    log("已保存 cabin_whitebox.blend")

# --- A4 白模视频（主镜头，裁到书桌一带）：--b1 --a4-wb
if B1 and "--a4-wb" in ARGV and A4_INFO:
    from bpy_extras.object_utils import world_to_camera_view
    set_state("night")
    r = sc.render
    sc.camera = CAM_MAIN
    corners = [Vector((x, y, z)) for x in (-1.6, 0.8) for y in (0.2, 2.0) for z in (0.0, 1.9)]
    vs = [world_to_camera_view(sc, CAM_MAIN, p) for p in corners]
    r.use_border, r.use_crop_to_border = True, True
    r.border_min_x, r.border_max_x = max(0, min(v.x for v in vs)), min(1, max(v.x for v in vs))
    r.border_min_y, r.border_max_y = max(0, min(v.y for v in vs)), min(1, max(v.y for v in vs))
    _even = lambda a, b, n: (a, a + 2 * round((b - a) * n / 2) / n)   # 裁切后宽高要是偶数，否则 H.264 报错
    r.border_min_x, r.border_max_x = _even(r.border_min_x, r.border_max_x, RES_X)
    r.border_min_y, r.border_max_y = _even(r.border_min_y, r.border_max_y, RES_Y)
    r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 100
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    for nm in ("A4_sit", "A4_up"):
        nf = a4_play(nm)
        sc.frame_start, sc.frame_end = 1, nf
        r.filepath = os.path.join(OUT, f"a4_wb_{nm}.mp4")
        t_ = time.time()
        bpy.ops.render.render(animation=True)
        log(f"A4 白模视频 {os.path.basename(r.filepath)}：{nf} 帧 {time.time() - t_:.0f} 秒")
    a4_play(None)
    r.use_border = False
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "JPEG"
    sc.frame_set(1)

# --- 走路白模视频（主镜头整幅 50%）：--b1 --walk-wb
if B1 and "--walk-wb" in ARGV and W_INFO:
    set_state("wb")
    r = sc.render
    sc.camera = CAM_MAIN
    r.use_border = False
    r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 50
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    for nm in W_INFO:
        nf = walk_play(nm)
        sc.frame_start, sc.frame_end = 1, nf
        r.filepath = os.path.join(OUT, f"walk_wb_{nm}.mp4")
        t_ = time.time()
        bpy.ops.render.render(animation=True)
        log(f"走路白模视频 {os.path.basename(r.filepath)}：{nf} 帧 {time.time() - t_:.0f} 秒")
    for k, info in CH_INFO.items():
        info["coll"].hide_render = False
    st_ = CH_INFO["stand"]
    st_["root"].animation_data.action = None
    if CHAIR_ROOT and CHAIR_ROOT.animation_data:
        CHAIR_ROOT.animation_data.action = None
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "JPEG"
    set_state("wb")
    sc.frame_set(1)

# --- 早上白模视频：--b1 --morning-wb（走路整幅 50%，G6 / G5 裁近景）
if B1 and "--morning-wb" in ARGV:
    from bpy_extras.object_utils import world_to_camera_view
    r = sc.render
    sc.camera = CAM_MAIN
    CROPS = {"G6_curtain": ((1.0, -1.5, 0.0), (2.4, 0.4, 2.1)), "G5_hat": ((-2.4, 0.4, 0.0), (-1.1, 1.9, 2.1))}
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    _even = lambda a, b, n: (a, a + 2 * round((b - a) * n / 2) / n)
    for nm, cm, hm in MORNING:
        if nm not in W_INFO:
            continue
        nf = morning_play(nm, cm, hm)
        if nm in CROPS:
            a_, b_ = CROPS[nm]
            corners = [Vector((x, y, z)) for x in (a_[0], b_[0]) for y in (a_[1], b_[1]) for z in (a_[2], b_[2])]
            vs = [world_to_camera_view(sc, CAM_MAIN, p) for p in corners]
            r.use_border, r.use_crop_to_border = True, True
            r.border_min_x, r.border_max_x = _even(max(0, min(v.x for v in vs)), min(1, max(v.x for v in vs)), RES_X)
            r.border_min_y, r.border_max_y = _even(max(0, min(v.y for v in vs)), min(1, max(v.y for v in vs)), RES_Y)
            r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 100
        else:
            r.use_border = False
            r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 50
        sc.frame_start, sc.frame_end = 1, nf
        r.filepath = os.path.join(OUT, f"morning_wb_{nm}.mp4")
        t_ = time.time()
        bpy.ops.render.render(animation=True)
        log(f"早上白模视频 {os.path.basename(r.filepath)}：{nf} 帧 {time.time() - t_:.0f} 秒")
    r.use_border = False
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "JPEG"
    hat_mode("stand")
    curtain_mode("closed")
    for k, info in CH_INFO.items():
        info["coll"].hide_render = False
    set_state("wb")
    sc.frame_set(1)

# --- B1 白模动作视频（Workbench，几秒钟一段）：--b1 --b1-wb [--b1-wb-cams E_monitor,A_right34]
if B1 and "--b1-wb" in ARGV:
    set_state("night")
    backdrops_on("night")
    r = sc.render
    r.use_border = False
    r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 50
    r.image_settings.media_type = "VIDEO"         # 5.x：先切到视频再选 FFMPEG
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    sc.frame_start, sc.frame_end = 1, B1_LOOP
    for cam_nm in [x for x in arg("--b1-wb-cams", "E_monitor,A_right34").split(",") if x]:
        sc.camera = DESK_CAM_OBJS[cam_nm]
        r.filepath = os.path.join(OUT, f"b1_wb_{cam_nm}.mp4")
        t_ = time.time()
        bpy.ops.render.render(animation=True)
        log(f"B1 白模视频 {os.path.basename(r.filepath)}：{B1_LOOP} 帧 {time.time() - t_:.0f} 秒")
        a6 = bpy.data.actions.get(f"CLIP_B6_smile_{cam_nm}")
        if a6 is not None:
            rig_ = CH_INFO["seat"]["rig"]
            assign(rig_, a6)
            fx_on(cam_nm)
            sc.frame_start, sc.frame_end = 1, B6_N
            r.filepath = os.path.join(OUT, f"b6_wb_{cam_nm}.mp4")
            t_ = time.time()
            bpy.ops.render.render(animation=True)
            log(f"B6 白模视频 {os.path.basename(r.filepath)}：{B6_N} 帧 {time.time() - t_:.0f} 秒")
            assign(rig_, bpy.data.actions["CLIP_B1_study"])
            fx_on(None, False)
            sc.frame_start, sc.frame_end = 1, B1_LOOP
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "JPEG"
    sc.frame_set(1)

# --- EEVEE 风格预览
if not WB_ONLY:
    COL["HIDDEN"].hide_render = False
    setup_eevee()
    # 室内人物不加描边（用户要求边缘不要任何颜色）；hull_outline() 保留备用
    from bpy_extras.object_utils import world_to_camera_view
    CLOSE = {"night": ("desk", (-1.3, 0.3, 0.0), (0.4, 2.0, 1.6)), "dawn": ("bed", (0.4, 0.6, 0.0), (2.5, 2.0, 1.3)),
             "day": ("center", (-0.7, -1.1, 0.0), (0.8, 0.2, 1.9)), "late": ("bed", (0.4, 0.6, 0.0), (2.5, 2.0, 1.3))}
    for t in RENDER_TIMES:
        apply_time(t)
        render(os.path.join(OUT, f"eevee_{t}.jpg"), CAM_MAIN, RES_X, RES_Y, PCT)
        if "--closeups" in ARGV and t in CLOSE:
            nm, a, b = CLOSE[t]
            corners = [Vector((x, y, z)) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]
            sc.camera = CAM_MAIN
            vs = [world_to_camera_view(sc, CAM_MAIN, p) for p in corners]
            r = sc.render
            r.use_border, r.use_crop_to_border = True, True
            r.border_min_x, r.border_max_x = max(0, min(v.x for v in vs)), min(1, max(v.x for v in vs))
            r.border_min_y, r.border_max_y = max(0, min(v.y for v in vs)), min(1, max(v.y for v in vs))
            render(os.path.join(OUT, f"close_{t}_{nm}.jpg"), CAM_MAIN, RES_X, RES_Y, 100)
            if nm == "bed" and "--headcrop" in ARGV:
                corners = [Vector((x, y, z)) for x in (1.75, 2.4) for y in (1.05, 1.7) for z in (0.45, 0.95)]
                vs = [world_to_camera_view(sc, CAM_MAIN, p) for p in corners]
                r.border_min_x, r.border_max_x = min(v.x for v in vs), max(v.x for v in vs)
                r.border_min_y, r.border_max_y = min(v.y for v in vs), max(v.y for v in vs)
                render(os.path.join(OUT, f"close_{t}_head.jpg"), CAM_MAIN, RES_X * 3, RES_Y * 3, 100)
            r.use_border = False
    if "--deskcams" in ARGV:
        apply_time("night")
        backdrops_on("night")
        only_ = [x for x in arg("--deskcam", "").split(",") if x]       # 只渲某几个，例如 --deskcam A_right34
        for nm_, co_ in DESK_CAM_OBJS.items():
            if only_ and nm_ not in only_:
                continue
            render(os.path.join(OUT, f"deskcam_{nm_}.jpg"), co_, RES_X, RES_Y, PCT)
if not WB_ONLY and "--late-video" in ARGV:              # 深夜：书桌 + 床的近景，192 帧（看屏幕光闪烁）
    from bpy_extras.object_utils import world_to_camera_view
    apply_time("late")
    r = sc.render
    sc.camera = CAM_MAIN
    corners = [Vector((x, y, z)) for x in (-1.1, 2.5) for y in (0.3, 2.0) for z in (0.0, 1.4)]
    vs = [world_to_camera_view(sc, CAM_MAIN, p) for p in corners]
    r.use_border, r.use_crop_to_border = True, True
    r.border_min_x, r.border_max_x = max(0, min(v.x for v in vs)), min(1, max(v.x for v in vs))
    r.border_min_y, r.border_max_y = max(0, min(v.y for v in vs)), min(1, max(v.y for v in vs))
    r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, 100
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    sc.frame_start, sc.frame_end = 1, 192
    r.filepath = os.path.join(OUT, "late_flicker.mp4")
    t_ = time.time()
    bpy.ops.render.render(animation=True)
    log(f"深夜闪烁视频 late_flicker.mp4：192 帧 {time.time() - t_:.0f} 秒")
    r.use_border = False
    r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "JPEG"
if not WB_ONLY and B1 and "--b6-frames" in ARGV:          # B6 对镜头笑：抽几帧出 EEVEE 静帧，例如 --b6-frames 1,20,48,80
    apply_time("night")
    backdrops_on("night")
    sc.render.use_border = False
    rig_ = CH_INFO["seat"]["rig"]
    for cam_nm in [x for x in arg("--b6-cams", "E_monitor,A_right34").split(",") if x]:
        a6 = bpy.data.actions.get(f"CLIP_B6_smile_{cam_nm}")
        if a6 is None:
            continue
        assign(rig_, a6)
        fx_on(cam_nm)
        for f_ in [int(x) for x in arg("--b6-frames", "48").split(",") if x]:
            sc.frame_set(f_)
            render(os.path.join(OUT, f"b6_{cam_nm}_f{f_:03d}.jpg"), DESK_CAM_OBJS[cam_nm], RES_X, RES_Y, PCT)
    assign(rig_, bpy.data.actions["CLIP_B1_study"])
    fx_on(None, False)
    sc.frame_set(1)
if not WB_ONLY and B1 and "--b1-video" in ARGV:
    apply_time("night")
    backdrops_on("night")
    r = sc.render
    r.use_border = False
    r.resolution_x, r.resolution_y, r.resolution_percentage = RES_X, RES_Y, PCT
    r.image_settings.media_type = "VIDEO"         # 5.x：先切到视频再选 FFMPEG
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "HIGH"
    r.fps = 24
    sc.frame_start, sc.frame_end = 1, B1_LOOP
    for cam_nm in [x for x in arg("--b1-cams", "E_monitor").split(",") if x]:
        sc.camera = DESK_CAM_OBJS[cam_nm] if cam_nm in DESK_CAM_OBJS else CAM_MAIN
        r.filepath = os.path.join(OUT, f"b1_study_{cam_nm}.mp4")
        t_ = time.time()
        bpy.ops.render.render(animation=True)
        log(f"B1 视频 {os.path.basename(r.filepath)}：{B1_LOOP} 帧 {time.time() - t_:.0f} 秒")
log("全部完成")
