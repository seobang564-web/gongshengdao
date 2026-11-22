# -*- coding: utf-8 -*-
"""
共生岛 · 魔法教室 · 人物白模 v1
运行（Mac，无界面）：Blender -b magic_classroom.blend -P classroom_anim/build_classroom.py
  · 从 gongshengdao_v4_anim.blend 追加伊蕾娜（CHAR_人物），坐到靠窗中排长凳（bench_02）上，面朝黑板
  · B5_listen：Sitting 截 192 帧首尾交叉淡化闭合 + 抬头看黑板 + 两次点头 + 斗篷物理
  · 讲台 CHAR_SPOT_1 放一个灰色老师占位（原创几何体，之后再定）
  · 另存 classroom_anim/classroom_anim.blend（不改 magic_classroom.blend）
  · Workbench 白模：主镜头 cls_CAM_main + 侧背面近景 CAM_side_back，各 192 帧 → whitebox/<镜头>/f_####.jpg
"""
import bpy, os, sys, json, math, time, bmesh
from mathutils import Vector, Quaternion, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
BLD = os.path.dirname(HERE)
LOG = os.path.join(HERE, "build_log.txt")
open(LOG, "w", encoding="utf-8").write("")
T0 = time.time()


def log(m):
    m = f"[{time.time() - T0:6.1f}s] {m}"
    print(m, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


sc = bpy.context.scene
sc.render.fps = 24
log(f"Blender {bpy.app.version_string}，场景 {bpy.data.filepath}")

# ------------------------------------------------------------------ 追加人物
SRCBLEND = os.path.join(BLD, "gongshengdao_v4_anim.blend")
with bpy.data.libraries.load(SRCBLEND, link=False) as (src, dst):
    dst.collections = [c for c in src.collections if c == "CHAR_人物"]
CH = dst.collections[0]
sc.collection.children.link(CH)
rig = next(o for o in CH.all_objects if o.type == "ARMATURE")
ROOTOB = bpy.data.objects.get("CHAR_root")
if ROOTOB is None:
    raise RuntimeError("没找到 CHAR_root")
if not ROOTOB.users_collection:
    CH.objects.link(ROOTOB)
par = rig
chain = []
while par.parent:
    chain.append(par.parent.name); par = par.parent
log(f"人物集合 {CH.name}，骨架 {rig.name}，父级链 {chain}，物体数 {len(CH.all_objects)}")

# ------------------------------------------------------------------ 座位（靠窗中排 bench_02）
bpy.context.view_layer.update()
def find(suffix):
    return next(o for o in bpy.data.objects if o.name.endswith(suffix))
ROOM = find("room_root")
SEAT = find("bench_02_seat")
APRON = find("desk_02_apron")
R3 = ROOM.matrix_world.to_3x3()
FWD = (R3 @ Vector((0, 1, 0))); FWD.z = 0; FWD.normalize()        # 学生面朝黑板 = 房间 +y
RIGHT = (R3 @ Vector((1, 0, 0))); RIGHT.z = 0; RIGHT.normalize()
SEAT_C = SEAT.matrix_world.translation.copy()
SEAT_TOP = max((SEAT.matrix_world @ Vector(c)).z for c in SEAT.bound_box)
APRON_BOT = min((APRON.matrix_world @ Vector(c)).z for c in APRON.bound_box)
SEAT_X = -0.30                                                  # 坐在凳子靠窗一侧（课本前）
SEATPOS = SEAT_C + RIGHT * SEAT_X
FLOOR_Z = SEAT_TOP - 0.45
H = math.atan2(FWD.x, -FWD.y)
ROOTOB.animation_data_clear()
ROOTOB.rotation_mode = "XYZ"
ROOTOB.location = (SEATPOS.x, SEATPOS.y, FLOOR_Z)
ROOTOB.rotation_euler = (0, 0, H)
bpy.context.view_layer.update()
log(f"凳面 {SEAT_TOP:.3f}，桌裙下沿 {APRON_BOT:.3f}，座位 {tuple(round(v, 3) for v in SEATPOS)}，朝向 {math.degrees(H):.1f}°")

# ------------------------------------------------------------------ 载入重定向库（人物已放到座位上）
sys.argv = [sys.argv[0], "--", "lib"]
RT = {"__name__": "gsd_retarget"}
_p = os.path.join(BLD, "retarget_mixamo.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), RT)
sys.path.insert(0, BLD)
import cloth_sim
rig = RT["rig"]; TB = RT["TB"]; W = RT["W"]; W3i = RT["W3i"]; LAST = RT["LAST"]
root_R3 = RT["R"]["root.x"].to_matrix()
RAMP = 12
LOOP = 192

# ------------------------------------------------------------------ 工具函数（取自 island_final/build_clips.py）
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


# ------------------------------------------------------------------ B5_listen
n = RT["retarget"]("Sitting", in_place=False)
act = rig.animation_data.action
S_src = sample(act, n)
S_hip = [h.copy() for h in LAST["hip"]]
bpy.data.actions.remove(act)
mx = bpy.data.scenes.get("MX_SRC")
if mx:
    bpy.data.scenes.remove(mx)
log(f"重定向 Sitting：{n} 帧，k={LAST.get('k', 0):.3f}")

PELVIS_W = W @ TB["root.x"].head_local
HIP_TARGET = Vector((SEATPOS.x, SEATPOS.y, SEAT_TOP + 0.10)) - FWD * 0.02
TARGET = HIP_TARGET - PELVIS_W
mean = sum(S_hip, Vector()) / len(S_hip)
add_root(S_src, [TARGET - mean] * len(S_src))
log(f"臀部目标 {tuple(round(v, 3) for v in HIP_TARGET)}（凳面 + 0.10）")

s0, XF = 24, 24
loopfr = []
for i in range(LOOP):
    p = S_src[s0 + i]
    if i >= LOOP - XF:
        p = blend(p, S_src[i - (LOOP - XF)], ease((i - (LOOP - XF) + 1) / (XF + 1)))
    loopfr.append(p)

# 抬头看黑板 + 两次点头（只在循环中段，首尾不受影响）
hb = TB["head.x"]
AX = (hb.matrix_local.to_3x3().inverted() @ RT["left_a"]).normalized()
LOOK_UP = -4.0      # 负 = 抬头
NODS = [(72, 9.0), (84, 7.0), (150, 8.0)]   # (中心帧, 角度)，正 = 低头


def bump(f, c, w=7.0):
    t = (f - c) / w
    return math.cos(t * math.pi / 2) ** 2 if abs(t) < 1 else 0.0


for i, fr in enumerate(loopfr):
    f = i + 1
    ang = LOOK_UP + sum(a * bump(f, c) for c, a in NODS)
    l, q = fr.get("head.x", (Vector(), Quaternion()))
    fr["head.x"] = (l, Quaternion(AX, math.radians(ang)) @ q)

# 求值期间只保留人物集合
EXCL = {}
vl = sc.view_layers["BG"] if "BG" in sc.view_layers else sc.view_layers[0]
for lc in vl.layer_collection.children:
    EXCL[lc.name] = lc.exclude
    lc.exclude = lc.name != CH.name

write_root("B5_listen", [ROOTOB.location.copy() for _ in range(LOOP)], [H] * LOOP)
act = write_rig("B5_listen", loopfr)
sc.frame_start, sc.frame_end = 1, LOOP
cloth_sim.simulate(rig, 1, LOOP, loop=True, log=log)
log("B5_listen：192 帧循环，衣摆完成")

# 检查：臀部 / 膝盖高度
for f in (1, 96):
    sc.frame_set(f)
    M = rig.matrix_world
    hip = M @ rig.pose.bones["root.x"].head
    kl = M @ rig.pose.bones["leg_stretch.l"].head
    kr = M @ rig.pose.bones["leg_stretch.r"].head
    fl = M @ rig.pose.bones["foot.l"].head
    log(f"  帧 {f}: 臀部 z={hip.z:.3f}（凳面 {SEAT_TOP:.3f}），膝盖 z={kl.z:.3f}/{kr.z:.3f}（桌裙下沿 {APRON_BOT:.3f}），脚踝 z={fl.z:.3f}（地面≈{FLOOR_Z:.3f}）")
for k, v in EXCL.items():
    vl.layer_collection.children[k].exclude = v

# ------------------------------------------------------------------ 黑板板书（classroom_anim/board_chalk.py）
_p = os.path.join(HERE, "board_chalk.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), globals())

# ------------------------------------------------------------------ 老师（classroom_anim/teacher.py）
_p = os.path.join(HERE, "teacher.py")
exec(compile(open(_p, encoding="utf-8").read(), _p, "exec"), globals())
# 伊蕾娜的 192 帧循环在 TL 帧里重复
for _a in (bpy.data.actions["CLIP_B5_listen"], bpy.data.actions["CLIPR_B5_listen"]):
    for _fc in act_fcurves(_a):
        if not any(m.type == "CYCLES" for m in _fc.modifiers):
            _fc.modifiers.new("CYCLES")

# ------------------------------------------------------------------ 侧背面近景镜头
def make_cam(name, eye, look, lens):
    d = bpy.data.cameras.new(name); d.lens = lens; d.clip_start = 0.05; d.clip_end = 100
    ob = bpy.data.objects.new(name, d); sc.collection.objects.link(ob)
    ob.location = eye
    ob.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()
    return ob


def at(right, fwd, z):
    v = SEATPOS + RIGHT * right + FWD * fwd
    v.z = FLOOR_Z + z
    return v


CAM_SB = make_cam("CAM_side_back", at(1.0, -2.2, 1.9), at(0.725, 1.73, 1.205), 26)   # 右后方近景，能看到老师和黑板
CAM_T = make_cam("CAM_teacher", RW(1.4, 0.7, 1.6), RW(-0.1, 4.3, 1.6), 28)   # 老师检查镜头

# ------------------------------------------------------------------ 保存
OUTBLEND = os.path.join(HERE, "classroom_anim.blend")
bpy.ops.wm.save_as_mainfile(filepath=OUTBLEND, copy=True)
log(f"已保存 {OUTBLEND}")

# ------------------------------------------------------------------ 可选：EEVEE 静帧看配色（GSD_STILLS=1 时只出静帧，不出白模）
if os.environ.get("GSD_STILLS"):
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 2560, 1440, 50
    sc.render.image_settings.file_format = "PNG"
    for cam, f in ((CAM_T, 50), (CAM_SB, 50), (CAM_SB, 270)):
        sc.camera = cam; sc.frame_set(f)
        sc.render.filepath = os.path.join(HERE, "check", f"eevee_{cam.name}_{f:04d}.png")
        t = time.time(); bpy.ops.render.render(write_still=True)
        log(f"EEVEE 静帧 {cam.name} 第 {f} 帧：{time.time() - t:.1f} 秒")
    log("CLASSROOM_STILLS_DONE")

# ------------------------------------------------------------------ Workbench 白模
for v in sc.view_layers:
    v.use = (v == vl)
def unexclude(lc):
    for c in lc.children:
        c.exclude = False; c.holdout = False; c.indirect_only = False
        unexclude(c)
unexclude(vl.layer_collection)
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_shadows = True; sh.show_cavity = True; sh.show_object_outline = True
sc.render.use_freestyle = False; sc.render.use_compositing = False; sc.render.film_transparent = False
try:
    sc.render.use_sequencer = False
except Exception:
    pass
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.view_settings.exposure = 0
HIDE_KEYS = ("atmos", "fog", "haze", "mist", "smoke", "sky", "cloud", "dust", "beam", "shaft", "volume", "backdrop", "godray")
hidden = 0
for o in sc.objects:
    nm = o.name.lower()
    if o.type == "MESH" and (any(k in nm for k in HIDE_KEYS) or max(o.dimensions) > 60):
        o.hide_render = True; hidden += 1
    o.color = (0.86, 0.84, 0.80, 1)
for o in CH.all_objects:
    o.color = (0.55, 0.72, 1.0, 1)
for o in TC.all_objects:
    o.color = (1.0, 0.72, 0.62, 1)
for o in BC.all_objects:
    o.color = (1.0, 1.0, 1.0, 1)
STAFF.color = (1.0, 0.85, 0.3, 1)
log(f"白模：隐藏体积 / 雾 / 光尘 {hidden} 个")
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 2560, 1440, 50
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 88
WB_PLAN = {"T1_lecture": (CAM_T,), "T2_pace": (CAM_T, CAM_SB)}
for tag, acts, n in TCLIPS:
    for ob, a in zip((TARM, T_ROOT, STAFF), acts):
        assign(ob, a)
    sc.frame_start, sc.frame_end = 1, n
    for cam in WB_PLAN.get(tag, (CAM_SB, CAM_T)):
        sc.camera = cam
        d = os.path.join(HERE, "whitebox", f"{tag}_{cam.name}"); os.makedirs(d, exist_ok=True)
        sc.render.filepath = os.path.join(d, "f_")
        t = time.time()
        bpy.ops.render.render(animation=True)
        log(f"白模 {tag} / {cam.name} 完成，{n} 帧，{(time.time() - t) / n:.2f} 秒 / 帧")
log("CLASSROOM_WB_DONE")
