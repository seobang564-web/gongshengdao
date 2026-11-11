# -*- coding: utf-8 -*-
"""
共生岛 · 岛屿最终版：构建全部人物片段 → island_{morning,noon,night}.blend + clips_island.json
运行（Mac，无界面）：Blender -b gongshengdao_v4_anim.blend -P island_final/build_clips.py
  · 所有一次性片段从「中立站姿」（站立待机第 1 帧）开始、回到中立站姿结束；坐着的片段以「中立坐姿」衔接
  · 循环片段 192 帧，首尾交叉淡化闭合
  · 走路 / 小跑：沿路径移动 CHAR_root，步伐按实际移动距离推进（不滑步），平滑转身，贴合地面 / 台阶 / 门廊
  · 坐下：按凳面高度修正臀部位置
  · 斗篷物理摆动（cloth_sim），头尾钉到相邻片段的衣摆姿势
  · 每个片段按时段的光照方向算出裁剪区域（含影子）
"""
import bpy, os, sys, json, math, time, builtins
from mathutils import Vector, Quaternion, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
BLD = os.path.dirname(HERE)
LOG = os.path.join(HERE, "build_log.txt")
open(LOG, "w", encoding="utf-8").write("")
T0 = time.time()


def log(m):
    m = f"[{time.time() - T0:6.1f}s] {m}"
    print(m)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


# ------------------------------------------------------------------ 载入重定向库
sys.argv = [sys.argv[0], "--", "lib"]
RT = {"__name__": "gsd_retarget"}
_p = os.path.join(BLD, "retarget_mixamo.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), RT)
sys.path.insert(0, BLD)
import cloth_sim
rig = RT["rig"]; TB = RT["TB"]; W = RT["W"]; W3i = RT["W3i"]; LAST = RT["LAST"]
root_R3 = RT["R"]["root.x"].to_matrix()
sc = bpy.context.scene
ROOTOB = bpy.data.objects["CHAR_root"]
CAM = sc.camera

# 场景脚本（apply_time 等）
gsd_ns = {"__name__": "__main__", "GSD_ATTACH": True}
_p = os.path.join(BLD, "gongshengdao_scene_v4.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), gsd_ns)
gsd = builtins.gsd

RAMP = 12          # 起步 / 停步、进入 / 离开中立姿势的过渡帧数
LOOP = 192


def ease(t):
    t = min(1.0, max(0.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


# ------------------------------------------------------------------ 动作读写（兼容 5.x 分层动作）
def act_fcurves(act):
    try:
        return list(act.fcurves)
    except AttributeError:
        return [fc for l in act.layers for s in l.strips for cb in s.channelbags for fc in cb.fcurves]


MODES0 = {pb.name: pb.rotation_mode for pb in rig.pose.bones}


def sample(act, n, start=1):
    ch = {}
    for fc in act_fcurves(act):
        dp = fc.data_path
        if not dp.startswith('pose.bones["'):
            continue
        bn = dp.split('"')[1]
        prop = dp.rsplit(".", 1)[1]
        ch.setdefault(bn, {}).setdefault(prop, {})[fc.array_index] = fc
    out = []
    for f in range(start, start + n):
        P = {}
        for bn, pr in ch.items():
            lc = pr.get("location", {})
            loc = Vector([lc[i].evaluate(f) if i in lc else 0.0 for i in range(3)])
            if "rotation_quaternion" in pr:
                qc = pr["rotation_quaternion"]
                q = Quaternion([qc[i].evaluate(f) if i in qc else (1.0 if i == 0 else 0.0) for i in range(4)])
                q.normalize()
            elif "rotation_euler" in pr:
                ec = pr["rotation_euler"]
                order = MODES0.get(bn, "XYZ")
                order = order if order in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX") else "XYZ"
                q = Euler([ec[i].evaluate(f) if i in ec else 0.0 for i in range(3)], order).to_quaternion()
            else:
                q = Quaternion()
            P[bn] = (loc, q)
        out.append(P)
    return out


ZERO = (Vector((0, 0, 0)), Quaternion())


def blend(Pa, Pb, w):
    if w <= 0:
        return dict(Pa)
    if w >= 1:
        return dict(Pb)
    out = {}
    for bn in set(Pa) | set(Pb):
        la, qa = Pa.get(bn, ZERO)
        lb, qb = Pb.get(bn, ZERO)
        qb = qb.copy(); qb.make_compatible(qa)
        out[bn] = (la.lerp(lb, w), qa.slerp(qb, w))
    return out


def new_action(name):
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    a = bpy.data.actions.new(name)
    a.use_fake_user = True
    return a


def put(act, idb, path, idx, vals, grp):
    fc = act.fcurve_ensure_for_datablock(idb, path, index=idx, group_name=grp)
    kp = fc.keyframe_points
    kp.add(len(vals))
    co = []
    for i, v in enumerate(vals):
        co += [float(i + 1), float(v)]
    kp.foreach_set("co", co)
    for k in kp:
        k.interpolation = "LINEAR"
    fc.update()


def assign(ob, act):
    ob.animation_data_create()
    ob.animation_data.action = act
    try:
        if act.slots and ob.animation_data.action_slot is None:
            ob.animation_data.action_slot = act.slots[0]
    except AttributeError:
        pass


def write_rig(name, frames):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    act = new_action("CLIP_" + name)
    assign(rig, act)
    bones = sorted(set().union(*[set(f) for f in frames]))
    for bn in bones:
        if bn not in rig.pose.bones:
            continue
        locs = [fr.get(bn, ZERO)[0] for fr in frames]
        qs, prev = [], None
        for fr in frames:
            q = fr.get(bn, ZERO)[1].copy()
            if prev is not None:
                q.make_compatible(prev)
            prev = q
            qs.append(q)
        if any(l.length > 1e-7 for l in locs):
            for i in range(3):
                put(act, rig, f'pose.bones["{bn}"].location', i, [l[i] for l in locs], bn)
        for i in range(4):
            put(act, rig, f'pose.bones["{bn}"].rotation_quaternion', i, [q[i] for q in qs], bn)
    assign(rig, act)
    return act


def write_root(name, locs, heads):
    act = new_action("CLIPR_" + name)
    assign(ROOTOB, act)
    ROOTOB.rotation_mode = "XYZ"
    un, prev = [], None
    for h in heads:
        if prev is not None:
            while h - prev > math.pi:
                h -= 2 * math.pi
            while h - prev < -math.pi:
                h += 2 * math.pi
        un.append(h); prev = h
    for i in range(3):
        put(act, ROOTOB, "location", i, [l[i] for l in locs], "root")
    for i in range(2):
        put(act, ROOTOB, "rotation_euler", i, [0.0] * len(locs), "root")
    put(act, ROOTOB, "rotation_euler", 2, un, "root")
    assign(ROOTOB, act)
    return act


def to_local(v):
    """世界空间（默认朝向）位移 → root.x 骨骼的本地位移"""
    return root_R3.transposed() @ (W3i @ v)


def add_root(frames, corr):
    for i, fr in enumerate(frames):
        l, q = fr.get("root.x", ZERO)
        fr["root.x"] = (l + to_local(corr[i]), q)


def heading_of(d):
    return math.atan2(d.x, -d.y)


def ang_lerp(a, b, w):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * w


# ------------------------------------------------------------------ 地面高度（射线）
GROUND = [o for o in bpy.data.objects if o.type == "MESH" and (
    o.name in ("island_top", "campfire_ground", "house_porch_planks", "house_porch_side_planks", "dock_planks")
    or o.name.startswith(("path_main", "path_back", "path_bridge", "house_step")) and "edge" not in o.name and "side" not in o.name)]
DG = bpy.context.evaluated_depsgraph_get()


def ground(x, y):
    best = None
    for o in GROUND:
        ev = o.evaluated_get(DG)
        mi = ev.matrix_world.inverted()
        org = mi @ Vector((x, y, 30.0))
        dr = (mi.to_3x3() @ Vector((0, 0, -1))).normalized()
        ok, loc, nor, idx = ev.ray_cast(org, dr)
        if ok:
            z = (ev.matrix_world @ loc).z
            best = z if best is None else max(best, z)
    return best if best is not None else 0.45


STAND = Vector(ROOTOB.location)
H0 = ROOTOB.rotation_euler.z
Z_OFF = STAND.z - ground(STAND.x, STAND.y)
log(f"站位 {tuple(round(v, 3) for v in STAND)} 朝向 {math.degrees(H0):.1f}° 地面偏移 {Z_OFF:.3f}")


def rootz(x, y):
    return ground(x, y) + Z_OFF


# 关键位置
FIRE_C = Vector(bpy.data.objects["campfire_ash"].matrix_world.translation)
SEAT = bpy.data.objects["campfire_seat0"]
SEAT_C = Vector(SEAT.matrix_world.translation)
SEAT_TOP = max((SEAT.matrix_world @ Vector(c)).z for c in SEAT.bound_box)
F_FIRE = Vector((FIRE_C.x - SEAT_C.x, FIRE_C.y - SEAT_C.y, 0)).normalized()     # 坐着时面朝篝火
H_FIRE = heading_of(F_FIRE)
PL = bpy.data.objects["planter3_box"]
PL_C = Vector(PL.matrix_world.translation)
PL_AX = (PL.matrix_world.to_3x3() @ Vector((1, 0, 0))).normalized()
PL_AX.z = 0; PL_AX.normalize()
if PL_AX.x < 0:
    PL_AX = -PL_AX
DOOR = Vector(bpy.data.objects["house_door"].matrix_world.translation)
log(f"篝火 {FIRE_C[:2]} 凳子 {SEAT_C[:2]} 凳面 {SEAT_TOP:.3f} 面向篝火 {math.degrees(H_FIRE):.1f}°；花箱 {PL_C[:2]} 轴 {PL_AX[:2]}；门 {DOOR[:2]}")

# ------------------------------------------------------------------ 先做重定向（这一步需要完整场景）
SRC = {}


def get_src(clip, in_place=None):
    n = RT["retarget"](clip, in_place=in_place)
    act = rig.animation_data.action
    fr = sample(act, n)
    SRC[clip] = {"frames": fr, "hip": [h.copy() for h in LAST.get("hip", [])], "drift": LAST.get("drift"), "n": n, "k": LAST.get("k")}
    bpy.data.actions.remove(act)
    log(f"重定向 {clip}: {n} 帧，k={LAST.get('k', 0):.3f}，位移 {tuple(round(v, 3) for v in (LAST.get('drift') or Vector()))}")


IDLE_ACT = bpy.data.actions.get("rig动作")
IDLE_ACT.use_fake_user = True
IDLE = sample(IDLE_ACT, LOOP)
for c, ip in (("Waving", None), ("Joyful Jump", None), ("Victory Idle", None), ("Arm Stretching", None), ("Yawn", None),
              ("Watering", True), ("Throwing", True), ("Happy Walk", True), ("Jogging", True),
              ("Stand To Sit", False), ("Sitting", False), ("Sit To Stand", False)):
    get_src(c, ip)
# 删除重定向用的源场景
mx = bpy.data.scenes.get("MX_SRC")
if mx:
    bpy.data.scenes.remove(mx)

# ------------------------------------------------------------------ 路径（射线要在完整场景里做）


def chaikin(pts, it=2):
    for _ in range(it):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [a * 0.75 + b * 0.25, a * 0.25 + b * 0.75]
        q.append(pts[-1])
        pts = q
    return pts


def path_samples(pts2d, ds=0.02):
    pts = chaikin([Vector((x, y)) for x, y in pts2d])
    seg = [(a, b, (b - a).length) for a, b in zip(pts[:-1], pts[1:])]
    L = sum(s[2] for s in seg)
    out, d = [], 0.0
    n = max(2, int(L / ds) + 1)
    si, acc = 0, 0.0
    for k in range(n):
        target = L * k / (n - 1)
        while si < len(seg) - 1 and acc + seg[si][2] < target:
            acc += seg[si][2]; si += 1
        a, b, l = seg[si]
        t = (target - acc) / l if l > 1e-9 else 0
        p = a.lerp(b, min(1, max(0, t)))
        tan = (b - a).normalized() if l > 1e-9 else Vector((1, 0))
        out.append((p.x, p.y, rootz(p.x, p.y), math.atan2(tan.x, -tan.y)))
    return out, L


FIRE_SPOT_D = None  # 站起点距凳子中心的水平距离 = Stand To Sit 的臀部后移量
d_sit = SRC["Stand To Sit"]["hip"][-1] - SRC["Stand To Sit"]["hip"][0]
FIRE_SPOT_D = Vector((d_sit.x, d_sit.y, 0)).length
FIRE_SPOT = SEAT_C + F_FIRE * FIRE_SPOT_D
FIRE_SPOT.z = rootz(FIRE_SPOT.x, FIRE_SPOT.y)
PL_SPOT = PL_C + PL_AX * (1.1 + 0.5)
PL_SPOT.z = rootz(PL_SPOT.x, PL_SPOT.y)
H_PL = heading_of(-PL_AX)
DOOR_SPOT = Vector((DOOR.x, DOOR.y - 0.42, 0)); DOOR_SPOT.z = rootz(DOOR_SPOT.x, DOOR_SPOT.y)
log(f"篝火站起点 {tuple(round(v, 3) for v in FIRE_SPOT)}（凳前 {FIRE_SPOT_D:.2f}m）；花箱站位 {tuple(round(v, 3) for v in PL_SPOT)}；门前 {tuple(round(v, 3) for v in DOOR_SPOT)}")

S2 = (STAND.x, STAND.y)
P_FIRE = [S2, (-1.0, -0.6), (-0.55, -1.9), (0.95, -2.95), (0.85, -3.85), (0.3, -3.95), (FIRE_SPOT.x, FIRE_SPOT.y)]
P_PL = [S2, (-2.8, 0.35), (-4.4, 0.65), (PL_SPOT.x, PL_SPOT.y)]
P_DOOR = [(FIRE_SPOT.x, FIRE_SPOT.y), (0.3, -3.95), (0.85, -3.85), (0.95, -2.95), (-0.55, -1.9), (-1.4, 0.2),
          (-2.4, 1.25), (-2.45, 2.95), (-2.85, 3.6), (DOOR_SPOT.x, DOOR_SPOT.y)]
PATHS = {"fire": path_samples(P_FIRE), "fire_back": path_samples(P_FIRE[::-1]),
         "planter": path_samples(P_PL), "planter_back": path_samples(P_PL[::-1]), "door": path_samples(P_DOOR)}
for k, (s, L) in PATHS.items():
    log(f"路径 {k}: {L:.2f} m，高度 {min(p[2] for p in s):.2f}–{max(p[2] for p in s):.2f}")

# ------------------------------------------------------------------ 之后只保留人物集合，逐帧求值会快很多
EXCL = {}
for vl in sc.view_layers:
    for lc in vl.layer_collection.children:
        EXCL[(vl.name, lc.name)] = lc.exclude
        lc.exclude = lc.name != "CHAR_人物"

CAPE = [n for c in cloth_sim.chains(rig) for n in c]
CLIPS = {}


def cape_pose(P):
    return {n: P[n][1] for n in CAPE if n in P}


def finish(name, frames, root_locs, root_heads, loop, pos_from, pos_to, pose_from, pose_to, times, pin_s=None, pin_e=None, fade_out=0):
    n = len(frames)
    write_root(name, root_locs, root_heads)
    act = write_rig(name, frames)
    sc.frame_start, sc.frame_end = 1, n
    out = cloth_sim.simulate(rig, 1, n, loop=loop, log=log, pin_start=pin_s, pin_end=pin_e)
    CLIPS[name] = {"name": name, "frames": n, "loop": loop, "from": pos_from, "to": pos_to, "pose_from": pose_from,
                   "pose_to": pose_to, "times": times, "fade_out": fade_out, "rig_action": act.name, "root_action": "CLIPR_" + name}
    log(f"片段 {name}: {n} 帧 {'循环' if loop else '一次性'} {pos_from}→{pos_to}  时段 {times}")
    return out


def static_root(n, pos, h):
    return [pos.copy() for _ in range(n)], [h] * n


ALL3 = ["morning", "noon", "night"]

# ---------- A1 站立待机（循环）→ 得到中立站姿 N
A1 = [dict(f) for f in IDLE]
co = finish("A1_idle", A1, *static_root(LOOP, STAND, H0), True, "stand", "stand", "stand", "stand", ALL3)
N = dict(A1[0])
for nm, q in co[0].items():
    N[nm] = (N.get(nm, ZERO)[0], q)
N_CAPE = dict(co[0])


def one_shot(frames, start=None, end=None):
    start = start or N
    end = end or N
    n = len(frames)
    out = []
    for i, fr in enumerate(frames):
        p = fr
        wi = ease(i / RAMP) if i < RAMP else 1.0
        if wi < 1:
            p = blend(start, p, wi)
        j = n - 1 - i
        wo = ease(j / RAMP) if j < RAMP else 1.0
        if wo < 1:
            p = blend(end, p, wo)
        out.append(p)
    return out


def src_frames(clip):
    return [dict(f) for f in SRC[clip]["frames"]]


# ---------- 原地一次性动作
for name, clip, times in (("B2_wave", "Waving", ALL3), ("A3_stretch", "Arm Stretching", ["morning"]),
                          ("C1a_yawn", "Yawn", ["morning"]), ("C2b_feed", "Throwing", ["noon"])):
    fr = one_shot(src_frames(clip))
    finish(name, fr, *static_root(len(fr), STAND, H0), False, "stand", "stand", "stand", "stand", times, N_CAPE, N_CAPE)

# ---------- B3 欢呼 = 开心跳 + 胜利欢呼（中间交叉 10 帧）
J, V = src_frames("Joyful Jump"), src_frames("Victory Idle")
OV = 10
B3 = J[:len(J) - OV] + [blend(J[len(J) - OV + i], V[i], ease((i + 1) / (OV + 1))) for i in range(OV)] + V[OV:]
fr = one_shot(B3)
finish("B3_cheer", fr, *static_root(len(fr), STAND, H0), False, "stand", "stand", "stand", "stand", ALL3, N_CAPE, N_CAPE)

# ---------- C1b 浇花（花箱旁）
fr = one_shot(src_frames("Watering"))
finish("C1b_water", fr, *static_root(len(fr), PL_SPOT, H_PL), False, "planter", "planter", "stand", "stand", ["morning"], N_CAPE, N_CAPE)

# ---------- 坐下修正
PELVIS_REL = (W @ TB["root.x"].head_local).z - ROOTOB.matrix_world.translation.z
SEAT_REL = SEAT_C - FIRE_SPOT
TARGET = Vector((SEAT_REL.x, SEAT_REL.y, SEAT_TOP + 0.10 - FIRE_SPOT.z - PELVIS_REL))
log(f"坐姿目标（相对站起点的臀部位移）{tuple(round(v, 3) for v in TARGET)}")

# C3_fire_loop：Sitting 截 192 帧并首尾淡化闭合
S_src = src_frames("Sitting")
S_hip = SRC["Sitting"]["hip"]
mean = sum(S_hip, Vector()) / len(S_hip)
add_root(S_src, [TARGET - mean] * len(S_src))
s0, XF = 24, 24
loopfr = []
for i in range(LOOP):
    p = S_src[s0 + i]
    if i >= LOOP - XF:
        p = blend(p, S_src[i - (LOOP - XF)], ease((i - (LOOP - XF) + 1) / (XF + 1)))
    loopfr.append(p)
co = finish("C3_fire_loop", loopfr, *static_root(LOOP, FIRE_SPOT, H_FIRE), True, "fire", "fire", "seat", "seat", ["noon", "night"])
SEATP = dict(loopfr[0])
for nm, q in co[0].items():
    SEATP[nm] = (SEATP.get(nm, ZERO)[0], q)
S_CAPE = dict(co[0])


def sit_corr(hip, target_end_seated, standing_first):
    """站→坐 或 坐→站：按臀部高度算坐下进度 p，修正量在「站立对齐」和「坐姿对齐」之间过渡"""
    zs = [h.z for h in hip]
    hs = hip[0] if standing_first else hip[-1]      # 站立那一端
    hd = hip[-1] if standing_first else hip[0]      # 坐着那一端
    A = Vector((-hs.x, -hs.y, 0))
    Bc = target_end_seated - hd
    dz = hd.z - hs.z
    out = []
    for h in hip:
        p = min(1, max(0, (h.z - hs.z) / dz)) if abs(dz) > 1e-4 else 0
        out.append(A.lerp(Bc, p))
    return out


fr = src_frames("Stand To Sit")
add_root(fr, sit_corr(SRC["Stand To Sit"]["hip"], TARGET, True))
fr = one_shot(fr, N, SEATP)
finish("C3_fire_in", fr, *static_root(len(fr), FIRE_SPOT, H_FIRE), False, "fire", "fire", "stand", "seat", ["noon", "night"], N_CAPE, S_CAPE)
fr = src_frames("Sit To Stand")
add_root(fr, sit_corr(SRC["Sit To Stand"]["hip"], TARGET, False))
fr = one_shot(fr, SEATP, N)
finish("C3_fire_out", fr, *static_root(len(fr), FIRE_SPOT, H_FIRE), False, "fire", "fire", "seat", "stand", ["noon", "night"], S_CAPE, N_CAPE)


# ---------- 走路 / 小跑
def gait(clip):
    fr = SRC[clip]["frames"]
    n = len(fr)

    def diff(a, b):
        return sum(a[k][1].rotation_difference(b[k][1]).angle for k in a if k in b and k in ("thigh_stretch.l", "thigh_stretch.r", "leg_stretch.l", "leg_stretch.r"))
    per = min((n - 1, n), key=lambda P: diff(fr[0], fr[P % n] if P < n else fr[0]) if P < n else 9)
    if per >= n:
        per = n - 1
    dr = SRC[clip]["drift"]
    speed = Vector((dr.x, dr.y)).length / (n - 1)
    return fr, per, speed


def build_walk(name, clip, pkey, h_start, h_end, pos_from, pos_to, times, hold_end=0, fade_out=0):
    fr, per, speed = gait(clip)
    samp, L = PATHS[pkey]
    T = int(math.ceil(L / speed + RAMP)) + 1
    vel = [min(1.0, (i + 0.5) / RAMP, (T - 1 - i - 0.5) / RAMP) for i in range(T - 1)]
    cum = [0.0]
    for v in vel:
        cum.append(cum[-1] + v)
    sc_ = L / cum[-1]
    frames, locs, heads = [], [], []
    TURN = 16
    for i in range(T):
        dist = cum[i] * sc_
        k = min(len(samp) - 1, int(round(dist / L * (len(samp) - 1))))
        x, y, z, ht = samp[k]
        ph = (dist / speed) % per
        a = int(ph); b = (a + 1) % per
        g = blend(fr[a], fr[b], ph - a)
        w = ease(min(i / RAMP, (T - 1 - i) / RAMP))
        frames.append(blend(N, g, w))
        h = ht
        if i < TURN:
            h = ang_lerp(h_start, ht, ease(i / TURN))
        if T - 1 - i < TURN:
            h = ang_lerp(h_end, h, ease((T - 1 - i) / TURN))
        locs.append(Vector((x, y, z)))
        heads.append(h)
    for _ in range(hold_end):
        frames.append(dict(N)); locs.append(locs[-1].copy()); heads.append(heads[-1])
    finish(name, frames, locs, heads, False, pos_from, pos_to, "stand", "stand", times, N_CAPE, N_CAPE, fade_out)


build_walk("W_stand_fire", "Happy Walk", "fire", H0, H_FIRE, "stand", "fire", ["noon", "night"])
build_walk("W_fire_stand", "Happy Walk", "fire_back", H_FIRE, H0, "fire", "stand", ["noon", "night"])
build_walk("W_stand_planter", "Happy Walk", "planter", H0, H_PL, "stand", "planter", ["morning"])
build_walk("W_planter_stand", "Happy Walk", "planter_back", H_PL, H0, "planter", "stand", ["morning"])
build_walk("B4_rush", "Jogging", "door", H_FIRE, math.pi, "fire", "door", ["night"], hold_end=14, fade_out=12)

# ------------------------------------------------------------------ 闭合检查
def pose_err(Pa, Pb):
    e = 0.0
    for bn in set(Pa) | set(Pb):
        if bn in CAPE:
            continue
        la, qa = Pa.get(bn, ZERO); lb, qb = Pb.get(bn, ZERO)
        e = max(e, math.degrees(qa.rotation_difference(qb).angle) if qa.rotation_difference(qb).angle < math.pi else 0, (la - lb).length * 100)
    return e


report = {}
for name, c in CLIPS.items():
    act = bpy.data.actions[c["rig_action"]]
    fr = sample(act, c["frames"])
    if c["loop"]:
        nxt = sample(act, 1, start=c["frames"] + 1)[0] if False else fr[0]
        e = pose_err(fr[-1], fr[0])
        report[name] = {"loop_last_vs_first": round(e, 2)}
    else:
        ref_s = N if c["pose_from"] == "stand" else SEATP
        ref_e = N if c["pose_to"] == "stand" else SEATP
        report[name] = {"start_vs_neutral": round(pose_err(fr[0], ref_s), 3), "end_vs_neutral": round(pose_err(fr[-1], ref_e), 3)}
log("闭合检查（角度°或厘米，越小越好）：" + json.dumps(report, ensure_ascii=False))

# ------------------------------------------------------------------ 每帧人物关键点（算裁剪区域）
KEYB = ["head.x", "hand.l", "hand.r", "foot.l", "foot.r", "toes_01.l", "toes_01.r", "root.x", "forearm_stretch.l", "forearm_stretch.r"]
tips = [c[-1] for c in cloth_sim.chains(rig)]
PTS = {}
for name, c in CLIPS.items():
    assign(rig, bpy.data.actions[c["rig_action"]]); assign(ROOTOB, bpy.data.actions[c["root_action"]])
    pts = []
    for f in range(1, c["frames"] + 1):
        sc.frame_set(f)
        M = rig.matrix_world
        pb = rig.pose.bones
        for b in KEYB:
            if b in pb:
                pts.append(M @ pb[b].head)
        hd = M @ pb["head.x"].head
        pts.append(hd + Vector((0, 0, 0.55)))     # 帽尖
        for side in (Vector((0.45, 0, 0.35)), Vector((-0.45, 0, 0.35)), Vector((0, 0.45, 0.35)), Vector((0, -0.45, 0.35))):
            pts.append(hd + side)                  # 帽檐
        for t in tips:
            pts.append(M @ pb[t].tail)
    PTS[name] = pts
for vl in sc.view_layers:
    for lc in vl.layer_collection.children:
        lc.exclude = EXCL[(vl.name, lc.name)]

RX, RY = sc.render.resolution_x, sc.render.resolution_y


def crop_for(pts, t):
    lights = [o for o in bpy.data.objects if o.type == "LIGHT" and not o.hide_render]
    suns = [o for o in lights if o.data.type == "SUN"]
    pnts = [o for o in lights if o.data.type in ("POINT", "SPOT") and o.data.energy > 1]
    allp = list(pts)
    gz = min(p.z for p in pts) - 0.05
    for p in pts[::3]:
        for s in suns:
            ld = (s.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
            if ld.z < -0.05:
                q = p + ld * ((p.z - gz) / -ld.z)
                if (q - p).length > 6:
                    q = p + (q - p).normalized() * 6
                allp.append(q)
        for o in pnts:
            lp = o.matrix_world.translation
            if (lp - p).length > 7 or lp.z <= p.z + 0.05:
                continue
            q = lp + (p - lp) * ((lp.z - gz) / (lp.z - p.z))
            if (q - p).length > 3.5:
                q = p + (q - p).normalized() * 3.5
            allp.append(q)
    xs, ys = [], []
    for p in allp:
        v = world_to_camera_view(sc, CAM, p)
        xs.append(v.x); ys.append(v.y)
    M = 48
    x0 = max(0, int(min(xs) * RX) - M); x1 = min(RX, int(math.ceil(max(xs) * RX)) + M)
    yb = max(0, int(min(ys) * RY) - M); yt = min(RY, int(math.ceil(max(ys) * RY)) + M)
    if (x1 - x0) % 2: x1 = x1 - 1 if x1 == RX else x1 + 1
    if (yt - yb) % 2: yt = yt - 1 if yt == RY else yt + 1
    return [x0, RY - yt, x1 - x0, yt - yb]        # 左上原点：x, y, 宽, 高


# ------------------------------------------------------------------ 渲染设置 + 三个时段文件
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("shadow_ray_count", 2), ("shadow_step_count", 10),
                  ("shadow_resolution_scale", 1.0), ("shadow_pool_size", "1024"), ("volumetric_tile_size", "8"),
                  ("volumetric_samples", 64), ("use_volumetric_shadows", True), ("fast_gi_method", "GLOBAL_ILLUMINATION")):
    try:
        setattr(ee, attr, val)
    except Exception:
        pass
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.use_compositing = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
for ob in bpy.data.objects:
    for md in ob.modifiers:
        if md.type == "PARTICLE_SYSTEM":
            md.show_render = True
atm = bpy.data.objects.get("atmosphere")
if atm:
    atm.hide_render = False
for vl in sc.view_layers:
    vl.use = (vl.name == "BG")
for name in ("FG_前景遮挡", "CHAR_人物", "LIGHTS_灯光"):
    lc = sc.view_layers["BG"].layer_collection.children.get(name)
    if lc:
        lc.exclude = False
try:
    bpy.ops.file.pack_all()
except Exception as e:
    log(f"打包贴图出错 {e}")


def add_flicker():
    """夜里灯笼轻闪：用整数频率的正弦叠加，192 帧整周期（背景循环和人物片段的环境光完全一致）"""
    for ob, _ in gsd_ns["LIGHTS"]:
        if ob.data.type != "POINT" or not any(k in ob.name for k in ("lamp", "hang", "dock")) or "campfire" in ob.name:
            continue
        E = ob.data.energy
        if E <= 0:
            continue
        ph = (hash(ob.name) % 100) / 100.0 * 2 * math.pi
        for f in range(1, LOOP + 2):
            t = (f - 1) / LOOP
            ob.data.energy = E * (1 + 0.07 * math.sin(2 * math.pi * 23 * t + ph) + 0.05 * math.sin(2 * math.pi * 41 * t + 2 * ph))
            ob.data.keyframe_insert("energy", frame=f)
        ob.data.energy = E
        for fc in act_fcurves(ob.data.animation_data.action):
            if not any(m.type == "CYCLES" for m in fc.modifiers):
                fc.modifiers.new("CYCLES")


def ensure_cyclic():
    """环境动画全部 192 帧循环（片段超过 192 帧时，环境和背景循环保持同相位）"""
    n = 0
    pools = [bpy.data.objects, bpy.data.lights, bpy.data.materials, bpy.data.worlds, bpy.data.node_groups, bpy.data.shape_keys, bpy.data.cameras]
    for pool in pools:
        for idb in pool:
            ad = getattr(idb, "animation_data", None)
            if not ad or not ad.action or ad.action.name.startswith(("CLIP_", "CLIPR_")):
                continue
            for fc in act_fcurves(ad.action):
                if not any(m.type == "CYCLES" for m in fc.modifiers):
                    fc.modifiers.new("CYCLES"); n += 1
    log(f"补上 Cyclic 的环境曲线：{n} 条")


ensure_cyclic()
# 默认动作：待机
assign(rig, bpy.data.actions["CLIP_A1_idle"]); assign(ROOTOB, bpy.data.actions["CLIPR_A1_idle"])
sc.frame_start, sc.frame_end = 1, LOOP
sc.frame_set(1)
for t in ALL3:
    gsd.apply_time(t)
    if t == "night":
        add_flicker()
    reg = {"time": t, "resolution": [RX, RY], "fps": sc.render.fps, "loop_frames": LOOP, "positions": {
        "stand": list(STAND), "fire": list(FIRE_SPOT), "planter": list(PL_SPOT), "door": list(DOOR_SPOT)}, "clips": []}
    for name, c in CLIPS.items():
        if t in c["times"]:
            e = dict(c)
            e["crop"] = crop_for(PTS[name], t)
            reg["clips"].append(e)
    txt = bpy.data.texts.get("clips_island.json") or bpy.data.texts.new("clips_island.json")
    txt.clear(); txt.write(json.dumps(reg, ensure_ascii=False, indent=1))
    json.dump(reg, open(os.path.join(HERE, f"clips_{t}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = os.path.join(HERE, f"island_{t}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True, copy=True)
    log(f"已保存 {out}：{len(reg['clips'])} 个片段，裁剪 " + ", ".join(f"{e['name']}={e['crop'][2]}x{e['crop'][3]}" for e in reg["clips"]))
json.dump(report, open(os.path.join(HERE, "closure_report.json"), "w"), indent=1, ensure_ascii=False)
log("BUILD_DONE")
