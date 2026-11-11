# -*- coding: utf-8 -*-
"""
共生岛 · Blender 场景 v4（按效果图重排 + 明亮温暖的夜景）
=====================================
在 v3 的建模函数（材质、草地粒子、树、灯笼、栅栏、樱花、小桥……）基础上：
  · 布局按效果图重排：用「效果图上的屏幕位置」反算世界坐标（S() 函数），
    岛形轮廓、木屋、码头和小船、石板路、樱花与野餐桌、拱桥和瀑布、鸭子、睡莲、芦苇都对齐到图上的位置
  · 新木屋：正面朝镜头右下，山墙朝左下，大窗户夜里发暖光；门廊木平台绕到左侧，连着码头
  · 石板路（Voronoi 石块 + 灰缝），路边有更多灯笼
  · 远处海平线：对岸小岛、亮灯的小房子、月亮、星星、月光在水面上的碎光
  · 夜景提亮：月光加强、环境光提亮、灯笼和窗户更亮、加暖色补光、曝光微调

人物不在本脚本里建模：仍由 import_character.py 导入伊蕾娜，站在门廊台阶前的石板路上。

用法（终端，不开界面）：
  /Applications/Blender.app/Contents/MacOS/Blender -b -P ~/Desktop/共生岛/blender/preview_v4.py -- night 50
"""

import bpy
import bmesh
import builtins
import math
import os
import random
from mathutils import Matrix, Euler, Vector

ROOT_V4 = os.path.expanduser("~/Desktop/共生岛/blender")

# ------------------------------------------------------------
# 载入 v3 的全部函数（不搭建），之后在这里覆盖需要改的部分
# ------------------------------------------------------------
_ATTACH_V4 = bool(globals().get("GSD_ATTACH"))
globals()["GSD_ATTACH"] = True
_p = os.path.join(ROOT_V4, "gongshengdao_scene_v3.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), globals())
GSD_ATTACH = _ATTACH_V4

_apply_time_v3 = apply_time
_rebind_v3 = rebind
_build_materials_v3 = build_materials

# ============================================================
# 配置
# ============================================================
CAM_AZIMUTH = -28.0      # 镜头在左前方：木屋正面朝右下，山墙朝左下（和效果图一致）
CAM_ELEVATION = 42.0
CAM_ORTHO_SCALE = 24.0
GRASS_COUNT = 15000
FLOWER_COUNT = 3200
ISLAND_TOP = 0.45
HORIZON_FY = 0.075        # 海平线在画面上的高度（0=顶，1=底）
SEED = 11
_AR = RES_Y / RES_X

# 效果图里岛的轮廓（屏幕比例坐标，x 向右，y 向下）
OUTLINE_F = [(0.035, 0.44), (0.09, 0.33), (0.18, 0.24), (0.30, 0.17), (0.44, 0.15), (0.57, 0.19),
             (0.70, 0.26), (0.84, 0.31), (0.95, 0.40), (0.995, 0.54), (0.97, 0.68), (0.90, 0.80),
             (0.81, 0.91), (0.68, 1.02), (0.50, 1.07), (0.33, 1.05), (0.23, 0.97), (0.17, 0.86),
             (0.11, 0.74), (0.06, 0.62), (0.035, 0.52)]

# 木屋尺寸（世界单位≈米）
HOUSE_W, HOUSE_D, HOUSE_H, HOUSE_RH = 5.2, 4.2, 2.5, 2.0
HOUSE_CORNER_F = (0.115, 0.55)   # 正面左下墙角在画面上的位置

PALETTE.update({
    "roof": (0.27, 0.36, 0.38), "roof_dark": (0.20, 0.27, 0.30),
    "far_island": (0.20, 0.33, 0.29), "far_tree": (0.15, 0.28, 0.24),
    "cobble": (0.86, 0.72, 0.52),
})

# ============================================================
# 屏幕坐标 ↔ 世界坐标
# ============================================================

def _cam_basis():
    az, el = math.radians(CAM_AZIMUTH), math.radians(CAM_ELEVATION)
    back = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    f = -back
    r = f.cross(Vector((0, 0, 1))).normalized()
    u = r.cross(f).normalized()
    return f, r, u


def S(fx, fy, z=None):
    """效果图上的屏幕位置 (fx, fy) → 世界坐标 (x, y)，落在高度 z 的水平面上（默认岛面）"""
    if z is None:
        z = ISLAND_TOP
    f, r, u = _cam_basis()
    Wd = CAM_ORTHO_SCALE
    Ht = Wd * _AR
    T = Vector(CAM_TARGET)
    p0 = T + r * ((fx - 0.5) * Wd + CAM_SHIFT_X * Wd) + u * ((0.5 - fy) * Ht + CAM_SHIFT_Y * Wd)
    t = (z - p0.z) / f.z
    p = p0 + f * t
    return (p.x, p.y)


def S3(fx, fy, z=None):
    x, y = S(fx, fy, z)
    return (x, y, ISLAND_TOP if z is None else z)


def screen_angle():
    """画面水平方向在世界里的角度（用于把桌子、码头、水面闪光摆成和画面平行）"""
    _, r, _ = _cam_basis()
    return math.atan2(r.y, r.x)


# ============================================================
# 岛形：按效果图轮廓
# ============================================================
_RAD = []


def _ray_poly(theta, poly):
    dx, dy = math.cos(theta), math.sin(theta)
    best = 0.0
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        det = -dx * ey + ex * dy
        if abs(det) < 1e-9:
            continue
        t = (-ax * ey + ex * ay) / det
        s = (dx * ay - dy * ax) / det
        if t > 0 and -1e-6 <= s <= 1 + 1e-6:
            best = max(best, t)
    return best


def island_radius(theta):
    if not _RAD:
        return 1.0
    n = len(_RAD)
    a = (theta % (2 * math.pi)) / (2 * math.pi) * n
    i = int(a) % n
    k = a - int(a)
    r = _RAD[i] * (1 - k) + _RAD[(i + 1) % n] * k
    return r + 0.012 * math.sin(9 * theta) + 0.008 * math.sin(14 * theta + 1.0)


# ============================================================
# 布局（全部在建模前算好）
# ============================================================
L = {}   # 布局数据


def compute_layout():
    global CAM_TARGET, CAM_SHIFT_X, CAM_SHIFT_Y, ISLAND_RX, ISLAND_RY, PATHS, FLAT_ZONES, HILLS, NOGRASS, SPARSE
    cx = sum(p[0] for p in OUTLINE_F) / len(OUTLINE_F)
    cy = sum(p[1] for p in OUTLINE_F) / len(OUTLINE_F)
    CAM_TARGET = (0.0, 0.0, ISLAND_TOP)
    CAM_SHIFT_X = 0.5 - cx
    CAM_SHIFT_Y = (cy - 0.5) * _AR
    poly = [S(fx, fy) for fx, fy in OUTLINE_F]
    raw = [_ray_poly(2 * math.pi * i / 360, poly) for i in range(360)]
    R0 = sum(raw) / len(raw)
    ISLAND_RX = ISLAND_RY = R0
    sm = []
    for i in range(360):
        sm.append(sum(raw[(i + k) % 360] for k in range(-4, 5)) / 9)
    _RAD[:] = [v / R0 for v in sm]

    # ---------- 木屋 ----------
    gx, gy = S(*HOUSE_CORNER_F)
    hx, hy = gx + HOUSE_W / 2, gy + HOUSE_D / 2
    L["house"] = (hx, hy)
    py0 = hy - HOUSE_D / 2 - 0.95                 # 门廊中线
    x0 = hx - HOUSE_W / 2 - 1.95                   # 门廊最左
    x1 = hx + HOUSE_W / 2 + 0.3                    # 门廊最右
    L["porch"] = (py0, x0, x1)
    sx = x1 - 0.75                                 # 台阶
    stairs_bottom = (sx, py0 - 0.9 - 1.15)
    L["stairs"] = stairs_bottom
    char = (sx + 0.85, py0 - 3.1)
    L["char"] = char
    builtins.GSD_CHAR_POS = (char[0], char[1], ISLAND_TOP)
    builtins.GSD_CAM_AZ = CAM_AZIMUTH

    # ---------- 道路 ----------
    main = [stairs_bottom, char, S(0.405, 0.64), S(0.38, 0.73), S(0.35, 0.83), S(0.37, 0.94), S(0.42, 1.10)]
    back = [char, S(0.45, 0.50), S(0.445, 0.40), S(0.43, 0.31), S(0.445, 0.22)]
    a, b = S(0.79, 0.645), S(0.885, 0.61)
    L["bridge"] = (a, b)
    toward_bridge = [S(0.405, 0.63), S(0.50, 0.615), S(0.60, 0.62), S(0.70, 0.635), a]
    after_bridge = [b, S(0.95, 0.585), S(1.03, 0.55)]
    PATHS = {
        "path_main": (main, 1.5),
        "path_back": (back, 1.2),
        "path_bridge": (toward_bridge, 1.3),
        "path_east": (after_bridge, 1.1),
    }

    # ---------- 小溪：从右上林间流下，过桥，到岛边变成瀑布 ----------
    pts = [S(0.905, 0.33), S(0.875, 0.44), S(0.85, 0.54), S(0.84, 0.625), S(0.855, 0.70), S(0.875, 0.77)]
    lx, ly = pts[-1]
    th = math.atan2(ly / ISLAND_RY, lx / ISLAND_RX)
    ex, ey = island_edge(th)
    pts += [(ex * 0.93, ey * 0.93), (ex, ey)]
    L["stream"] = pts

    # ---------- 地形 ----------
    FLAT_ZONES = [(hx, hy - 0.6, 5.2), (*S(0.455, 0.86), 2.2), (*S(0.53, 0.80), 1.7), (*a, 1.4), (*b, 1.4),
                  (*S(0.605, 0.90), 0.8)]
    HILLS = []
    for fx, fy, rr, A in ((0.48, 0.30, 2.6, 0.55), (0.72, 0.36, 3.0, 0.7), (0.93, 0.47, 2.3, 0.55),
                          (0.62, 0.95, 2.0, 0.22), (0.24, 0.88, 2.0, 0.22), (0.60, 0.72, 1.6, 0.18)):
        X, Y = S(fx, fy)
        HILLS.append((X, Y, rr, A))
    # 不长草的区域：木屋 + 门廊（世界坐标矩形）
    NOGRASS = [(x0 - 0.1, hx + HOUSE_W / 2 + 0.6, py0 - 1.0, hy + HOUSE_D / 2 + 0.4)]
    SPARSE = [(*S(0.455, 0.86), 1.4, 0.2)]


NOGRASS = []
SPARSE = []


def _stream_pts():
    return L["stream"]


def grass_weight(x, y):
    if _rr(x, y) > 0.965:
        return 0.0
    w = _smooth((line_dist(x, y) - 0.08) / 0.35)
    for x0, x1, y0, y1 in NOGRASS:
        if x0 < x < x1 and y0 < y < y1:
            return 0.0
    for cx, cy, rr, k in SPARSE:
        w = min(w, k + _smooth((math.hypot(x - cx, y - cy) - rr) / 0.8))
    return w


def flower_weight(x, y):
    g = grass_weight(x, y)
    meadow = 0.5 + 0.5 * math.sin(1.3 * x + 0.3) * math.cos(1.1 * y + 1.0)
    edge = 1.0 - _smooth(abs(line_dist(x, y) - 0.6) / 0.7)
    return g * max(_smooth((meadow - 0.45) / 0.3), 0.85 * edge)


compute_layout()

# ============================================================
# 夜景提亮：时段参数、灯光功率、自发光强度
# ============================================================
LANTERN_POWER = {"morning": 10.0, "noon": 0.0, "night": 260.0}
WINDOW_POWER = {"morning": 15.0, "noon": 0.0, "night": 320.0}
FILL_POWER = {"morning": 0.0, "noon": 0.0, "night": 300.0}


def _moon_az():
    """月光从画面左上方偏左照过来"""
    f, r, u = _cam_basis()
    fg = Vector((f.x, f.y, 0)).normalized()
    frm = (-r * 1.0 + fg * 0.35).normalized()
    return math.degrees(math.atan2(frm.x, -frm.y))


TIMES["morning"]["exposure"] = 0.0
TIMES["noon"]["exposure"] = 0.0
TIMES["night"] = dict(el=36, az=_moon_az(), sun=(0.62, 0.72, 1.0), power=1.05, sky=(0.09, 0.13, 0.30), sky_power=0.55,
                      tint=(0.72, 0.74, 0.92), bloom=1.0, line=(0.08, 0.08, 0.14), haze=0.006,
                      haze_col=(0.62, 0.68, 0.95), exposure=0.1)

# 夜里海水换成深蓝（近岸 → 远海），白天恢复原色
SEA_NIGHT = [(0.10, 0.34, 0.50), (0.06, 0.19, 0.40), (0.03, 0.09, 0.26)]


def set_glow(m, **kw):
    for i, (mm, st) in enumerate(GLOW_MATS):
        if mm == m:
            st = dict(st)
            st.update(kw)
            GLOW_MATS[i] = (mm, st)
            mm["gsd_strengths"] = st
            return


def cobble_material(name, rgb=(0.86, 0.72, 0.52), mortar=(0.42, 0.34, 0.27), scale=2.3):
    """石板路：Voronoi 石块 + 深色灰缝 + 每块石头深浅不同 + 凹凸"""
    m = _new_material(name)
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    bsdf = N.new("ShaderNodeBsdfPrincipled")
    geo = N.new("ShaderNodeNewGeometry")
    vor = N.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    _set(vor.inputs, "Scale", scale)
    _set(vor.inputs, "Randomness", 0.85)
    Lk.new(geo.outputs["Position"], vor.inputs["Vector"])
    edge = N.new("ShaderNodeMapRange")
    _set(edge.inputs, "From Min", 0.02)
    _set(edge.inputs, "From Max", 0.08)
    Lk.new(vor.outputs["Distance"], edge.inputs["Value"])
    vor2 = N.new("ShaderNodeTexVoronoi")
    _set(vor2.inputs, "Scale", scale)
    _set(vor2.inputs, "Randomness", 0.85)
    Lk.new(geo.outputs["Position"], vor2.inputs["Vector"])
    bw = N.new("ShaderNodeRGBToBW")
    Lk.new(vor2.outputs["Color"], bw.inputs["Color"])
    mr = N.new("ShaderNodeMapRange")
    _set(mr.inputs, "To Min", 0.80)
    _set(mr.inputs, "To Max", 1.15)
    Lk.new(bw.outputs["Val"], mr.inputs["Value"])
    hs = N.new("ShaderNodeHueSaturation")
    hs.inputs["Color"].default_value = (*lin(rgb), 1)
    Lk.new(mr.outputs["Result"], hs.inputs["Value"])
    col = mix_color(nt, edge.outputs["Result"], tuple(lin(mortar)), hs.outputs["Color"])
    ao = N.new("ShaderNodeAmbientOcclusion")
    _set(ao.inputs, "Distance", 0.4)
    Lk.new(col, ao.inputs["Color"])
    Lk.new(ao.outputs["Color"], bsdf.inputs["Base Color"])
    bump = N.new("ShaderNodeBump")
    _set(bump.inputs, "Strength", 0.45)
    Lk.new(edge.outputs["Result"], bump.inputs["Height"])
    Lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf.inputs, "Roughness", 0.85)
    _set(bsdf.inputs, "Specular IOR Level", 0.25)
    Lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    return m


def build_materials():
    M = _build_materials_v3()
    set_glow(M["window"], night=9.0)
    set_glow(M["lantern"], night=12.0)
    set_glow(M["firefly"], night=14.0)
    set_glow(M["laptop_screen"], night=3.0)
    M["cobble"] = cobble_material("T_cobble")
    M["moon"] = glow("G_moon", (1.0, 0.95, 0.82), {"morning": 0.0, "noon": 0.0, "night": 7.0})
    M["star"] = glow("G_star", (0.90, 0.93, 1.0), {"morning": 0.0, "noon": 0.0, "night": 5.0})
    M["glint_moon"] = glow("G_glint_moon", (0.86, 0.92, 1.0), {"morning": 0.0, "noon": 0.0, "night": 4.0})
    M["glint_warm"] = glow("G_glint_warm", (1.0, 0.74, 0.40), {"morning": 0.0, "noon": 0.0, "night": 4.5})
    M["fire_outer"] = glow("G_fire_outer", (1.0, 0.42, 0.10), {"morning": 0.0, "noon": 0.0, "night": 16.0})
    M["fire_inner"] = glow("G_fire_inner", (1.0, 0.80, 0.32), {"morning": 0.0, "noon": 0.0, "night": 24.0})
    M["ember"] = glow("G_ember", (1.0, 0.55, 0.18), {"morning": 0.0, "noon": 0.0, "night": 12.0})
    M["far_window"] = glow("G_far_window", (1.0, 0.76, 0.42), {"morning": 0.3, "noon": 0.1, "night": 8.0})
    return M


def area_light(coll, name, loc, rgb, powers, size=6.0):
    """大面积柔和补光（不投影），模拟灯笼照亮地面的暖色光晕"""
    ld = bpy.data.lights.new(name, "AREA")
    try:
        ld.shape = "DISK"
    except Exception:
        pass
    ld.size = size
    ld.color = lin(rgb)
    ld.energy = powers["night"]
    ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    coll.objects.link(ob)
    LIGHTS.append((ob, powers))
    ob["gsd_powers"] = powers
    return ob


def rebind():
    _rebind_v3()
    have = {ob.name for ob, _ in LIGHTS}
    for ob in bpy.data.objects:
        if ob.type == "LIGHT" and ob.data.type != "POINT" and ob.get("gsd_powers") is not None and ob.name not in have:
            LIGHTS.append((ob, dict(ob["gsd_powers"])))


def apply_time(name):
    _apply_time_v3(name)
    t = TIMES[name]
    sc = bpy.context.scene
    try:
        sc.view_settings.exposure = t.get("exposure", 0.0)
    except Exception:
        pass
    sea = bpy.data.materials.get("W_sea")
    ramp = next((n for n in sea.node_tree.nodes if n.type == "VALTORGB"), None) if sea else None
    if ramp is not None:
        els = ramp.color_ramp.elements
        if sea.get("gsd_sea_day") is None:
            sea["gsd_sea_day"] = [list(e.color) for e in els]
        if name == "night":
            for e, c in zip(els, SEA_NIGHT):
                e.color = (*lin(c), 1)
        else:
            for e, c in zip(els, sea["gsd_sea_day"]):
                e.color = tuple(c)
    for ob in bpy.data.objects:
        show = ob.get("gsd_show")
        if show is not None:
            vis = name in str(show).split(",")
            ob.hide_render = not vis
            ob.hide_viewport = not vis


def only_at(ob, times):
    if ob is not None:
        ob["gsd_show"] = times
    return ob


# ============================================================
# 新道具
# ============================================================

def window_v4(coll, LC, M, nm, cx, cy, cz, face, w=0.95, h=1.0, box=True):
    """窗户：发光玻璃 + 窗框 + 十字窗棂 + 花箱 + 窗外暖光。face: front(-Y) / left(-X) / right(+X)"""
    nx, ny = {"front": (0, -1), "left": (-1, 0), "right": (1, 0)}[face]
    along_x = face == "front"

    def sz(a, d, hh):
        return (a, d, hh) if along_x else (d, a, hh)

    def off(d, t=0.0):
        return (cx + nx * d + (t if along_x else 0.0), cy + ny * d + (0.0 if along_x else t))

    gx, gy = off(0.03)
    shape(nm + "_glass", "cube", coll, M["window"], loc=(gx, gy, cz), scale=sz(w, 0.05, h))
    fr = []
    for dz in (-h / 2 - 0.04, h / 2 + 0.04):
        px, py = off(0.07)
        fr.append(((px, py, cz + dz), sz(w + 0.18, 0.1, 0.1), (0, 0, 0)))
    for t in (-w / 2 - 0.04, w / 2 + 0.04):
        px, py = off(0.07, t)
        fr.append(((px, py, cz), sz(0.1, 0.1, h + 0.18), (0, 0, 0)))
    px, py = off(0.08)
    fr.append(((px, py, cz), sz(w, 0.06, 0.05), (0, 0, 0)))
    fr.append(((px, py, cz), sz(0.05, 0.06, h), (0, 0, 0)))
    batch(nm + "_frame", "cube", coll, M["wood_dark"], fr)
    if box:
        bx, by = off(0.22)
        shape(nm + "_box", "cube", coll, M["wood"], loc=(bx, by, cz - h / 2 - 0.18), scale=sz(w + 0.12, 0.3, 0.2))
        fl, lv = [], []
        for k in range(9):
            t = (k / 8 - 0.5) * w
            qx, qy = off(0.24 + random.uniform(-0.05, 0.05), t)
            fl.append(((qx, qy, cz - h / 2 - 0.02 + random.uniform(0, 0.07)), (0.085, 0.085, 0.075), (0, 0, 0)))
            qx, qy = off(0.3, t)
            lv.append(((qx, qy, cz - h / 2 - 0.12), (0.12, 0.1, 0.08), (0, 0, 0)))
        batch(nm + "_fl_a", "ico", coll, M["pink"], fl[::3], sub=1)
        batch(nm + "_fl_b", "ico", coll, M["white"], fl[1::3], sub=1)
        batch(nm + "_fl_c", "ico", coll, M["purple"], fl[2::3], sub=1)
        batch(nm + "_fl_leaf", "ico", coll, M["leaf2"], lv, sub=1, jitter=0.1)
    lx, ly = off(0.8)
    point_light(LC, nm + "_light", (lx, ly, cz - 0.2), (1.0, 0.70, 0.40), WINDOW_POWER, radius=0.45)


def ivy_line(prefix, coll, M, p0, p1, n=10, s=0.2, drop=0.0, flowers=("white", "yellow")):
    """沿屋檐的藤蔓（一串叶团 + 小花 + 少量垂下的藤）"""
    leaves, hang, fl = [], [], {c: [] for c in flowers}
    for k in range(n):
        t = k / max(n - 1, 1)
        x = p0[0] + (p1[0] - p0[0]) * t + random.uniform(-0.05, 0.05)
        y = p0[1] + (p1[1] - p0[1]) * t + random.uniform(-0.05, 0.05)
        z = p0[2] + (p1[2] - p0[2]) * t
        ss = s * random.uniform(0.8, 1.25)
        leaves.append(((x, y, z), (ss, ss, ss * 0.8), (0, 0, 0)))
        if drop and random.random() < 0.4:
            d = random.uniform(0.3, drop)
            hang.append(((x, y, z - d / 2), (ss * 0.45, ss * 0.45, d / 2), (0, 0, 0)))
        if random.random() < 0.6:
            c = flowers[k % len(flowers)]
            fl[c].append(((x + random.uniform(-0.1, 0.1), y + random.uniform(-0.1, 0.1), z + ss * 0.6),
                          (0.05, 0.05, 0.05), (0, 0, 0)))
    batch(prefix, "ico", coll, M["leaf"], leaves, sub=1, jitter=0.08)
    batch(prefix + "_hang", "ico", coll, M["leaf2"], hang, sub=1, jitter=0.05)
    for c, items in fl.items():
        batch(f"{prefix}_fl_{c}", "ico", coll, M[c], items, sub=1)


def build_house_v4(coll, LC, M, x, y, z):
    W, D, H, rh, ov = HOUSE_W, HOUSE_D, HOUSE_H, HOUSE_RH, 0.5
    zb = z + 0.4
    zr = zb + H

    # 石砌地基
    stones = []
    for side, (ax, ay, bx, by) in enumerate(((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1))):
        n = 10 if side % 2 == 0 else 8
        for i in range(n):
            t = (i + 0.5) / n
            px = x + (ax + (bx - ax) * t) * (W / 2 + 0.12)
            py = y + (ay + (by - ay) * t) * (D / 2 + 0.12)
            for lvl in range(2):
                stones.append(((px + random.uniform(-0.05, 0.05), py + random.uniform(-0.05, 0.05), z + 0.1 + lvl * 0.2),
                               (0.26 + random.uniform(0, 0.12), 0.26 + random.uniform(0, 0.12), 0.11),
                               (0, 0, random.uniform(0, 1))))
    batch("house_stones", "ico", coll, M["stone"], stones, sub=1, jitter=0.08)
    shape("house_floor", "cube", coll, M["stone"], loc=(x, y, z + 0.2), scale=(W + 0.1, D + 0.1, 0.4))

    # 墙 + 半木结构
    shape("house_wall", "cube", coll, M["wall"], loc=(x, y, zb + H / 2), scale=(W, D, H))
    beams = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            beams.append(((x + sx * W / 2, y + sy * D / 2, zb + H / 2), (0.2, 0.2, H), (0, 0, 0)))
    for zz in (zb + 0.05, zb + H * 0.52, zb + H - 0.05):
        beams.append(((x, y - D / 2 - 0.02, zz), (W, 0.12, 0.14), (0, 0, 0)))
        beams.append(((x - W / 2 - 0.02, y, zz), (0.12, D, 0.14), (0, 0, 0)))
        beams.append(((x + W / 2 + 0.02, y, zz), (0.12, D, 0.14), (0, 0, 0)))
    for px in (x - W * 0.04, x + W * 0.2):
        beams.append(((px, y - D / 2 - 0.02, zb + H / 2), (0.14, 0.12, H), (0, 0, 0)))
    beams.append(((x - W / 2 - 0.02, y, zb + H / 2), (0.12, 0.14, H), (0, 0, 0)))
    beams.append(((x - W * 0.04 - 0.55, y - D / 2 - 0.03, zb + H * 0.26), (0.1, 0.1, 1.0), (0, math.radians(48), 0)))
    beams.append(((x - W / 2 - 0.03, y - D * 0.32, zb + H * 0.76), (0.1, 0.1, 0.95), (math.radians(48), 0, 0)))
    beams.append(((x - W / 2 - 0.03, y + D * 0.32, zb + H * 0.76), (0.1, 0.1, 0.95), (math.radians(-48), 0, 0)))
    batch("house_beams", "cube", coll, M["wood_dark"], beams)

    # 山墙（两端三角）+ 木条 + 山墙窗
    gv = [(x - W / 2, y - D / 2, zr), (x - W / 2, y + D / 2, zr), (x - W / 2, y, zr + rh - 0.15),
          (x + W / 2, y - D / 2, zr), (x + W / 2, y + D / 2, zr), (x + W / 2, y, zr + rh - 0.15)]
    from_pydata("house_gable", gv, [(0, 1, 2), (3, 5, 4)], coll, M["wall"])
    trim = []
    for sx in (-1, 1):
        trim.append(((x + sx * (W / 2 + 0.03), y, zr + 0.05), (0.1, D, 0.12), (0, 0, 0)))
        trim.append(((x + sx * (W / 2 + 0.03), y - 0.55, zr + rh * 0.3), (0.1, 0.1, rh * 0.55), (0, 0, 0)))
        trim.append(((x + sx * (W / 2 + 0.03), y + 0.55, zr + rh * 0.3), (0.1, 0.1, rh * 0.55), (0, 0, 0)))
    batch("house_gable_trim", "cube", coll, M["wood_dark"], trim)
    window_v4(coll, LC, M, "house_win_g", x - W / 2 - 0.02, y, zr + 0.62, "left", w=0.7, h=0.62, box=False)

    # 屋顶（两坡瓦片，屋脊沿 X）
    ang = math.atan2(rh, D / 2 + ov)
    slope_len = math.hypot(rh, D / 2 + ov)
    rows = 8
    tiles_a, tiles_b = [], []
    for side in (-1, 1):
        for r in range(rows):
            t = (r + 0.5) / rows
            py = y + side * (D / 2 + ov) * (1 - t)
            pz = zr - 0.1 + rh * t
            cols = 10
            span = W + 2 * ov
            step = span / cols
            left = x - W / 2 - ov
            centers = [left + step * (c + 0.5) for c in range(cols)] if r % 2 == 0 else \
                      [left + step * 0.25] + [left + step * c for c in range(1, cols)] + [left + span - step * 0.25]
            for c, px in enumerate(centers):
                w_ = step * (0.5 if (r % 2 and (c == 0 or c == len(centers) - 1)) else 1.02)
                item = ((px, py, pz + 0.05), (w_, slope_len / rows * 1.25, 0.1), (side * -ang, 0, 0))
                (tiles_b if (r * 7 + c * 3) % 5 == 0 else tiles_a).append(item)
    batch("house_roof_tiles", "cube", coll, M["roof"], tiles_a)
    batch("house_roof_tiles_dark", "cube", coll, M["roof_dark"], tiles_b)
    v = [(x - W / 2 - ov, y - D / 2 - ov, zr - 0.12), (x + W / 2 + ov, y - D / 2 - ov, zr - 0.12),
         (x + W / 2 + ov, y, zr + rh - 0.05), (x - W / 2 - ov, y, zr + rh - 0.05),
         (x - W / 2 - ov, y + D / 2 + ov, zr - 0.12), (x + W / 2 + ov, y + D / 2 + ov, zr - 0.12)]
    under = from_pydata("house_roof_base", v, [(0, 1, 2, 3), (3, 2, 5, 4)], coll, M["roof_dark"])
    under.modifiers.new("厚度", "SOLIDIFY").thickness = 0.12
    shape("house_ridge", "cyl", coll, M["roof_dark"], loc=(x, y, zr + rh + 0.05), scale=(0.16, 0.16, W + 2 * ov + 0.1),
          rot=(0, math.pi / 2, 0), seg=8)
    batch("house_fascia", "cube", coll, M["wood_dark"],
          [((x + sx * (W / 2 + ov), y + sy * (D / 4 + ov / 2), zr + rh / 2 - 0.05), (0.12, slope_len, 0.16), (sy * -ang, 0, 0))
           for sx in (-1, 1) for sy in (-1, 1)])
    # 藤蔓：正面屋檐 + 左侧山墙斜边
    ivy_line("house_ivy_eave", coll, M, (x - W / 2 - ov, y - D / 2 - ov + 0.05, zr - 0.02),
             (x + W / 2 - 0.6, y - D / 2 - ov + 0.05, zr - 0.02), n=16, s=0.2, drop=0.7)
    ivy_line("house_ivy_gable", coll, M, (x - W / 2 - ov - 0.03, y - D / 2 - ov, zr - 0.05),
             (x - W / 2 - ov - 0.03, y, zr + rh - 0.1), n=9, s=0.18, drop=0.4)
    ivy_line("house_ivy_corner", coll, M, (x - W / 2 - 0.08, y - D / 2 - 0.08, zb),
             (x - W / 2 - 0.08, y - D / 2 - 0.08, zr), n=9, s=0.17)

    # 烟囱 + 炊烟（屋顶右后方）
    cxh, cyh = x + W * 0.3, y + D * 0.2
    st = []
    for lvl in range(7):
        st.append(((cxh, cyh, zr + 0.5 + lvl * 0.3), (0.62, 0.62, 0.32), (0, 0, random.uniform(-0.05, 0.05))))
    batch("house_chimney", "cube", coll, M["stone"], st, jitter=0.03)
    shape("house_chimney_cap", "cube", coll, M["rock_dark"], loc=(cxh, cyh, zr + 2.6), scale=(0.75, 0.75, 0.1))
    smoke("house_smoke", coll, M, cxh + 0.1, cyh + 0.1, zr + 3.0)

    # 门（正面右侧，靠台阶）
    dx = x + W / 2 - 0.95
    shape("house_door", "cube", coll, M["wood"], loc=(dx, y - D / 2 - 0.04, zb + 0.98), scale=(0.95, 0.06, 1.95))
    batch("house_door_planks", "cube", coll, M["wood_dark"],
          [((dx + k * 0.24, y - D / 2 - 0.08, zb + 0.98), (0.03, 0.03, 1.9), (0, 0, 0)) for k in (-1, 0, 1)] +
          [((dx, y - D / 2 - 0.06, zb + 2.0), (1.15, 0.1, 0.14), (0, 0, 0))])
    shape("house_door_knob", "sphere", coll, M["metal"], loc=(dx + 0.32, y - D / 2 - 0.12, zb + 0.95), scale=(0.05, 0.05, 0.05))
    shape("house_door_window", "cube", coll, M["window"], loc=(dx, y - D / 2 - 0.08, zb + 1.55), scale=(0.4, 0.03, 0.35))
    # 门边壁灯
    shape("house_wall_lamp", "cube", coll, M["lantern"], loc=(dx - 0.72, y - D / 2 - 0.14, zb + 1.75), scale=(0.16, 0.16, 0.22))
    shape("house_wall_lamp_cap", "cone", coll, M["roof_dark"], loc=(dx - 0.72, y - D / 2 - 0.14, zb + 1.92),
          scale=(0.15, 0.15, 0.1), seg=4, rot=(0, 0, math.pi / 4))
    point_light(LC, "house_wall_lamp_light", (dx - 0.72, y - D / 2 - 0.45, zb + 1.7), (1.0, 0.72, 0.42), LANTERN_POWER)

    # 窗户：正面两扇、左侧山墙两扇（大）
    window_v4(coll, LC, M, "house_win_f1", x - W / 2 + 0.95, y - D / 2 - 0.02, zb + 1.3, "front", w=1.05, h=1.05)
    window_v4(coll, LC, M, "house_win_f2", x - 0.35, y - D / 2 - 0.02, zb + 1.3, "front", w=1.05, h=1.05)
    window_v4(coll, LC, M, "house_win_l1", x - W / 2 - 0.02, y - 0.85, zb + 1.3, "left", w=1.1, h=1.1)
    window_v4(coll, LC, M, "house_win_l2", x - W / 2 - 0.02, y + 0.85, zb + 1.3, "left", w=1.1, h=1.1)

    # 门廊：正面一条 + 左侧一条（L 形），左前角接码头
    py0, x0, x1 = L["porch"]
    zt = z + 0.32
    n = int((x1 - x0) / 0.5)
    planks = [((x0 + 0.25 + k * (x1 - x0) / n, py0, z + 0.26), ((x1 - x0) / n - 0.03, 1.8, 0.12), (0, 0, 0)) for k in range(n)]
    batch("house_porch_planks", "cube", coll, M["wood_light"], planks)
    porch = shape("house_porch", "cube", coll, M["wood"], loc=((x0 + x1) / 2, py0, z + 0.14), scale=(x1 - x0, 1.8, 0.18))
    WALKABLE.add(porch.name)
    WALKABLE.add("house_porch_planks")
    lx = x0 + 0.95
    ly0, ly1 = py0 + 0.9, y + D / 2 - 0.2
    m = int((ly1 - ly0) / 0.5)
    planks2 = [((lx, ly0 + 0.25 + k * (ly1 - ly0) / m, z + 0.26), (1.9, (ly1 - ly0) / m - 0.03, 0.12), (0, 0, 0)) for k in range(m)]
    batch("house_porch_side_planks", "cube", coll, M["wood_light"], planks2)
    shape("house_porch_side", "cube", coll, M["wood"], loc=(lx, (ly0 + ly1) / 2, z + 0.14), scale=(1.9, ly1 - ly0, 0.18))
    WALKABLE.add("house_porch_side_planks")
    # 门廊下的支柱
    sup = [((px, py0 - 0.85, z + 0.05), (0.12, 0.12, 0.5), (0, 0, 0)) for px in (x0 + 0.1, x0 + 2.2, hx_mid(x0, x1), x1 - 0.1)]
    batch("house_porch_supports", "cube", coll, M["wood_dark"], sup)
    # 栏杆：正面（右端留台阶口）、左侧（前端留码头口）
    fence("house_rail_front", coll, M, (x0 + 0.1, py0 - 0.85), (x1 - 1.45, py0 - 0.85), zt, n=8, h=0.62)
    fence("house_rail_side", coll, M, (x0 + 0.08, py0 + 0.45), (x0 + 0.08, ly1 - 0.05), zt, n=4, h=0.62)
    fence("house_rail_back", coll, M, (x0 + 0.08, ly1 - 0.05), (x0 + 1.85, ly1 - 0.05), zt, n=2, h=0.62)
    # 台阶
    sxs = x1 - 0.75
    for k in range(3):
        stp = shape(f"house_step{k}", "cube", coll, M["wood_light"], loc=(sxs, py0 - 1.08 - k * 0.34, z + 0.2 - k * 0.075),
                    scale=(1.25, 0.36, 0.1))
        WALKABLE.add(stp.name)
    batch("house_step_side", "cube", coll, M["wood_dark"],
          [((sxs + s * 0.66, py0 - 1.4, z + 0.12), (0.1, 1.05, 0.26), (0.18, 0, 0)) for s in (-1, 1)])
    # 门廊吊灯
    hy = y - D / 2 - 0.35
    shape("house_hang_chain", "cyl", coll, M["metal"], loc=(dx - 0.05, hy, zr - 0.25), scale=(0.015, 0.015, 0.4), seg=4)
    shape("house_hang_lamp", "cube", coll, M["lantern"], loc=(dx - 0.05, hy, zr - 0.55), scale=(0.2, 0.2, 0.26))
    shape("house_hang_cap", "cone", coll, M["roof_dark"], loc=(dx - 0.05, hy, zr - 0.36), scale=(0.2, 0.2, 0.12), seg=4,
          rot=(0, 0, math.pi / 4))
    point_light(LC, "house_hang_light", (dx - 0.05, hy - 0.25, zr - 0.65), (1.0, 0.72, 0.42), LANTERN_POWER)
    # 门廊小物：花盆、木箱、睡觉的橘猫、小凳
    for i, (px, py, fl) in enumerate(((x0 + 1.0, py0 + 0.45, "pink"), (x - 1.3, py0 + 0.5, "yellow"),
                                       (x + 0.6, py0 + 0.5, "white"), (x0 + 0.4, py0 - 0.5, "purple"),
                                       (lx - 0.5, ly1 - 0.5, "pink"), (sxs - 1.0, py0 + 0.45, "red"))):
        potted_plant(f"house_pot{i}", coll, M, px, py, zt, fl)
    shape("house_crate", "cube", coll, M["wood"], loc=(lx + 0.3, ly0 + 1.2, zt + 0.22), scale=(0.5, 0.45, 0.44))
    shape("house_crate2", "cube", coll, M["wood_light"], loc=(lx + 0.35, ly0 + 1.2, zt + 0.56), scale=(0.36, 0.32, 0.24),
          rot=(0, 0, 0.3))
    cat("house_cat", coll, M, x0 + 0.85, py0 + 0.2, zt, rz=0.5)
    shape("house_stool", "cyl", coll, M["wood_light"], loc=(x - 2.2, py0 + 0.35, zt + 0.25), scale=(0.22, 0.22, 0.06), seg=10)
    batch("house_stool_legs", "cube", coll, M["wood"],
          [((x - 2.2 + 0.12 * math.cos(a), py0 + 0.35 + 0.12 * math.sin(a), zt + 0.11), (0.04, 0.04, 0.22), (0, 0, 0))
           for a in (0.3, 2.4, 4.4)])
    return zt


def hx_mid(a, b):
    return (a + b) / 2


def plank_walk(prefix, coll, LC, M, a, b, z, width=1.7, lamp=True):
    """木栈道（码头）：从 a 到 b，木板垂直于走向，下面有立柱，末端有灯笼"""
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    ln = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(3, int(ln / 0.42))
    planks = []
    for k in range(n):
        t = (k + 0.5) / n
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        planks.append(((px, py, z), (ln / n - 0.03, width, 0.1), (0, 0, ang + random.uniform(-0.015, 0.015))))
    batch(prefix + "_planks", "cube", coll, M["wood_light"], planks)
    WALKABLE.add(prefix + "_planks")
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    shape(prefix + "_frame", "cube", coll, M["wood"], loc=(mx, my, z - 0.1), scale=(ln, width, 0.1), rot=(0, 0, ang))
    px_, py_ = -math.sin(ang), math.cos(ang)
    posts = []
    for i in range(int(ln / 1.1) + 1):
        t = i / max(int(ln / 1.1), 1)
        cx_, cy_ = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        for s in (-1, 1):
            posts.append(((cx_ + px_ * s * width * 0.48, cy_ + py_ * s * width * 0.48, z / 2 - 0.1), (0.09, 0.09, z + 0.5), (0, 0, 0)))
    batch(prefix + "_posts", "cyl", coll, M["wood_dark"], posts, seg=7)
    shape(prefix + "_rope", "cyl", coll, M["rope"], loc=(b[0] - math.cos(ang) * 0.5 + px_ * 0.5, b[1] - math.sin(ang) * 0.5 + py_ * 0.5, z + 0.1),
          scale=(0.2, 0.2, 0.1), seg=10)
    if lamp:
        lantern(prefix + "_lamp", coll, LC, M, b[0] - math.cos(ang) * 0.3 - px_ * 0.7, b[1] - math.sin(ang) * 0.3 - py_ * 0.7, z + 0.05)
    return ang


def rowboat(coll, M, bx, by, br):
    shape("boat_hull", "sphere", coll, M["boat"], loc=(bx, by, 0.1), scale=(1.55, 0.58, 0.32), rot=(0, 0, br))
    shape("boat_rim", "sphere", coll, M["wood_dark"], loc=(bx, by, 0.2), scale=(1.5, 0.55, 0.12), rot=(0, 0, br))
    shape("boat_inner", "sphere", coll, M["wood"], loc=(bx, by, 0.21), scale=(1.32, 0.44, 0.1), rot=(0, 0, br))
    shape("boat_stripe", "sphere", coll, M["roof"], loc=(bx, by, 0.14), scale=(1.57, 0.6, 0.06), rot=(0, 0, br))
    batch("boat_seats", "cube", coll, M["wood_light"],
          [((bx + k * math.cos(br) * 0.5, by + k * math.sin(br) * 0.5, 0.3), (0.18, 0.86, 0.05), (0, 0, br)) for k in (-1, 1)])
    shape("boat_oar", "cube", coll, M["wood_light"], loc=(bx + 0.2, by + 0.25, 0.34), scale=(1.4, 0.06, 0.04), rot=(0, 0.1, br + 0.3))
    shape("boat_ripple", "cyl", coll, M["foam"], loc=(bx, by, 0.02), scale=(1.9, 0.85, 0.01), rot=(0, 0, br), seg=20)


def build_stream_v4(coll_bg, coll_fg, M, z, pts):
    ex, ey = pts[-1]
    ribbon("stream_bed", pts, 1.9, z + 0.01, coll_bg, M["dirt"], steps=10, wobble=0.1)
    ob, curve, normals = ribbon("stream", pts, 1.5, z + 0.03, coll_bg, M["stream"], steps=10)
    ribbon("stream_highlight", pts[1:-1], 0.25, z + 0.04, coll_bg, M["foam"], steps=10, wobble=0.6)
    rocks, mossy = [], []
    for i in range(0, len(curve) - 2, 2):
        x, y = curve[i]
        nx, ny = normals[i]
        for side in (-1, 1):
            s = random.uniform(0.2, 0.5)
            item = ((x + nx * side * (0.95 + random.uniform(-0.1, 0.15)), y + ny * side * (0.95 + random.uniform(-0.1, 0.15)),
                     z + s * 0.35), (s, s * 0.9, s * 0.65), (0, 0, random.uniform(0, 3)))
            (mossy if random.random() < 0.3 else rocks).append(item)
    batch("stream_rocks", "ico", coll_bg, M["rock"], rocks[::2], sub=1, jitter=0.12)
    batch("stream_rocks_b", "ico", coll_bg, M["rock_dark"], rocks[1::2], sub=1, jitter=0.12)
    batch("stream_rocks_moss", "ico", coll_bg, M["moss"], mossy, sub=1, jitter=0.12)
    ux, uy = ex / math.hypot(ex, ey), ey / math.hypot(ex, ey)
    px, py = -uy, ux
    w = 0.8
    tiers = [(0.0, z + 0.03, 0.3, z * 0.55), (0.3, z * 0.55, 0.7, 0.02)]
    for k, (d0, z0, d1, z1) in enumerate(tiers):
        v = [(ex + ux * d0 + px * w, ey + uy * d0 + py * w, z0), (ex + ux * d0 - px * w, ey + uy * d0 - py * w, z0),
             (ex + ux * d1 - px * w, ey + uy * d1 - py * w, z1), (ex + ux * d1 + px * w, ey + uy * d1 + py * w, z1)]
        from_pydata(f"waterfall{k}", v, [(0, 1, 2, 3)], coll_fg, M["stream"])
        stripes = []
        for j in range(6):
            t = (j + 0.5) / 6 * 2 - 1
            sx_, sy_ = px * w * t * 0.9, py * w * t * 0.9
            mid = ((ex + ux * (d0 + d1) / 2 + sx_), (ey + uy * (d0 + d1) / 2 + sy_), (z0 + z1) / 2 + 0.02)
            stripes.append((mid, (0.05, 0.05, math.hypot(d1 - d0, z0 - z1) * 0.45), (0, 0, 0)))
        batch(f"waterfall_stripes{k}", "cube", coll_fg, M["foam"], stripes)
    mist = [((ex + ux * random.uniform(0.7, 1.5) + px * random.uniform(-1.0, 1.0),
              ey + uy * random.uniform(0.7, 1.5) + py * random.uniform(-1.0, 1.0), random.uniform(0.02, 0.25)),
             (random.uniform(0.2, 0.42),) * 2 + (0.15,), (0, 0, 0)) for _ in range(12)]
    batch("waterfall_mist", "ico", coll_fg, M["foam"], mist, sub=1, jitter=0.1)
    big = [((ex + px * 1.35 * side + ux * 0.2, ey + py * 1.35 * side + uy * 0.2, z * 0.4), (0.9, 0.85, 0.8), (0, 0, side))
           for side in (-1, 1)]
    big += [((ex + px * 2.2 * side + ux * 0.6, ey + py * 2.2 * side + uy * 0.6, 0.1), (0.6, 0.55, 0.5), (0, 0, side)) for side in (-1, 1)]
    batch("waterfall_rocks", "ico", coll_fg, M["rock_dark"], big, sub=1, jitter=0.15)
    batch("waterfall_rocks_moss", "ico", coll_fg, M["moss"],
          [((ex + px * 1.35 * side + ux * 0.1, ey + py * 1.35 * side + uy * 0.1, z * 0.4 + 0.55), (0.55, 0.5, 0.25), (0, 0, side))
           for side in (-1, 1)], sub=1, jitter=0.1)
    return curve


def build_picnic(coll, LC, M, x, y, z, ang):
    """樱花树下的野餐桌：桌子 + 两条长凳 + 桌上提灯、书、杯子、花瓶"""
    ca, sa = math.cos(ang), math.sin(ang)

    def P(u, v):
        return (x + u * ca - v * sa, y + u * sa + v * ca)

    shape("picnic_top", "cube", coll, M["wood_light"], loc=(*P(0, 0), z + 0.78), scale=(2.1, 0.95, 0.08), rot=(0, 0, ang))
    batch("picnic_grooves", "cube", coll, M["wood_dark"],
          [((*P(0, v), z + 0.825), (2.08, 0.02, 0.01), (0, 0, ang)) for v in (-0.24, 0.0, 0.24)])
    batch("picnic_legs", "cube", coll, M["wood"],
          [((*P(u, v), z + 0.37), (0.1, 0.1, 0.74), (0, 0, ang)) for u in (-0.85, 0.85) for v in (-0.36, 0.36)])
    for k, v in enumerate((-0.85, 0.85)):
        shape(f"picnic_bench{k}", "cube", coll, M["wood_light"], loc=(*P(0, v), z + 0.45), scale=(2.0, 0.34, 0.07), rot=(0, 0, ang))
        batch(f"picnic_bench{k}_legs", "cube", coll, M["wood"],
              [((*P(u, v), z + 0.21), (0.09, 0.3, 0.42), (0, 0, ang)) for u in (-0.8, 0.8)])
    # 桌上提灯
    lx, ly = P(0.55, 0.1)
    zt = z + 0.82
    shape("picnic_lamp_base", "cube", coll, M["wood_dark"], loc=(lx, ly, zt + 0.02), scale=(0.24, 0.24, 0.04), rot=(0, 0, ang))
    shape("picnic_lamp_glass", "cube", coll, M["lantern"], loc=(lx, ly, zt + 0.17), scale=(0.17, 0.17, 0.24), rot=(0, 0, ang))
    batch("picnic_lamp_frame", "cube", coll, M["wood_dark"],
          [((lx + 0.09 * math.cos(ang + a), ly + 0.09 * math.sin(ang + a), zt + 0.17), (0.025, 0.025, 0.26), (0, 0, ang))
           for a in (0.785, 2.356, 3.927, 5.498)])
    shape("picnic_lamp_cap", "cone", coll, M["roof_dark"], loc=(lx, ly, zt + 0.35), scale=(0.17, 0.17, 0.12), seg=4,
          rot=(0, 0, ang + math.pi / 4))
    shape("picnic_lamp_ring", "cyl", coll, M["metal"], loc=(lx, ly, zt + 0.45), scale=(0.04, 0.04, 0.01), seg=8, rot=(math.pi / 2, 0, ang))
    point_light(LC, "picnic_lamp_light", (lx, ly, zt + 0.25), (1.0, 0.74, 0.44), {"morning": 2.0, "noon": 0.0, "night": 90.0}, radius=0.1)
    # 书、杯子、花瓶
    bx, by = P(-0.45, -0.05)
    for k, mat in enumerate(("book_red", "book_blue", "book_green")):
        shape(f"picnic_book{k}", "cube", coll, M[mat], loc=(bx, by, zt + 0.03 + k * 0.06), scale=(0.34 - k * 0.03, 0.25, 0.055),
              rot=(0, 0, ang + k * 0.2))
    ox, oy = P(-0.05, -0.2)
    shape("picnic_open_book", "cube", coll, M["white"], loc=(ox, oy, zt + 0.015), scale=(0.42, 0.28, 0.02), rot=(0, 0, ang - 0.15))
    mx, my = P(0.2, 0.25)
    shape("picnic_mug", "cyl", coll, M["mug"], loc=(mx, my, zt + 0.07), scale=(0.06, 0.06, 0.13), seg=10)
    vx, vy = P(-0.75, 0.25)
    shape("picnic_vase", "cyl", coll, M["mug"], loc=(vx, vy, zt + 0.09), scale=(0.06, 0.06, 0.18), seg=10, top=0.7)
    batch("picnic_vase_fl", "ico", coll, M["pink"],
          [((vx + random.uniform(-0.07, 0.07), vy + random.uniform(-0.07, 0.07), zt + 0.25 + random.uniform(0, 0.08)),
            (0.045, 0.045, 0.045), (0, 0, 0)) for _ in range(6)])
    WALKABLE.add("picnic_top")


def birdhouse(coll, M, x, y, z):
    shape("birdhouse_post", "cube", coll, M["wood"], loc=(x, y, z + 0.85), scale=(0.08, 0.08, 1.7))
    shape("birdhouse", "cube", coll, M["wood_light"], loc=(x, y, z + 1.8), scale=(0.36, 0.36, 0.4))
    shape("birdhouse_roof", "cone", coll, M["roof"], loc=(x, y, z + 2.1), scale=(0.33, 0.33, 0.22), seg=4, rot=(0, 0, math.pi / 4))
    shape("birdhouse_hole", "cyl", coll, M["black"], loc=(x, y - 0.19, z + 1.85), scale=(0.07, 0.07, 0.02), rot=(math.pi / 2, 0, 0), seg=8)
    shape("birdhouse_perch", "cyl", coll, M["wood_dark"], loc=(x, y - 0.25, z + 1.72), scale=(0.015, 0.015, 0.12),
          rot=(math.pi / 2, 0, 0), seg=5)


def _loop_keys(ob, path, fn, step=4, loop=192):
    """在第 1–193 帧按周期函数打关键帧（首尾相同，8 秒无缝循环）"""
    for f in range(1, loop + 2, step):
        t = (f - 1) / loop
        setattr(ob, path, fn(t))
        ob.keyframe_insert(path, frame=f)


def campfire(coll, LC, M, x, y, z):
    """篝火：石头围的火塘 + 交叉木柴 + 跳动的火苗 + 火星 + 原木凳 + 三脚架吊锅"""
    f_, r_, _ = _cam_basis()
    fg = Vector((f_.x, f_.y, 0)).normalized()
    rocks = []
    for k in range(12):
        a = 2 * math.pi * k / 12 + random.uniform(-0.08, 0.08)
        s = random.uniform(0.15, 0.21)
        rocks.append(((x + 0.62 * math.cos(a), y + 0.62 * math.sin(a), z + s * 0.45), (s * 1.25, s, s * 0.8), (0, 0, a)))
    batch("campfire_rocks", "ico", coll, M["rock"], rocks[::2], sub=1, jitter=0.12)
    batch("campfire_rocks_b", "ico", coll, M["rock_dark"], rocks[1::2], sub=1, jitter=0.12)
    shape("campfire_ash", "cyl", coll, M["rock_dark"], loc=(x, y, z + 0.03), scale=(0.52, 0.52, 0.04), seg=14)
    logs = [((x, y, z + 0.11 + 0.05 * (k % 2)), (0.07, 0.07, 0.8), (math.pi / 2, 0, k * math.pi / 4 + 0.3)) for k in range(4)]
    batch("campfire_logs", "cyl", coll, M["wood_dark"], logs, seg=7)
    # 火苗：以篝火中心为原点建模，方便按中心缩放做跳动
    outer = [((0, 0, 0.52), (0.33, 0.33, 0.95), (0, 0, 0)), ((0.16, 0.07, 0.4), (0.19, 0.19, 0.66), (0.15, -0.2, 0)),
             ((-0.15, 0.1, 0.38), (0.18, 0.18, 0.6), (0.1, 0.25, 0)), ((0.03, -0.16, 0.37), (0.18, 0.18, 0.58), (-0.25, 0, 0))]
    inner = [((0, 0, 0.44), (0.19, 0.19, 0.66), (0, 0, 0)), ((0.07, 0.05, 0.34), (0.1, 0.1, 0.42), (0.1, -0.1, 0))]
    fo = batch("campfire_flame_outer", "cone", coll, M["fire_outer"], outer, seg=8, jitter=0.06)
    fi = batch("campfire_flame_inner", "cone", coll, M["fire_inner"], inner, seg=8, jitter=0.05)
    sparks = [((random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), random.uniform(0.8, 1.9)), (0.025, 0.025, 0.025), (0, 0, 0))
              for _ in range(14)]
    sp = batch("campfire_sparks", "ico", coll, M["ember"], sparks, sub=1)
    for ob in (fo, fi, sp):
        ob.location = (x, y, z)
        only_at(ob, "night")
    _loop_keys(fo, "scale", lambda t: (1 - 0.06 * math.sin(2 * math.pi * 6 * t), 1 - 0.06 * math.sin(2 * math.pi * 6 * t),
                                       1 + 0.14 * math.sin(2 * math.pi * 6 * t) + 0.07 * math.sin(2 * math.pi * 11 * t + 1)))
    _loop_keys(fi, "scale", lambda t: (1.0, 1.0, 1 + 0.18 * math.sin(2 * math.pi * 8 * t + 2) + 0.06 * math.sin(2 * math.pi * 13 * t)))
    _loop_keys(sp, "location", lambda t: (x + 0.08 * math.sin(2 * math.pi * 2 * t), y + 0.08 * math.cos(2 * math.pi * 3 * t),
                                          z + 0.12 * math.sin(2 * math.pi * 4 * t)))
    lt = point_light(LC, "campfire_light", (x, y, z + 0.65), (1.0, 0.56, 0.24), {"morning": 0.0, "noon": 0.0, "night": 480.0}, radius=0.3)
    _loop_keys(lt.data, "energy", lambda t: 480.0 * (1 + 0.12 * math.sin(2 * math.pi * 7 * t) + 0.06 * math.sin(2 * math.pi * 17 * t + 1)))
    # 原木凳（火的后方和右侧，左前方是野餐桌）
    for k, d in enumerate((fg, Vector((r_.x, r_.y, 0)).normalized(), (fg - Vector((r_.x, r_.y, 0))).normalized())):
        sx_, sy_ = x + d.x * 1.55, y + d.y * 1.55
        ang = math.atan2(d.y, d.x)
        shape(f"campfire_seat{k}", "cyl", coll, M["trunk"], loc=(sx_, sy_, z + 0.2), scale=(0.2, 0.2, 1.25),
              rot=(math.pi / 2, 0, ang), seg=10, jitter=0.01)
        ax_, ay_ = -math.sin(ang), math.cos(ang)
        batch(f"campfire_seat{k}_ends", "cyl", coll, M["wood_light"],
              [((sx_ + e * 0.63 * ax_, sy_ + e * 0.63 * ay_, z + 0.2), (0.18, 0.18, 0.02), (math.pi / 2, 0, ang)) for e in (-1, 1)],
              seg=10)
    # 三脚架 + 吊锅
    legs = []
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.4
        bx_, by_ = x + 0.55 * math.cos(a), y + 0.55 * math.sin(a)
        d = Vector((x - bx_, y - by_, 1.25))
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_euler()
        legs.append((((bx_ + x) / 2, (by_ + y) / 2, z + 0.62), (0.025, 0.025, d.length), tuple(rot)))
    batch("campfire_tripod", "cyl", coll, M["wood_dark"], legs, seg=5)
    shape("campfire_chain", "cyl", coll, M["metal"], loc=(x, y, z + 1.08), scale=(0.01, 0.01, 0.3), seg=4)
    shape("campfire_pot", "sphere", coll, M["metal"], loc=(x, y, z + 0.86), scale=(0.17, 0.17, 0.14), seg=12)
    shape("campfire_pot_rim", "cyl", coll, M["black"], loc=(x, y, z + 0.97), scale=(0.15, 0.15, 0.02), seg=12)
    # 火塘周围踩出来的土
    shape("campfire_ground", "cyl", coll, M["path_edge"], loc=(x, y, z + 0.012), scale=(1.15, 1.15, 0.01), seg=20)


def planter(prefix, coll, M, x, y, z, Lg=2.2, Wd=0.7, ang=0.0, colors=("pink", "white", "purple", "yellow", "red")):
    """抬高的木花箱，种满花"""
    ca, sa = math.cos(ang), math.sin(ang)
    shape(prefix + "_box", "cube", coll, M["wood"], loc=(x, y, z + 0.22), scale=(Lg, Wd, 0.44), rot=(0, 0, ang))
    corners = [((x + u * ca - v * sa, y + u * sa + v * ca, z + 0.24), (0.1, 0.1, 0.5), (0, 0, ang))
               for u in (-Lg / 2, Lg / 2) for v in (-Wd / 2, Wd / 2)]
    batch(prefix + "_corners", "cube", coll, M["wood_dark"], corners)
    heads = {c: [] for c in colors}
    leaves = []
    nf = int(Lg * Wd * 45)
    for i in range(nf):
        u, v = random.uniform(-Lg / 2 + 0.08, Lg / 2 - 0.08), random.uniform(-Wd / 2 + 0.06, Wd / 2 - 0.06)
        px, py = x + u * ca - v * sa, y + u * sa + v * ca
        s = random.uniform(0.07, 0.11)
        heads[colors[i % len(colors)]].append(((px, py, z + 0.55 + random.uniform(0, 0.15)), (s, s, s * 0.75), (0, 0, 0)))
    for i in range(int(Lg * 5)):
        u = random.uniform(-Lg / 2 + 0.1, Lg / 2 - 0.1)
        px, py = x + u * ca, y + u * sa
        leaves.append(((px, py, z + 0.5), (0.25, 0.22, 0.14), (0, 0, 0)))
    batch(prefix + "_leaves", "ico", coll, M["leaf2"], leaves, sub=1, jitter=0.1)
    for c, items in heads.items():
        batch(f"{prefix}_{c}", "ico", coll, M[c], items, sub=1)


def far_strip(prefix, coll, M, fx, fy, rx, ry, ang, houses=0, seed=0):
    """海平线上的对岸：一条长岛 + 深色树林 + 亮灯的小房子"""
    rnd = random.Random(seed)
    cx, cy = S(fx, fy, 0.0)
    top, side, _ = blob_island(prefix + "_top", prefix + "_side", 0.0, 0.0, rx, ry, 0.18, -0.3, coll, M["far_island"], M["far_tree"],
                               n=40, radius_fn=lambda t: 1.0 + 0.08 * math.sin(3 * t + seed) + 0.05 * math.sin(7 * t + seed * 2))
    for ob in (top, side):
        ob.location = (cx, cy, 0)
        ob.rotation_euler = (0, 0, ang)
    ca, sa = math.cos(ang), math.sin(ang)

    def P(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)

    for k in range(9):
        u, v = rnd.uniform(-rx * 0.85, rx * 0.85), rnd.uniform(-ry * 0.1, ry * 0.6)
        px, py = P(u, v)
        tree(f"{prefix}_tree{k}", coll, M, px, py, 0.18, h=rnd.uniform(0.7, 1.15), r=rnd.uniform(0.28, 0.42),
             kind="pine" if k % 3 == 0 else "round", leaf=("far_tree", "far_island", "far_tree"))
    for k in range(houses):
        u = -rx * 0.5 + k * rx * 0.9 / max(houses - 1, 1) + rnd.uniform(-0.2, 0.2)
        px, py = P(u, -ry * 0.35)
        hn = f"{prefix}_house{k}"
        shape(hn, "cube", coll, M["wall"], loc=(px, py, 0.33), scale=(0.34, 0.28, 0.3), rot=(0, 0, ang))
        shape(hn + "_roof", "cone", coll, M["roof_dark"], loc=(px, py, 0.56), scale=(0.29, 0.24, 0.2), seg=4, rot=(0, 0, ang + math.pi / 4))
        wx, wy = px - sa * -0.15, py + ca * -0.15
        shape(hn + "_win", "cube", coll, M["far_window"], loc=(wx, wy, 0.34), scale=(0.11, 0.02, 0.1), rot=(0, 0, ang))
        point_light(bpy.data.collections["LIGHTS_灯光"], hn + "_light", (wx - sa * -0.15, wy + ca * -0.15, 0.36),
                    (1.0, 0.72, 0.42), {"morning": 0.0, "noon": 0.0, "night": 6.0}, radius=0.05)


def glints(name, coll, mat, center_fx, fy0, fy1, n, spread0, spread1, lmin, lmax, avoid_island=True):
    """水面上的碎光：一束沿画面竖直方向的横向短条（月光 / 灯光倒影）"""
    ang = screen_angle()
    items = []
    tries = 0
    while len(items) < n and tries < n * 20:
        tries += 1
        t = random.random() ** 0.8
        fy = fy0 + (fy1 - fy0) * t
        spread = spread0 + (spread1 - spread0) * t
        fx = center_fx + random.gauss(0, spread)
        x, y = S(fx, fy, 0.0)
        if avoid_island and inside_island(x, y, 1.1):
            continue
        Lg = random.uniform(lmin, lmax) * (1.0 - 0.5 * abs(fx - center_fx) / max(spread * 3, 1e-3))
        items.append(((x, y, 0.025), (max(Lg, 0.08), 0.05, 0.01), (0, 0, ang)))
    return only_at(batch(name, "cube", coll, mat, items), "night")


def water_pts(region, n, margin=1.1):
    fx0, fx1, fy0, fy1 = region
    pts, tries = [], 0
    while len(pts) < n and tries < n * 40:
        tries += 1
        x, y = S(random.uniform(fx0, fx1), random.uniform(fy0, fy1), 0.0)
        if inside_island(x, y, margin):
            continue
        pts.append((x, y))
    return pts


# ============================================================
# 搭建整个场景（v4 布局）
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
    init_lines()
    build_instances(M)
    ang_s = screen_angle()

    # ---------- 海面：到海平线为止，上面露出夜空 ----------
    corners = [S(-0.8, HORIZON_FY, 0.0), S(1.8, HORIZON_FY, 0.0), S(1.8, 2.0, 0.0), S(-0.8, 2.0, 0.0)]
    from_pydata("sea", [(x_, y_, 0.0) for x_, y_ in corners], [(0, 1, 2, 3)], WATER, M["sea"])
    ring = [island_edge(2 * math.pi * i / 120) for i in range(120)]
    ring_band("shore_foam", ring, 1.0, 1.06, 0.016, WATER, M["foam"])
    ring_band("shore_foam_outer", ring, 1.11, 1.13, 0.016, WATER, M["foam"])
    # 白天的水面闪点（夜里换成月光碎光）
    day = []
    for _ in range(80):
        x_, y_ = S(random.uniform(0.0, 1.0), random.uniform(HORIZON_FY + 0.03, 1.0), 0.0)
        if inside_island(x_, y_, 1.2):
            continue
        Lg = random.uniform(0.15, 0.45)
        day.append(((x_, y_, 0.02), (Lg, Lg * 0.18, 0.01), (0, 0, ang_s)))
    only_at(batch("sea_sparkles", "cube", FX, M["sparkle"], day), "morning,noon")
    # 夜：月光一束 + 灯光倒影
    glints("glint_moon", FX, M["glint_moon"], 0.17, HORIZON_FY + 0.01, 0.42, 110, 0.012, 0.05, 0.25, 0.95)
    glints("glint_far", FX, M["glint_warm"], 0.32, 0.092, 0.15, 40, 0.06, 0.07, 0.08, 0.35)
    glints("glint_dock", FX, M["glint_warm"], 0.07, 0.56, 0.78, 35, 0.025, 0.035, 0.15, 0.5)
    glints("glint_falls", FX, M["glint_warm"], 0.93, 0.82, 0.98, 30, 0.03, 0.04, 0.12, 0.45)
    glints("glint_south", FX, M["glint_warm"], 0.22, 0.93, 1.02, 18, 0.025, 0.03, 0.12, 0.35)
    # 睡莲（左下、右下、左侧）
    lilies, lily_fl = [], []
    for region, n in (((0.0, 0.16, 0.70, 1.02), 26), ((0.86, 1.0, 0.86, 1.02), 14), ((0.0, 0.08, 0.40, 0.55), 6),
                      ((0.20, 0.30, 0.96, 1.02), 6)):
        for x_, y_ in water_pts(region, n):
            s = random.uniform(0.22, 0.38)
            lilies.append(((x_, y_, 0.02), (s, s, 0.015), (0, 0, random.uniform(0, 3))))
            if random.random() < 0.25:
                lily_fl.append(((x_, y_, 0.08), (0.08, 0.08, 0.06), (0, 0, 0)))
    batch("lilies", "cyl", WATER, M["lily"], lilies, seg=9)
    batch("lily_flowers", "ico", WATER, M["pink"], lily_fl, sub=1)

    # ---------- 主岛 ----------
    top, side, _ = blob_island("island_top", "island_cliff", 0, 0, ISLAND_RX, ISLAND_RY, z, -1.0,
                               ISL, M["grass"], M["cliff"], n=120, radius_fn=island_radius)
    bpy.data.objects.remove(top, do_unlink=True)
    top = build_terrain(ISL, M["grass"])
    WALKABLE.add(top.name)
    add_scatter(top, "grass_scatter", INST["grass"], GRASS_COUNT, 1.0, 0.45, vgroup="grass", seed=3)
    add_scatter(top, "flower_scatter", INST["flowers"], FLOWER_COUNT, 1.0, 0.35, vgroup="flowers", seed=5)
    shore_a, shore_b, shore_m = [], [], []
    for i in range(160):
        a = 2 * math.pi * i / 160 + random.uniform(-0.01, 0.01)
        x_, y_ = island_edge(a, random.uniform(1.0, 1.05))
        if random.random() < 0.9:
            s = random.uniform(0.35, 0.9)
            item = ((x_, y_, random.uniform(-0.05, 0.25)), (s, s * random.uniform(0.8, 1.2), s * 0.7), (0, 0, random.uniform(0, 3)))
            r_ = random.random()
            (shore_m if r_ < 0.2 else (shore_a if r_ < 0.6 else shore_b)).append(item)
    batch("shore_rocks_a", "ico", ISL, M["rock"], shore_a, sub=2, jitter=0.1)
    batch("shore_rocks_b", "ico", ISL, M["rock_dark"], shore_b, sub=2, jitter=0.1)
    batch("shore_rocks_moss", "ico", ISL, M["rock"], shore_m, sub=2, jitter=0.1)
    batch("shore_moss_caps", "ico", ISL, M["moss"],
          [((p[0][0], p[0][1], p[0][2] + p[1][2] * 0.55), (p[1][0] * 0.7, p[1][1] * 0.7, p[1][2] * 0.35), p[2]) for p in shore_m],
          sub=1, jitter=0.05)
    # 芦苇、香蒲（岸边）
    for i, (fx, fy) in enumerate(((0.20, 0.80), (0.175, 0.88), (0.625, 0.985), (0.68, 0.955), (0.74, 0.905), (0.12, 0.70),
                                  (0.30, 1.02), (0.96, 0.66))):
        x_, y_ = S(fx, fy, 0.2)
        th = math.atan2(y_ / ISLAND_RY, x_ / ISLAND_RX)
        ex_, ey_ = island_edge(th, 1.04)
        reeds(f"reeds{i}", PLANTS, M, ex_, ey_, n=11, base_z=0.05)

    # ---------- 木屋、码头、小船 ----------
    hx, hy = L["house"]
    zt = build_house_v4(PROPS, LC, M, hx, hy, z)
    py0, x0, x1 = L["porch"]
    dock_a = (x0 + 0.1, py0 - 0.2)
    dock_dir = S(-0.06, 0.60, 0.4)
    d = math.hypot(dock_dir[0] - dock_a[0], dock_dir[1] - dock_a[1])
    dock_b = (dock_a[0] + (dock_dir[0] - dock_a[0]) / d * 4.6, dock_a[1] + (dock_dir[1] - dock_a[1]) / d * 4.6)
    dang = plank_walk("dock", PROPS, LC, M, dock_a, dock_b, zt - 0.02, width=1.7)
    bx, by = S(0.06, 0.735, 0.0)
    rowboat(PROPS, M, bx, by, dang + 0.12)

    # ---------- 石板路（带路边石子）----------
    pebbles = []
    for name, (pts, w) in PATHS.items():
        ribbon(name + "_edge", pts, w + 0.3, z + 0.015, PROPS, M["path_edge"])
        ob, curve, normals = ribbon(name, pts, w, z + 0.03, PROPS, M["cobble"], wobble=0.08)
        WALKABLE.add(ob.name)
        WALKABLE.add(name + "_edge")
        for i in range(0, len(curve), 2):
            x_, y_ = curve[i]
            nx, ny = normals[i]
            for sd in (-1, 1):
                if random.random() < 0.6:
                    dd = (w / 2 + 0.15) * sd
                    s = random.uniform(0.08, 0.16)
                    pebbles.append(((x_ + nx * dd, y_ + ny * dd, z + 0.05), (s, s, s * 0.6), (0, 0, 0)))
    batch("path_pebbles", "ico", PROPS, M["rock_warm"], pebbles, sub=1, jitter=0.1)
    # 往桥去的路上有几级石阶
    a_, b_ = L["bridge"]
    batch("bridge_steps", "cube", PROPS, M["stone"],
          [((a_[0] - (b_[0] - a_[0]) * 0.25 * k, a_[1] - (b_[1] - a_[1]) * 0.25 * k, z + 0.06 + 0.05 * (3 - k)),
            (0.45, 1.3, 0.1), (0, 0, math.atan2(b_[1] - a_[1], b_[0] - a_[0]))) for k in range(1, 4)], jitter=0.01)

    # ---------- 小溪、拱桥、瀑布 ----------
    build_stream_v4(PROPS, FG, M, z, L["stream"])
    build_bridge(PROPS, LC, M, a_, b_, z)

    # ---------- 樱花 + 野餐桌 + 鸟屋 ----------
    cx_, cy_ = S(0.53, 0.80)
    campfire(FG, LC, M, cx_, cy_, z)
    px_, py_ = S(0.455, 0.865)
    build_picnic(FG, LC, M, px_, py_, z, ang_s)
    bhx, bhy = S(0.605, 0.905)
    birdhouse(FG, M, bhx, bhy, z)
    for i, (fx, fy) in enumerate(((0.585, 0.86), (0.40, 0.90))):
        sx_, sy_ = S(fx, fy)
        shape(f"stump{i}", "cyl", PROPS, M["trunk"], loc=(sx_, sy_, z + 0.22), scale=(0.28, 0.28, 0.44), seg=9, jitter=0.02)
        shape(f"stump{i}_top", "cyl", PROPS, M["wood_light"], loc=(sx_, sy_, z + 0.45), scale=(0.25, 0.25, 0.02), seg=9)

    # ---------- 门廊前的花箱、花坛 ----------
    planter("planter1", PROPS, M, hx - 0.9, py0 - 1.55, z, Lg=2.6, Wd=0.75)
    planter("planter2", PROPS, M, x0 + 1.2, py0 - 1.6, z, Lg=2.0, Wd=0.75, colors=("white", "yellow", "pink", "blue"))
    planter("planter3", PROPS, M, *S(0.205, 0.70), z, Lg=2.2, Wd=0.9, ang=0.25, colors=("purple", "white", "pink", "yellow"))

    # ---------- 灯笼（沿路）----------
    for i, (fx, fy) in enumerate(((0.415, 0.27), (0.47, 0.47), (0.325, 0.60), (0.315, 0.79), (0.40, 0.975),
                                  (0.625, 0.585), (0.775, 0.72), (0.925, 0.555), (0.53, 0.40), (0.69, 0.47))):
        lx_, ly_ = S(fx, fy)
        lantern(f"lamp{i}", PROPS, LC, M, lx_, ly_, terrain_h(lx_, ly_) - 0.02)

    # ---------- 栅栏 ----------
    for i, (a, b, n) in enumerate((((0.455, 0.30), (0.51, 0.37), 3), ((0.51, 0.37), (0.525, 0.46), 3),
                                   ((0.37, 0.31), (0.40, 0.40), 3), ((0.265, 0.885), (0.33, 0.965), 3),
                                   ((0.33, 0.965), (0.40, 1.02), 3), ((0.69, 0.67), (0.765, 0.69), 3),
                                   ((0.905, 0.635), (0.975, 0.655), 3), ((0.50, 0.65), (0.62, 0.66), 4))):
        A, B = S(*a), S(*b)
        coll = FG if a[1] > 0.85 else PROPS
        fence(f"fence{i}", coll, M, A, B, terrain_h((A[0] + B[0]) / 2, (A[1] + B[1]) / 2) - 0.02, n=n)

    # ---------- 树 ----------
    for i, (fx, fy, k, h, r) in enumerate((
            (0.52, 0.41, "round", 3.4, 1.45), (0.48, 0.32, "round", 3.6, 1.5), (0.375, 0.28, "round", 3.3, 1.35),
            (0.66, 0.40, "round", 3.5, 1.5), (0.75, 0.42, "round", 3.7, 1.55), (0.84, 0.44, "round", 3.4, 1.45),
            (0.93, 0.50, "round", 3.5, 1.5), (0.975, 0.61, "round", 3.1, 1.3))):
        tx, ty = S(fx, fy)
        tree(f"tree{i}", PLANTS, M, tx, ty, z, h=h, r=r, kind=k)

    # ---------- 灌木、花丛 ----------
    for i, (fx, fy, fl) in enumerate(((0.14, 0.58, "white"), (0.395, 0.43, None), (0.545, 0.48, "pink"), (0.62, 0.53, None),
                                      (0.71, 0.555, "purple"), (0.80, 0.86, "white"), (0.27, 0.93, "yellow"),
                                      (0.56, 0.95, None), (0.885, 0.70, "pink"), (0.36, 0.33, "white"))):
        bx_, by_ = S(fx, fy)
        bush(f"bush{i}", PLANTS, M, bx_, by_, z, r=random.uniform(0.45, 0.7), flowers=fl)
    for i, (fx, fy) in enumerate(((0.13, 0.63), (0.17, 0.74), (0.25, 0.76), (0.29, 0.69), (0.335, 0.50), (0.37, 0.46),
                                  (0.49, 0.44), (0.51, 0.53), (0.30, 0.88), (0.24, 0.84), (0.44, 0.985), (0.55, 0.99),
                                  (0.63, 0.80), (0.67, 0.89), (0.72, 0.80), (0.58, 0.70), (0.665, 0.71), (0.78, 0.56),
                                  (0.72, 0.51), (0.95, 0.71), (0.47, 0.71), (0.83, 0.79), (0.255, 0.62), (0.60, 0.43))):
        fx_, fy_ = S(fx, fy)
        flower_patch(f"flower{i}", PLANTS, M, fx_, fy_, z, spread=0.8, n=18,
                     colors=random.choice((("pink", "white", "purple", "yellow"), ("red", "white", "yellow", "orange"),
                                           ("purple", "blue", "white", "pink"))))
    add_bevels(PROPS)
    add_bevels(FG)

    # ---------- 对岸、月亮、星星 ----------
    for i, (fx, fy, rx, ry, houses) in enumerate(((0.05, 0.088, 3.0, 0.45, 0), (0.26, 0.086, 3.4, 0.5, 3),
                                                  (0.45, 0.084, 3.0, 0.45, 2), (0.68, 0.082, 3.4, 0.5, 1),
                                                  (0.92, 0.081, 3.6, 0.45, 0))):
        far_strip(f"far{i}", FAR, M, fx, fy, rx, ry, ang_s, houses=houses, seed=i + 1)
    mx_, my_ = S(0.17, 0.035, 0.0)
    moon = shape("moon", "sphere", FAR, M["moon"], loc=(mx_, my_, 0.0), scale=(0.42, 0.42, 0.42), seg=24)
    only_at(moon, "night")
    stars = []
    for _ in range(70):
        fx, fy = random.uniform(-0.02, 1.02), random.uniform(-0.02, HORIZON_FY - 0.02)
        if math.hypot(fx - 0.17, (fy - 0.035) * 1.78) < 0.05:
            continue
        sx_, sy_ = S(fx, fy, 0.0)
        s = random.uniform(0.025, 0.06)
        stars.append(((sx_, sy_, 0.0), (s, s, s), (0, 0, 0)))
    only_at(batch("stars", "ico", FAR, M["star"], stars, sub=1), "night")

    # ---------- 大气 ----------
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    make_mesh_object("atmosphere", bm, FX, M["haze"], loc=(0, 6, 5), scale=(80, 80, 12))

    # ---------- 鸭子 ----------
    for i, (fx, fy) in enumerate(((0.065, 0.80), (0.085, 0.865), (0.048, 0.875), (0.07, 0.935))):
        x_, y_ = S(fx, fy, 0.0)
        shape(f"duck{i}_body", "sphere", WATER, M["white"], loc=(x_, y_, 0.12), scale=(0.28, 0.19, 0.15), rot=(0, 0, 0.6))
        shape(f"duck{i}_tail", "cone", WATER, M["white"], loc=(x_ - 0.22, y_ - 0.12, 0.22), scale=(0.08, 0.08, 0.12),
              rot=(0, -0.8, 0.6), seg=5)
        shape(f"duck{i}_head", "sphere", WATER, M["white"], loc=(x_ + 0.18, y_ + 0.12, 0.33), scale=(0.11, 0.11, 0.11))
        shape(f"duck{i}_beak", "cone", WATER, M["beak"], loc=(x_ + 0.27, y_ + 0.18, 0.32), scale=(0.04, 0.04, 0.09),
              rot=(0, math.pi / 2, 0.6), seg=5)
        shape(f"duck{i}_ripple", "cyl", WATER, M["foam"], loc=(x_, y_, 0.015), scale=(0.42, 0.3, 0.005), rot=(0, 0, 0.6), seg=14)

    # ---------- 萤火虫 ----------
    flies = []
    for _ in range(80):
        fx, fy = random.choice(((0.50, 0.45), (0.62, 0.70), (0.30, 0.75), (0.75, 0.50), (0.45, 0.95), (0.88, 0.65)))
        x_, y_ = S(fx + random.uniform(-0.08, 0.08), fy + random.uniform(-0.08, 0.08))
        flies.append(((x_, y_, z + random.uniform(0.4, 2.6)), (0.045, 0.045, 0.045), (0, 0, 0)))
    batch("fireflies", "ico", FX, M["firefly"], flies, sub=1)

    # ---------- 暖色补光（夜）：灯笼照亮的地面光晕 ----------
    for i, (fx, fy, pw, sz) in enumerate(((0.34, 0.56, 0.7, 3.5), (0.46, 0.84, 0.9, 3.5), (0.82, 0.65, 0.7, 3.0),
                                          (0.20, 0.63, 0.8, 3.5), (0.44, 0.37, 0.6, 3.0), (0.63, 0.60, 0.6, 3.0),
                                          (0.36, 0.78, 0.6, 3.0))):
        ax, ay = S(fx, fy)
        area_light(LC, f"fill_warm{i}", (ax, ay, z + 3.0), (1.0, 0.72, 0.42),
                   {k: v * pw for k, v in FILL_POWER.items()}, size=sz)

    # 冷色月光补光（从镜头这边柔和地照亮屋顶、树冠，夜里看得清形状）
    f_, r_, u_ = _cam_basis()
    fg_ = Vector((f_.x, f_.y, 0)).normalized()
    mfl = area_light(LC, "fill_moon", (-fg_.x * 10, -fg_.y * 10, 16.0), (0.58, 0.68, 1.0),
                     {"morning": 0.0, "noon": 0.0, "night": 1400.0}, size=26.0)
    con = mfl.constraints.new("TRACK_TO")
    tgt = bpy.data.objects.new("fill_moon_target", None)
    tgt.location = (0, 0, z)
    LC.objects.link(tgt)
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    # ---------- 人物占位（之后由 import_character.py 换成伊蕾娜）----------
    cx_, cy_ = L["char"]
    build_character(CH, M, cx_, cy_, z)
    return BG, FG, CH, LC


# ============================================================
# 对外接口
# ============================================================

class _API:
    apply_time = staticmethod(lambda name: apply_time(name))
    preview = staticmethod(lambda scale=50: preview(scale))
    render_all = staticmethod(lambda: render_all())
    render_scene_layers = staticmethod(lambda: render_scene_layers())
    render_walkmask = staticmethod(lambda: render_walkmask())
    render_character = staticmethod(lambda frames=None: render_character(frames))
    render_character_shadow = staticmethod(lambda: render_character_shadow())
    rebuild = staticmethod(lambda: build())
    S = staticmethod(S)


bpy.app.driver_namespace["gsd"] = _API
builtins.gsd = _API

if not _ATTACH_V4:
    build()
else:
    rebind()
    print("[共生岛] v4 已连接到当前打开的场景（未重建）")
