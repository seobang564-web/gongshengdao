# -*- coding: utf-8 -*-
"""
共生岛 · 魔法教室 · 老师（MMD 骨架模型）讲课循环 TL=384 帧（16 秒，环境动画 192 帧的整 2 倍）
由 build_classroom.py exec，共享其全局（sc, log, ROOM, R3, BLD, HERE, blend, ease, ZERO, put, assign, act_fcurves, new_action）
流程：讲台右侧面向学生讲话（头部扫视）→ 走到黑板前 → 侧身用教鞭指黑板（敲两下、沿一行划过、回头看学生）→ 放下 → 走回 → 继续讲
"""
import bpy, os, math, bmesh
import numpy as np
from mathutils import Vector, Quaternion, Matrix

TL = 576
PROJ = os.path.dirname(BLD)
T_FBX = os.path.join(BLD, "characters", "teacher", "Untitled.fbx")
T_HEIGHT = 1.62
RAMP_T = 12


def RW(x, y, z):
    return ROOM.matrix_world @ Vector((x, y, z))


def RD(x, y):
    v = R3 @ Vector((x, y, 0)); v.z = 0
    return v.normalized()


def hd(v):            # 世界水平方向 → 「面朝方向」角（人物默认面朝 (sin h, −cos h)）
    return math.atan2(v.x, -v.y)


def basis_(up, left):
    up = up.normalized()
    left = (left - up * left.dot(up)).normalized()
    front = left.cross(up).normalized()
    return Matrix((left, up, front)).transposed()


# ------------------------------------------------------------------ 导入
TC = bpy.data.collections.new("TEACHER_老师"); sc.collection.children.link(TC)
T_ROOT = bpy.data.objects.new("TEACHER_root", None); TC.objects.link(T_ROOT)
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=T_FBX, use_anim=False, automatic_bone_orientation=False, ignore_leaf_bones=True)
new = [o for o in bpy.data.objects if o not in before]
for o in new:
    for c in list(o.users_collection):
        c.objects.unlink(o)
    TC.objects.link(o)
TARM = next(o for o in new if o.type == "ARMATURE")
TMESH = [o for o in new if o.type == "MESH"]
for o in new:
    if o.parent is None:
        o.parent = T_ROOT; o.matrix_parent_inverse = Matrix.Identity(4)
TARM.animation_data_clear()
for pb in TARM.pose.bones:
    pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0); pb.scale = (1, 1, 1)


# ------------------------------------------------------------------ 原创配色（模型没带贴图；不复刻原角色配色）
def lin_(rgb):
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


PALETTE = [  # (名称前缀, sRGB 颜色)；按前缀最长匹配
    ("颜", (0.98, 0.87, 0.80)), ("肌", (0.98, 0.87, 0.80)), ("足肌", (0.98, 0.87, 0.80)),
    ("髪", (0.36, 0.22, 0.17)), ("眉睫", (0.20, 0.12, 0.10)),
    ("白目", (0.98, 0.98, 0.97)), ("目", (0.22, 0.55, 0.50)),
    ("口", (0.86, 0.48, 0.48)), ("齿", (0.97, 0.96, 0.94)), ("舌", (0.90, 0.52, 0.52)),
    ("衣1", (0.16, 0.20, 0.38)), ("衣2", (0.16, 0.20, 0.38)),
    ("衣饰2", (0.86, 0.70, 0.36)), ("衣饰", (0.93, 0.89, 0.80)),
    ("手套", (0.95, 0.93, 0.88)), ("足", (0.14, 0.15, 0.24)), ("腿带", (0.86, 0.70, 0.36)),
    ("发饰", (0.86, 0.70, 0.36)), ("蝶", (0.88, 0.86, 0.95)), ("焰色", (1.0, 0.62, 0.30)),
]
HIDE_MAT = ("biaoq", "目影")
LINE_RGB = (0.16, 0.12, 0.14)
TOON = bpy.data.node_groups.get("ToonCore")


def toon_mat(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    col = (*lin_(rgb), 1)
    if TOON:
        g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = TOON
        g.inputs["Color"].default_value = col
        nt.links.new(g.outputs["Shader"], out.inputs["Surface"])
    else:
        bs = nt.nodes.new("ShaderNodeBsdfDiffuse"); bs.inputs["Color"].default_value = col
        nt.links.new(bs.outputs[0], out.inputs["Surface"])
    m.diffuse_color = col
    return m


def hidden_mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    nt.links.new(tr.outputs[0], out.inputs["Surface"])
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        m.blend_method = "HASHED"
    m.diffuse_color = (1, 1, 1, 0)
    return m


MATCACHE = {}
for o in TMESH:
    for sl in o.material_slots:
        if not sl.material:
            continue
        base = sl.material.name.split(".")[0]
        if base.endswith("+") or base.startswith(HIDE_MAT):
            key = "hide"
            m = MATCACHE.get(key) or hidden_mat("T_hidden")
        else:
            hit = max((p for p in PALETTE if base.startswith(p[0])), key=lambda p: len(p[0]), default=None)
            rgb = hit[1] if hit else (0.8, 0.8, 0.8)
            key = hit[0] if hit else "other"
            m = MATCACHE.get(key) or toon_mat("T_" + key, rgb)
        MATCACHE[key] = m
        sl.material = m
    # 反向外壳描边
    LM = MATCACHE.get("line") or bpy.data.materials.new("T_line")
    if "line" not in MATCACHE:
        LM.use_nodes = True; nt = LM.node_tree; nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*lin_(LINE_RGB), 1)
        out = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], out.inputs["Surface"])
        LM.use_backface_culling = True; LM.diffuse_color = (*lin_(LINE_RGB), 1)
        MATCACHE["line"] = LM
    o.data.materials.append(LM)
    sol = o.modifiers.new("T_outline", "SOLIDIFY")
    sol.thickness = 0.004; sol.offset = 1.0; sol.use_flip_normals = True; sol.use_rim = False
    sol.material_offset = len(o.material_slots) - 1
# 身体（肌）的上衣原本画在贴图里：锁骨以下按「未变形坐标」涂成裙子颜色 → 长袖连衣裙
bpy.context.view_layer.update()
DRESS_RGB = (0.16, 0.20, 0.38)
if "肌" in MATCACHE:
    m = MATCACHE["肌"]
    for o in TMESH:
        if not any(sl.material == m for sl in o.material_slots):
            continue
        bb = [Vector(c) for c in o.bound_box]
        zlo, zhi = min(c.z for c in bb), max(c.z for c in bb)
        neck = o.matrix_world.inverted() @ (TARM.matrix_world @ TARM.data.bones["首"].head_local)
        thr = (neck.z - 0.06 / max(o.matrix_world.to_scale().z, 1e-6) - zlo) / max(zhi - zlo, 1e-6)
        break
    nt = m.node_tree
    g = next(n for n in nt.nodes if n.type in ("GROUP", "BSDF_DIFFUSE"))
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    sp = nt.nodes.new("ShaderNodeSeparateXYZ"); sp.location = (-700, 0)
    lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = thr; lt.location = (-500, 0)
    mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.location = (-300, 0)
    mx.inputs[6].default_value = (*lin_((0.98, 0.87, 0.80)), 1)
    mx.inputs[7].default_value = (*lin_(DRESS_RGB), 1)
    nt.links.new(tc.outputs["Generated"], sp.inputs[0])
    nt.links.new(sp.outputs["Z"], lt.inputs[0])
    nt.links.new(lt.outputs[0], mx.inputs[0])
    nt.links.new(mx.outputs[2], g.inputs["Color"])
    log(f"身体上衣分界（未变形 Z 归一化）{thr:.3f}")
log(f"老师配色：{sorted(k for k in MATCACHE)}，ToonCore {'有' if TOON else '无（用漫反射代替）'}")


def zrange():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = 1e9, -1e9
    for o in TMESH:
        ev = o.evaluated_get(dg); me = ev.to_mesh(); M = ev.matrix_world
        co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        z = co @ np.array(M.row[2][:3], dtype=np.float32) + M.row[2][3]
        if len(z):
            lo = min(lo, float(z.min())); hi = max(hi, float(z.max()))
        ev.to_mesh_clear()
    return lo, hi


# 骨架原点不一定在脚下：把「センター」水平位置挪到根（T_ROOT）正下方
bpy.context.view_layer.update()
_bn = "センター" if "センター" in TARM.data.bones else TARM.data.bones[0].name
_c = TARM.matrix_world @ TARM.data.bones[_bn].head_local
log(f"老师骨架物体位置 {tuple(round(v, 3) for v in TARM.location)}，旋转 {tuple(round(math.degrees(v), 1) for v in TARM.rotation_euler)}，缩放 {tuple(round(v, 4) for v in TARM.scale)}；{_bn} 世界坐标 {tuple(round(v, 3) for v in _c)}")
for o in new:
    if o.parent == T_ROOT:
        o.location.x -= _c.x; o.location.y -= _c.y
z0, z1 = zrange()
h0 = z1 - z0
S_ = T_HEIGHT / h0 if not (1.35 < h0 < 1.95) else 1.0
T_ROOT.scale = (S_, S_, S_)
z0, z1 = zrange()
log(f"老师模型：{len(new)} 个物体，{len(TMESH)} 个网格，骨骼 {len(TARM.data.bones)}，原高 {h0:.3f} → 缩放 {S_:.4f}，现高 {z1 - z0:.3f}")

TB_ = TARM.data.bones
vgs = set(g.name for o in TMESH for g in o.vertex_groups)
with open(os.path.join(HERE, "teacher_bones.txt"), "w", encoding="utf-8") as fh:
    for b in TB_:
        fh.write(f"{b.name}\t{b.parent.name if b.parent else '-'}\t{'deform' if b.name in vgs else ''}\n")
D_ = "D" if ("足D.L" in TB_ and "足D.L" in vgs) else ""
MAPT = [("Hips", "腰", False), ("Spine", "上半身", False), ("Spine1", "上半身1", False), ("Spine2", "上半身2", False),
        ("Neck", "首", False), ("Head", "頭", False)]
FING = [("Thumb", ["親指０", "親指１", "親指２"]), ("Index", ["人指１", "人指２", "人指３"]), ("Middle", ["中指１", "中指２", "中指３"]),
        ("Ring", ["薬指１", "薬指２", "薬指３"]), ("Pinky", ["小指１", "小指２", "小指３"])]
for S, s in (("Left", "L"), ("Right", "R")):
    MAPT += [(f"{S}Shoulder", f"肩.{s}", False), (f"{S}Arm", f"腕.{s}", True), (f"{S}ForeArm", f"ひじ.{s}", True),
             (f"{S}Hand", f"手首.{s}", "parent"),
             (f"{S}UpLeg", f"足{D_}.{s}", False), (f"{S}Leg", f"ひざ{D_}.{s}", False), (f"{S}Foot", f"足首{D_}.{s}", False)]
    for fn, tl in FING:
        for i, t in enumerate(tl):
            MAPT.append((f"{S}Hand{fn}{i + 1}", f"{t}.{s}", "parent"))
missing = [t for _, t, _ in MAPT if t not in TB_]
MAPT = [m for m in MAPT if m[1] in TB_]
log(f"老师骨骼映射 {len(MAPT)} 根，腿用{'D 骨' if D_ else '普通骨'}，缺失 {missing}")
CEN = "センター" if "センター" in TB_ else MAPT[0][1]

bpy.context.view_layer.update()
WT = TARM.matrix_world.copy(); WTq = WT.to_quaternion(); W3 = WT.to_3x3(); W3i = W3.inverted()
RTq = {b.name: b.matrix_local.to_quaternion() for b in TB_}
tw = lambda n: WT @ TB_[n].head_local
T_BASIS = basis_(tw("首") - tw("腰"), tw("腕.L") - tw("腕.R"))
FRONT_W = T_BASIS.col[2].copy(); FRONT_W.z = 0; FRONT_W.normalize()
H_REST = hd(FRONT_W)
FRONT_A = (WTq.inverted() @ T_BASIS.col[2]).normalized()
UP_A = (WTq.inverted() @ Vector((0, 0, 1))).normalized()
ANK = (f"足首{D_}.L", f"足首{D_}.R")
T_HIP_H = (tw("腰") - (tw(ANK[0]) + tw(ANK[1])) / 2).z
SOLE = z0                       # 根在原点时最低点
log(f"老师静止朝向 {math.degrees(H_REST):.1f}°，髋高 {T_HIP_H:.3f}")


def t_delta(b, D):
    while b is not None and b.name not in D:
        b = b.parent
    return D[b.name] if b is not None else Quaternion()


# ------------------------------------------------------------------ Mixamo → 老师
def t_retarget(clip, in_place=False):
    path = os.path.join(PROJ, "动作", clip + ".fbx")
    bef = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, automatic_bone_orientation=False, ignore_leaf_bones=True)
    nw = [o for o in bpy.data.objects if o not in bef]
    ss = bpy.data.scenes.get("MX_T") or bpy.data.scenes.new("MX_T")
    for o in nw:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        ss.collection.objects.link(o)
    src = next(o for o in nw if o.type == "ARMATURE")
    act = src.animation_data.action
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    sb = {b.name.split(":")[-1]: b for b in src.data.bones}
    Ms = src.matrix_world.copy(); Ms3 = Ms.to_3x3()
    sw = lambda n: Ms @ sb[n].head_local
    F = (T_BASIS @ basis_(sw("Neck") - sw("Hips"), sw("LeftArm") - sw("RightArm")).transposed()).to_quaternion()
    Fi = F.inverted()
    S_rest = {k: (Ms @ b.matrix_local).to_quaternion() for k, b in sb.items()}
    A = {}
    for s_, t, al in MAPT:
        if s_ not in sb:
            continue
        if al is True:
            sd = (Ms3 @ (sb[s_].tail_local - sb[s_].head_local)).normalized()
            td = (W3 @ (TB_[t].tail_local - TB_[t].head_local)).normalized()
            A[t] = td.rotation_difference(F @ sd)
        else:
            A[t] = Quaternion()
    for s_, t, al in MAPT:
        if al == "parent":
            A[t] = A.get("ひじ." + t.split(".")[-1], Quaternion())
    s_hip_h = (sw("Hips") - (sw("LeftFoot") + sw("RightFoot")) / 2).z
    k = T_HIP_H / max(s_hip_h, 1e-4)
    hips_rest = sw("Hips")
    samples = []
    for f in range(f0, f1 + 1):
        ss.frame_set(f)
        vl_ = ss.view_layers[0]
        if vl_.depsgraph is None:
            vl_.update()
        ev = src.evaluated_get(vl_.depsgraph)
        samples.append(({p.name.split(":")[-1]: (Ms @ p.matrix).to_quaternion() for p in ev.pose.bones},
                        (Ms @ ev.pose.bones[sb["Hips"].name].head).copy()))
    first, last = samples[0][1], samples[-1][1]
    n = len(samples)
    RC = RTq[CEN].to_matrix().inverted()
    out = []
    for i, (Sp, hip) in enumerate(samples):
        D = {}
        for s_, t, _ in MAPT:
            if s_ in Sp:
                D[t] = WTq.inverted() @ (F @ (Sp[s_] @ S_rest[s_].inverted()) @ Fi) @ A[t] @ WTq
        P = {}
        for t, Dt in D.items():
            Dp = t_delta(TB_[t].parent, D)
            P[t] = (Vector(), (RTq[t].inverted() @ Dp.inverted() @ Dt @ RTq[t]).normalized())
        d = hip - hips_rest
        if in_place:
            u = i / max(n - 1, 1)
            d = Vector((hip.x - first.x - (last.x - first.x) * u, hip.y - first.y - (last.y - first.y) * u, hip.z - hips_rest.z))
        P[CEN] = (RC @ (W3i @ (F @ (d * k))), Quaternion())
        out.append(P)
    drift = F @ ((last - first) * k)
    for o in nw:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.actions.remove(act)
    bpy.data.scenes.remove(ss)
    log(f"老师重定向 {clip}：{n} 帧，k={k:.3f}，位移 {tuple(round(v, 3) for v in drift)}")
    return out, drift


IDLE_T, _ = t_retarget("Breathing Idle")
WALK_T, WDR = t_retarget("Happy Walk", in_place=True)


def leg_diff(a, b):
    return sum(a[k][1].rotation_difference(b[k][1]).angle for k in (f"足{D_}.L", f"足{D_}.R", f"ひざ{D_}.L", f"ひざ{D_}.R") if k in a and k in b)


nW = len(WALK_T)
PER = nW - 1 if leg_diff(WALK_T[0], WALK_T[nW - 1]) < 0.15 else nW
SPEED = Vector((WDR.x, WDR.y)).length / (nW - 1)
log(f"走路周期 {PER} 帧，速度 {SPEED * 24:.2f} m/s")


def concat(a, b, xf):
    return a[:-xf] + [blend(a[len(a) - xf + i], b[i], ease((i + 1) / (xf + 1))) for i in range(xf)] + b[xf:]


# 576 帧待机底子：idle[24:239] + idle[40:239] + idle[29:239]（交叉 24 帧），首尾闭合（最后 24 帧淡到 idle[0:24]，第 1 帧 = idle[24]）
IDL = concat(concat([dict(p) for p in IDLE_T[24:239]], [dict(p) for p in IDLE_T[40:239]], 24), [dict(p) for p in IDLE_T[29:239]], 24)
assert len(IDL) == TL, len(IDL)
for i in range(TL - 24, TL):
    j = i - (TL - 24)
    IDL[i] = blend(IDL[i], IDLE_T[j], ease((j + 1) / 25))

# 站姿收腿：Breathing Idle 双脚分得太开，腿部骨骼向静止姿势（双腿并拢直立）收拢
LEG_TIGHT = 0.65
LEGS = [f"{n}{D_}.{s}" for n in ("足", "ひざ", "足首") for s in ("L", "R")]
for P in IDL:
    for nm in LEGS:
        if nm in P:
            loc, q = P[nm]
            I = Quaternion(); I.make_compatible(q)
            P[nm] = (loc, q.slerp(I, LEG_TIGHT))

# 站着不左右摇摆：髋部（センター）去掉水平平移，只留一半呼吸起伏；腰 / 上身晃动压到 25%
CALM = 0.75
for P in IDL:
    if CEN in P:
        loc, q = P[CEN]
        P[CEN] = (Vector((0.0, 0.0, 0.0)) + RTq[CEN].to_matrix().inverted() @ (W3i @ Vector((0, 0, (W3 @ (RTq[CEN].to_matrix() @ loc)).z * 0.5))), q)
    for nm in ("腰", "上半身", "上半身1", "上半身2"):
        if nm in P:
            loc, q = P[nm]
            I = Quaternion(); I.make_compatible(q)
            P[nm] = (loc, q.slerp(I, CALM))

# ------------------------------------------------------------------ 位置（房间坐标）
STAGE_Z = RW(0, 0, 0.18).z
RZ = STAGE_Z - SOLE                          # 根高度：鞋底贴讲台
A_L = Vector((-0.60, 3.30))                  # 讲台正中、讲桌前
M1_L = Vector((0.45, 3.30)); M2_L = Vector((0.88, 3.68)); B_L = Vector((0.75, 4.05))
P_L = Vector((0.0, 5.12, 2.25))              # 教鞭尖指向黑板中央 UI 区域
dirP = (P_L.xy - B_L).normalized()
c, s = math.cos(math.radians(65)), math.sin(math.radians(65))
faceB = Vector((dirP.x * c - dirP.y * s, dirP.x * s + dirP.y * c))   # 侧身：黑板在右手前方 25°
H_A = hd(RD(0.0 - A_L.x, -1.5 - A_L.y))
H_B = hd(RD(faceB.x, faceB.y))


def W2(v):
    p = RW(v.x, v.y, 0); return Vector((p.x, p.y))


def chaikin_(pts, it=2):
    for _ in range(it):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [a * 0.75 + b * 0.25, a * 0.25 + b * 0.75]
        q.append(pts[-1]); pts = q
    return pts


def path_(pts, ds=0.01):
    pts = chaikin_(pts)
    seg = [(a, b, (b - a).length) for a, b in zip(pts[:-1], pts[1:])]
    L = sum(x[2] for x in seg)
    out = []; n = max(2, int(L / ds) + 1); si, acc = 0, 0.0
    for kk in range(n):
        tgt = L * kk / (n - 1)
        while si < len(seg) - 1 and acc + seg[si][2] < tgt:
            acc += seg[si][2]; si += 1
        a, b, l = seg[si]
        t = (tgt - acc) / l if l > 1e-9 else 0
        p = a.lerp(b, min(1, max(0, t)))
        tan = (b - a).normalized()
        out.append((p.x, p.y, math.atan2(tan.x, -tan.y)))
    return out, L


def ang_lerp_(a, b, w):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * w


frames = [dict(p) for p in IDL]
locs = [Vector((*W2(A_L), RZ)) for _ in range(TL)]
heads = [H_A] * TL
wwalk = [0.0] * TL


def place_walk(f0, pts, h0, h1, pace=1.0):
    samp, L = path_([W2(p) for p in pts])
    T = int(math.ceil(L / (SPEED * pace) + RAMP_T)) + 1
    vel = [min(1.0, (i + 0.5) / RAMP_T, (T - 1 - i - 0.5) / RAMP_T) for i in range(T - 1)]
    cum = [0.0]
    for v in vel:
        cum.append(cum[-1] + v)
    sc_ = L / cum[-1]
    TURN = 14
    for i in range(T):
        f = f0 + i
        dist = cum[i] * sc_
        kk = min(len(samp) - 1, int(round(dist / L * (len(samp) - 1))))
        x, y, ht = samp[kk]
        ph = (dist / SPEED) % PER
        a = int(ph); b = (a + 1) % PER
        g = blend(WALK_T[a], WALK_T[b], ph - a)
        w = ease(min(i / RAMP_T, (T - 1 - i) / RAMP_T))
        frames[f] = blend(IDL[f], g, w)
        wwalk[f] = w
        h = ht
        if i < TURN:
            h = ang_lerp_(h0, ht, ease(i / TURN))
        if T - 1 - i < TURN:
            h = ang_lerp_(h1, h, ease((T - 1 - i) / TURN))
        locs[f] = Vector((x, y, RZ)); heads[f] = h
    log(f"  走路 {f0 + 1}–{f0 + T} 帧，路程 {L:.2f} m")
    return f0 + T


W1S = 168                                   # 0 基：第 169 帧开始走
e1 = place_walk(W1S, [A_L, M1_L, M2_L, B_L], H_A, H_B)
W2S = 344
for f in range(e1, W2S):
    locs[f] = Vector((*W2(B_L), RZ)); heads[f] = H_B
e2 = place_walk(W2S, [B_L, M2_L, M1_L, A_L], H_B, H_A)
assert e2 <= TL - 30, e2
assert e2 < 412, e2

# ------------------------------------------------------------------ 姿势细节：指黑板、看黑板、扫视、握教鞭
def bump_(f, c, w):
    t = (f - c) / w
    return math.cos(t * math.pi / 2) ** 2 if abs(t) < 1 else 0.0


PA = e1 + 6; RAISE = 18; PE = W2S - 8
def wpoint(f):
    if f < PA or f > PE:
        return 0.0
    return ease(min((f - PA) / RAISE, (PE - f) / RAISE, 1.0))


def pose_mats(P):
    cache = {}
    def pm(name):
        if name in cache:
            return cache[name]
        b = TB_[name]
        loc, q = P.get(name, ZERO)
        bas = Matrix.Translation(loc) @ q.to_matrix().to_4x4()
        M = (pm(b.parent.name) @ (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local) @ bas
        cache[name] = M
        return M
    return pm


def total(pm, name):
    return pm(name).to_quaternion() @ RTq[name].inverted()


def set_total(P, pm, name, Dnew, w):
    if w <= 0:
        return
    par = TB_[name].parent
    Dp = total(pm, par.name) if par else Quaternion()
    Lnew = (RTq[name].inverted() @ Dp.inverted() @ Dnew @ RTq[name]).normalized()
    loc, q = P.get(name, ZERO)
    Lnew.make_compatible(q)
    P[name] = (loc, q.slerp(Lnew, w))


def root_mat(f):
    return (Matrix.Translation(locs[f]) @ Matrix.Rotation(heads[f] - H_REST, 4, "Z") @ Matrix.Diagonal((S_, S_, S_, 1))) @ TARM.matrix_basis


R_ARM = (TB_["腕.R"].tail_local - TB_["腕.R"].head_local).normalized()
ARM_LEN = (TB_["ひじ.R"].head_local - TB_["腕.R"].head_local).length + (TB_["手首.R"].head_local - TB_["ひじ.R"].head_local).length
HAND_DIR = (TB_["手首.R"].tail_local - TB_["手首.R"].head_local).normalized()
GRIP_OFF = 0.075 / (S_ * TARM.matrix_basis.to_scale().x)
P_dbg = []
for f in range(TL):
    P = frames[f]
    wp = wpoint(f)
    # 扫视全班（3 个整周期 / 384 帧），走路和指黑板时减弱
    yaw = math.radians(16) * math.sin(2 * math.pi * 4 * f / TL) * (1 - max(wwalk[f], wp))
    if abs(yaw) > 1e-4:
        pm = pose_mats(P)
        set_total(P, pm, "頭", Quaternion(UP_A, yaw) @ total(pm, "頭"), 1.0)
    if wp > 0:
        tap = bump_(f, PA + RAISE + 14, 4) + bump_(f, PA + RAISE + 24, 4)
        slide = -0.18 + 0.36 * ease((f - (PA + RAISE + 34)) / 40)
        Pw = RW(P_L.x + slide, P_L.y - 0.035 + 0.035 * tap, P_L.z - 0.04 * ease((f - (PA + RAISE + 34)) / 40))
        Pa = root_mat(f).inverted() @ Pw
        pm = pose_mats(P)
        Sh = pm("腕.R").translation
        u = (Pa - Sh).normalized()
        set_total(P, pm, "腕.R", R_ARM.rotation_difference(u), wp)
        for nm in ("ひじ.R", "手首.R"):
            loc, q = P.get(nm, ZERO)
            P[nm] = (loc, q.slerp(Quaternion(), wp))
        # 头看黑板，中途回头看学生
        look = wp * (1 - bump_(f, PA + RAISE + 60, 16))
        pm = pose_mats(P)
        Hh = pm("頭").translation
        v = (Pa - Hh).normalized()
        Q = FRONT_A.rotation_difference(v)
        Q = Quaternion().slerp(Q, min(1.0, math.radians(70) / max(Q.angle, 1e-6)))
        set_total(P, pm, "頭", Q, look * 0.85)
        if f == PA + RAISE + 10:
            P_dbg.append((Pa - Sh).length)
# 讲台中间讲课：左手讲解手势（前臂抬起、掌心向前），手随语气上下点
LEFT_A = TB_["腕.L"].head_local - TB_["腕.R"].head_local
LEFT_A = (LEFT_A - UP_A * LEFT_A.dot(UP_A)).normalized()
R_ARM_L = (TB_["腕.L"].tail_local - TB_["腕.L"].head_local).normalized()
R_FORE_L = (TB_["ひじ.L"].tail_local - TB_["ひじ.L"].head_local).normalized()
BEATS = [(20, 76), (100, 154), (412, 466), (488, 548)]


def wgest(f):
    w = 0.0
    for a, b in BEATS:
        if a <= f <= b:
            w = max(w, ease(min((f - a) / 14, (b - f) / 14, 1.0)))
    return w


for f in range(TL):
    w = wgest(f)
    if w <= 0:
        continue
    P = frames[f]
    pm = pose_mats(P)
    Dsp = total(pm, "上半身2")
    beat = math.sin(2 * math.pi * f / 20.0)
    d_up = Dsp @ (-UP_A * 0.85 + FRONT_A * 0.30 + LEFT_A * 0.40).normalized()
    d_fo = Dsp @ (FRONT_A * 0.80 + LEFT_A * 0.42 + UP_A * (0.22 + 0.10 * beat)).normalized()
    set_total(P, pm, "腕.L", R_ARM_L.rotation_difference(d_up), w)
    pm = pose_mats(P)
    set_total(P, pm, "ひじ.L", R_FORE_L.rotation_difference(d_fo), w)
    loc, q = P.get("手首.L", ZERO)
    P["手首.L"] = (loc, q.slerp(Quaternion(), w * 0.7))
    # 讲到重点时轻轻点头
    pm = pose_mats(P)
    set_total(P, pm, "頭", Quaternion(LEFT_A, math.radians(-5 * max(0.0, beat))) @ total(pm, "頭"), w)

# 右手握拳（握教鞭）
pm0 = pose_mats({})
hand_h = pm0("手首.R").translation
cen = pm0("上半身").translation
inward = Vector((cen.x - hand_h.x, cen.y - hand_h.y, 0)).normalized()
want = (Vector((0, 0, -1)) + inward).normalized()
i2p = (TB_["人指１.R"].head_local - TB_["小指１.R"].head_local).normalized()
palm = HAND_DIR.cross(i2p).normalized()
if palm.dot(want) < 0:
    palm = -palm
CURL = {"１": 55, "２": 75, "３": 50}
for f in range(TL):
    P = frames[f]
    for base in ("人指", "中指", "薬指", "小指"):
        for k_, ang in CURL.items():
            nm = f"{base}{k_}.R"
            if nm not in TB_:
                continue
            fd = (TB_[nm].tail_local - TB_[nm].head_local).normalized()
            ax = fd.cross(palm).normalized()
            P[nm] = (Vector(), (RTq[nm].inverted() @ Quaternion(ax, math.radians(ang)) @ RTq[nm]).normalized())

T1_FIRST = dict(frames[0])
# ------------------------------------------------------------------ 写动作
for pb in TARM.pose.bones:
    pb.rotation_mode = "QUATERNION"
ta = new_action("TEACHER_lecture")
assign(TARM, ta)
bones = sorted(set().union(*[set(fr) for fr in frames]))
for bn in bones:
    if bn not in TARM.pose.bones:
        continue
    lc = [fr.get(bn, ZERO)[0] for fr in frames]
    qs, prev = [], None
    for fr in frames:
        q = fr.get(bn, ZERO)[1].copy()
        if prev is not None:
            q.make_compatible(prev)
        prev = q; qs.append(q)
    if any(l.length > 1e-7 for l in lc):
        for i in range(3):
            put(ta, TARM, f'pose.bones["{bn}"].location', i, [l[i] for l in lc], bn)
    for i in range(4):
        put(ta, TARM, f'pose.bones["{bn}"].rotation_quaternion', i, [q[i] for q in qs], bn)
ra = new_action("TEACHER_root")
assign(T_ROOT, ra)
T_ROOT.rotation_mode = "XYZ"
un, prev = [], None
for h in heads:
    h = h - H_REST
    if prev is not None:
        while h - prev > math.pi: h -= 2 * math.pi
        while h - prev < -math.pi: h += 2 * math.pi
    un.append(h); prev = h
for i in range(3):
    put(ra, T_ROOT, "location", i, [l[i] for l in locs], "root")
for i in range(2):
    put(ra, T_ROOT, "rotation_euler", i, [0.0] * TL, "root")
put(ra, T_ROOT, "rotation_euler", 2, un, "root")

# ------------------------------------------------------------------ 教鞭（挂右手 手首.R，握点在掌心）
U_ = S_ * TARM.matrix_basis.to_scale().x          # 骨架单位 → 米
L_ST = (P_dbg[0] if P_dbg else 1.45) - ARM_LEN - GRIP_OFF
L_ST = min(1.1 / U_, max(0.6 / U_, L_ST))
me = bpy.data.meshes.new("TEACHER_pointer"); bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.012 / U_, radius2=0.007 / U_, depth=L_ST)
bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, L_ST / 2))
orb = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.022 / U_)
bmesh.ops.translate(bm, verts=orb["verts"], vec=(0, 0, L_ST))
bm.to_mesh(me); bm.free()
STAFF = bpy.data.objects.new("TEACHER_pointer", me); TC.objects.link(STAFF)
me.materials.append(toon_mat("T_pointer", (0.86, 0.70, 0.36)))
STAFF.parent = TARM; STAFF.parent_type = "BONE"; STAFF.parent_bone = "手首.R"; STAFF.matrix_parent_inverse = Matrix.Identity(4)
hb_ = TB_["手首.R"]
Pm = hb_.matrix_local @ Matrix.Translation((0, hb_.length, 0))
G = hb_.head_local + HAND_DIR * GRIP_OFF
AXS = HAND_DIR.cross(FRONT_A).normalized()
A_IDLE = math.radians(150)                    # 站着：教鞭竖握
A_WALK = math.radians(55)                     # 走路：教鞭朝前下方斜握，不戳到头发和身体
def staff_ang(f, ww, wp=0.0):
    w = ease(min(1.0, ww * 1.4))
    return (A_IDLE * (1 - w) + A_WALK * w) * (1 - wp)
# 教鞭朝向按身体坐标系给定（不跟手腕乱甩）：站着竖握、走路斜向前下、指黑板时顺着手臂
D_UP = (UP_A * 1.0 + FRONT_A * 0.18 - LEFT_A * 0.12).normalized()
D_DOWN = (-UP_A * 0.62 + FRONT_A * 0.75 - LEFT_A * 0.22).normalized()
G_LOCAL = hb_.matrix_local.inverted() @ G


def vslerp(a, b, w):
    return (Quaternion().slerp(a.rotation_difference(b), w)) @ a


def staff_basis(P, ww, wp):
    pm = pose_mats(P)
    Mh = pm("手首.R")
    grip = Mh @ G_LOCAL
    d_point = (Mh.to_quaternion() @ RTq["手首.R"].inverted()) @ HAND_DIR
    d = vslerp(D_UP, D_DOWN, ease(min(1.0, ww * 1.4)))
    d = vslerp(d, d_point, wp)
    Ms = Matrix.Translation(grip) @ Vector((0, 0, 1)).rotation_difference(d).to_matrix().to_4x4()
    return (Mh @ Matrix.Translation((0, hb_.length, 0))).inverted() @ Ms


sa = new_action("TEACHER_pointer")
assign(STAFF, sa)
STAFF.rotation_mode = "QUATERNION"
locs_s, qs_s, prev = [], [], None
for f in range(TL):
    Ms_ = staff_basis(frames[f], wwalk[f], wpoint(f))
    l, q, _ = Ms_.decompose()
    if prev is not None:
        q.make_compatible(prev)
    prev = q; locs_s.append(l); qs_s.append(q)
for i in range(3):
    put(sa, STAFF, "location", i, [l[i] for l in locs_s], "pointer")
for i in range(4):
    put(sa, STAFF, "rotation_quaternion", i, [q[i] for q in qs_s], "pointer")
for a in (ta, ra, sa):
    for fc in act_fcurves(a):
        fc.modifiers.new("CYCLES")
log(f"老师讲课循环：{TL} 帧；走到黑板 {W1S + 1}–{e1}，指黑板 {PA + 1}–{PE + 1}，走回 {W2S + 1}–{e2}；教鞭长 {L_ST * U_:.2f} m")


# =================================================================== T2_pace：讲台上来回踱步讲课（单独片段）
# 从讲台正中中立姿势（= T1_lecture 第 1 帧）开始，走到讲台左侧停下讲、走到右侧停下讲、回到正中，结束姿势同第 1 帧
LECTURE_ACTS = (ta, ra, sa)
T1_N = TL
PACE = 0.72                                   # 走得比正常慢一点（步幅不变、节奏放慢，不滑步）
L_L = Vector((-2.45, 3.35)); R_L = Vector((1.75, 3.35))
H_L = hd(RD(0.0 - L_L.x, -1.5 - L_L.y)); H_R = hd(RD(0.0 - R_L.x, -1.5 - R_L.y))
CLASS_W = RW(0.0, -1.2, 1.2)                  # 学生区中心（踱步时头朝这里）


def walk_T(pts, pace):
    _, L = path_([W2(p) for p in pts])
    return int(math.ceil(L / (SPEED * pace) + RAMP_T)) + 1


SEG = [("stand", 24), ("walk", [A_L, L_L], H_A, H_L), ("stand", 80), ("walk", [L_L, A_L, R_L], H_L, H_R), ("stand", 80),
       ("walk", [R_L, A_L], H_R, H_A), ("stand", 36)]
TP = sum(sg[1] if sg[0] == "stand" else walk_T(sg[1], PACE) for sg in SEG)


def stand_fix(seq):
    for P in seq:
        for nm in LEGS:
            if nm in P:
                loc, q = P[nm]; I = Quaternion(); I.make_compatible(q); P[nm] = (loc, q.slerp(I, LEG_TIGHT))
        if CEN in P:
            loc, q = P[CEN]
            P[CEN] = (RTq[CEN].to_matrix().inverted() @ (W3i @ Vector((0, 0, (W3 @ (RTq[CEN].to_matrix() @ loc)).z * 0.5))), q)
        for nm in ("腰", "上半身", "上半身1", "上半身2"):
            if nm in P:
                loc, q = P[nm]; I = Quaternion(); I.make_compatible(q); P[nm] = (loc, q.slerp(I, CALM))
    return seq


base = [dict(p) for p in IDLE_T[24:239]]
while len(base) < TP + 24:
    base = concat(base, [dict(p) for p in IDLE_T[40:239]], 24)
base = base[:TP]
for i in range(TP - 24, TP):
    j = i - (TP - 24)
    base[i] = blend(base[i], IDLE_T[j], ease((j + 1) / 25))
IDL = stand_fix(base)
frames = [dict(p) for p in IDL]
locs = [Vector((*W2(A_L), RZ)) for _ in range(TP)]
heads = [H_A] * TP
wwalk = [0.0] * TP
f = 0; stops = []
cur_loc, cur_h = Vector((*W2(A_L), RZ)), H_A
for sg in SEG:
    if sg[0] == "stand":
        for k in range(f, f + sg[1]):
            locs[k] = cur_loc.copy(); heads[k] = cur_h
        stops.append((f, f + sg[1]))
        f += sg[1]
    else:
        e = place_walk(f, sg[1], sg[2], sg[3], PACE)
        cur_loc = locs[e - 1].copy(); cur_h = sg[3]
        f = e
assert f == TP, (f, TP)

# 踱步时头朝学生；停下时扫视 + 讲解手势
for f in range(TP):
    P = frames[f]
    w = wwalk[f]
    pm = pose_mats(P)
    v = (root_mat(f).inverted() @ CLASS_W - pm("頭").translation).normalized()
    Q = FRONT_A.rotation_difference(v)
    Q = Quaternion().slerp(Q, min(1.0, math.radians(65) / max(Q.angle, 1e-6)))
    if w > 0:
        set_total(P, pm, "頭", Q, 0.75 * w)
    else:
        yaw = math.radians(12) * math.sin(2 * math.pi * f / 96.0)
        set_total(P, pm, "頭", Quaternion(UP_A, yaw) @ total(pm, "頭"), 1.0)
BEATS_P = [(a + 8, b - 8) for a, b in stops if b - a >= 60]
for f in range(TP):
    w = 0.0
    for a, b in BEATS_P:
        if a <= f <= b:
            w = max(w, ease(min((f - a) / 14, (b - f) / 14, 1.0)))
    if w <= 0:
        continue
    P = frames[f]
    pm = pose_mats(P)
    Dsp = total(pm, "上半身2")
    beat = math.sin(2 * math.pi * f / 20.0)
    d_up = Dsp @ (-UP_A * 0.85 + FRONT_A * 0.30 + LEFT_A * 0.40).normalized()
    d_fo = Dsp @ (FRONT_A * 0.80 + LEFT_A * 0.42 + UP_A * (0.22 + 0.10 * beat)).normalized()
    set_total(P, pm, "腕.L", R_ARM_L.rotation_difference(d_up), w)
    pm = pose_mats(P)
    set_total(P, pm, "ひじ.L", R_FORE_L.rotation_difference(d_fo), w)
    loc, q = P.get("手首.L", ZERO)
    P["手首.L"] = (loc, q.slerp(Quaternion(), w * 0.7))
for f in range(TP):
    P = frames[f]
    for base_ in ("人指", "中指", "薬指", "小指"):
        for k_, ang in CURL.items():
            nm = f"{base_}{k_}.R"
            if nm in TB_:
                fd = (TB_[nm].tail_local - TB_[nm].head_local).normalized()
                ax = fd.cross(palm).normalized()
                P[nm] = (Vector(), (RTq[nm].inverted() @ Quaternion(ax, math.radians(ang)) @ RTq[nm]).normalized())


def write_clip(tag, frames, locs, heads, n, staff_fn):
    a1 = new_action(f"TEACHER_{tag}"); assign(TARM, a1)
    for bn in sorted(set().union(*[set(fr) for fr in frames])):
        if bn not in TARM.pose.bones:
            continue
        lc = [fr.get(bn, ZERO)[0] for fr in frames]
        qs, prev = [], None
        for fr in frames:
            q = fr.get(bn, ZERO)[1].copy()
            if prev is not None:
                q.make_compatible(prev)
            prev = q; qs.append(q)
        if any(l.length > 1e-7 for l in lc):
            for i in range(3):
                put(a1, TARM, f'pose.bones["{bn}"].location', i, [l[i] for l in lc], bn)
        for i in range(4):
            put(a1, TARM, f'pose.bones["{bn}"].rotation_quaternion', i, [q[i] for q in qs], bn)
    a2 = new_action(f"TEACHER_{tag}_root"); assign(T_ROOT, a2)
    un, prev = [], None
    for h in heads:
        h = h - H_REST
        if prev is not None:
            while h - prev > math.pi: h -= 2 * math.pi
            while h - prev < -math.pi: h += 2 * math.pi
        un.append(h); prev = h
    for i in range(3):
        put(a2, T_ROOT, "location", i, [l[i] for l in locs], "root")
    for i in range(2):
        put(a2, T_ROOT, "rotation_euler", i, [0.0] * n, "root")
    put(a2, T_ROOT, "rotation_euler", 2, un, "root")
    a3 = new_action(f"TEACHER_{tag}_pointer"); assign(STAFF, a3)
    ls_, qs_, prev = [], [], None
    for f in range(n):
        Ms_ = staff_fn(f)
        l, q, _ = Ms_.decompose()
        if prev is not None:
            q.make_compatible(prev)
        prev = q; ls_.append(l); qs_.append(q)
    for i in range(3):
        put(a3, STAFF, "location", i, [l[i] for l in ls_], "pointer")
    for i in range(4):
        put(a3, STAFF, "rotation_quaternion", i, [q[i] for q in qs_], "pointer")
    return a1, a2, a3


PACE_ACTS = write_clip("pace", frames, locs, heads, TP, lambda f: staff_basis(frames[f], wwalk[f], 0.0))
# 首尾和 T1_lecture 第 1 帧的姿势差（中立衔接检查）
def pose_gap(Pa, Pb):
    return max((Pa.get(k, ZERO)[1].rotation_difference(Pb.get(k, ZERO)[1]).angle for k in set(Pa) | set(Pb)), default=0.0)
log(f"T2_pace：{TP} 帧（踱步 3 段、停下讲 2 次）；与讲课循环第 1 帧的姿势差：开头 {math.degrees(pose_gap(frames[0], T1_FIRST)):.2f}°")
TCLIPS = [("T1_lecture", LECTURE_ACTS, T1_N), ("T2_pace", PACE_ACTS, TP)]
for ob, a in zip((TARM, T_ROOT, STAFF), LECTURE_ACTS):
    assign(ob, a)
