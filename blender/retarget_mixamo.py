# -*- coding: utf-8 -*-
"""
共生岛 · 把 Mixamo 动作搬到伊蕾娜身上（重定向）+ 白模预览

用法（在 gongshengdao_v4_anim.blend 上无界面运行）：
  Blender -b gongshengdao_v4_anim.blend -P retarget_mixamo.py -- preview island
  Blender -b gongshengdao_v4_anim.blend -P retarget_mixamo.py -- preview "Happy Walk" "Waving"
输出：~/Desktop/共生岛/动作预览/<动作名>/f_####.png（之后合成 mp4）

做法：
  · 躯干、头、肩、腿、脚：把源骨骼「相对静止姿势的转动」按朝向换算后套到伊蕾娜对应骨骼上
  · 上臂、前臂、手：先把伊蕾娜的 A 字静止手臂对齐到 Mixamo 的 T 字手臂方向，再套转动（避免手插进身体）
  · 髋部位移按身高比例缩放；走路、慢跑去掉向前的位移，变成原地动作
  · 保留：眨眼、头发 / 衣摆轻摆、袖口始终下垂（抵消手臂转动）
"""
import bpy
import builtins
import math
import os
import sys
import glob
import json
import time
from mathutils import Matrix, Quaternion, Vector

ROOT = os.path.expanduser("~/Desktop/共生岛")
SRC_DIR = os.path.join(ROOT, "动作")
OUT_DIR = os.environ.get("GSD_OUT") or os.path.join(ROOT, "动作预览")
os.makedirs(OUT_DIR, exist_ok=True)
LOG = os.path.join(OUT_DIR, "log.txt")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = argv[0] if argv else "preview"
CLIPS = argv[1:] or ["island"]
ISLAND = ["Breathing Idle", "Happy Walk", "Jogging", "Arm Stretching", "Waving", "Joyful Jump", "Victory Idle",
          "Watering", "Throwing", "Sitting Idle", "Sitting_edge", "Stand To Sit", "Sit To Stand", "Thinking", "Yawn"]
INDOOR = ["Typing", "Sitting", "Lying Down", "Laying Sleeping"]
if CLIPS == ["island"]:
    CLIPS = ISLAND
elif CLIPS == ["indoor"]:
    CLIPS = INDOOR
elif CLIPS == ["all"]:
    CLIPS = ISLAND + INDOOR
IN_PLACE = {"Happy Walk", "Jogging"}
LOOP_CLIPS = {"Breathing Idle", "Happy Walk", "Jogging", "Sitting Idle", "Sitting_edge"}
USE_CLOTH = os.environ.get("GSD_CLOTH", "1") != "0"
sys.path.insert(0, os.path.join(ROOT, "blender"))
import cloth_sim

# Mixamo → 伊蕾娜；第三项：True = 先对齐静止方向（手臂），False = 只套转动
MAP = [("Hips", "root.x", False), ("Spine", "spine_01.x", False), ("Spine1", "spine_02.x", False),
       ("Spine2", "spine_03.x", False), ("Neck", "neck.x", False), ("Head", "head.x", False)]
for S, s in (("Left", "l"), ("Right", "r")):
    MAP += [(f"{S}Shoulder", f"shoulder.{s}", False), (f"{S}Arm", f"arm_stretch.{s}", True),
            (f"{S}ForeArm", f"forearm_stretch.{s}", True), (f"{S}Hand", f"hand.{s}", "parent"),
            (f"{S}UpLeg", f"thigh_stretch.{s}", False), (f"{S}Leg", f"leg_stretch.{s}", False),
            (f"{S}Foot", f"foot.{s}", False), (f"{S}ToeBase", f"toes_01.{s}", False)]


def log(m):
    print(m)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def basis(up, left):
    up = up.normalized()
    left = (left - up * left.dot(up)).normalized()
    front = left.cross(up).normalized()
    return Matrix((left, up, front)).transposed()      # 列向量：左、上、前


# ------------------------------------------------------------
# 目标：伊蕾娜
# ------------------------------------------------------------
sc = bpy.context.scene
rig = next(o for o in bpy.data.collections["CHAR_人物"].all_objects if o.type == "ARMATURE")
W = rig.matrix_world.copy()
Wq = W.to_quaternion()
W3i = W.to_3x3().inverted()
TB = rig.data.bones
R = {b.name: b.matrix_local.to_quaternion() for b in TB}
tw = lambda n: W @ TB[n].head_local
T_basis = basis(tw("neck.x") - tw("root.x"), tw("arm_stretch.l") - tw("arm_stretch.r"))
# 伊蕾娜骨架空间里的上 / 左 / 前（给眨眼、头发、袖口用）
up_a = (TB["neck.x"].head_local - TB["root.x"].head_local).normalized()
left_a = TB["arm_stretch.l"].head_local - TB["arm_stretch.r"].head_local
left_a = (left_a - up_a * left_a.dot(up_a)).normalized()
front_a = left_a.cross(up_a).normalized()
down_a = (W3i @ Vector((0, 0, -1))).normalized()
t_hip_h = (tw("root.x") - (tw("foot.l") + tw("foot.r")) / 2).z

mapped = {t for _, t, _ in MAP if t in TB}
hair_roots = [b.name for b in TB if b.name.startswith("Bone") and b.parent and b.parent.name == "head.x"]
sleeve_roots = {s: [b.name for b in TB if b.name.startswith("Bone") and b.parent and b.parent.name == f"forearm_twist.{s}"]
                for s in ("l", "r")}
sleeve_set = {n for v in sleeve_roots.values() for n in v}
cloth_roots = [b.name for b in TB if b.name.startswith("Bone") and b.parent and not b.parent.name.startswith("Bone")
               and b.parent.name != "head.x" and b.name not in sleeve_set]
second = {b.name: b.parent.name for b in TB if b.name.startswith("Bone") and b.parent and b.parent.name.startswith("Bone")
          and (b.parent.name in hair_roots or b.parent.name in cloth_roots or b.parent.name in sleeve_set)}


def delta_of(name, D):
    """骨骼在骨架空间里相对静止姿势的总转动：未驱动的骨骼继承父级"""
    b = TB[name]
    while b is not None and b.name not in D:
        b = b.parent
    return D[b.name] if b is not None else Quaternion()


def key_local(name, L, f, prev):
    pb = rig.pose.bones[name]
    if name in prev:
        L.make_compatible(prev[name])
    prev[name] = L.copy()
    pb.rotation_quaternion = L
    pb.keyframe_insert("rotation_quaternion", frame=f, group=name)


def set_from_delta(name, D, f, prev):
    """已知该骨骼的总转动 D[name]，换算成相对父级的本地转动并打帧"""
    par = TB[name].parent
    Dp = delta_of(par.name, D) if par is not None else Quaternion()
    Rb = R[name]
    key_local(name, Rb.inverted() @ Dp.inverted() @ D[name] @ Rb, f, prev)


def set_relative(name, A, f, prev, D):
    """A：相对父级的转动（骨架空间表达），同时记下总转动"""
    par = TB[name].parent
    Dp = delta_of(par.name, D) if par is not None else Quaternion()
    D[name] = Dp @ A
    Rb = R[name]
    key_local(name, Rb.inverted() @ A @ Rb, f, prev)


def blink(f):
    a = 0.0
    for bf in (40, 118, 125, 200, 290, 297, 380):
        d = f - bf
        if -3 <= d <= 0:
            a = max(a, 1 + d / 3.0)
        elif 0 < d <= 5:
            a = max(a, 1 - d / 5.0)
    return a


# ------------------------------------------------------------
# 一个动作
# ------------------------------------------------------------

LAST = {}


def retarget(clip, in_place=None):
    path = os.path.join(SRC_DIR, clip + ".fbx")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, automatic_bone_orientation=False, ignore_leaf_bones=True)
    new = [o for o in bpy.data.objects if o not in before]
    src_scene = bpy.data.scenes.get("MX_SRC") or bpy.data.scenes.new("MX_SRC")
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        src_scene.collection.objects.link(o)
    src = next(o for o in new if o.type == "ARMATURE")
    act = src.animation_data.action
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    dg = src_scene.view_layers[0].depsgraph
    sb = {b.name.split(":")[-1]: b for b in src.data.bones}
    Ms = src.matrix_world.copy()
    Ms3 = Ms.to_3x3()
    sw = lambda n: Ms @ sb[n].head_local
    F = (T_basis @ basis(sw("Neck") - sw("Hips"), sw("LeftArm") - sw("RightArm")).transposed()).to_quaternion()
    Fi = F.inverted()
    S_rest = {k: (Ms @ b.matrix_local).to_quaternion() for k, b in sb.items()}
    # 手臂：先把伊蕾娜的静止方向对齐到 Mixamo
    A = {}
    for s_name, t_name, align in MAP:
        if t_name not in TB or s_name not in sb:
            continue
        if align is True:
            sd = (Ms3 @ (sb[s_name].tail_local - sb[s_name].head_local)).normalized()
            td = (W.to_3x3() @ (TB[t_name].tail_local - TB[t_name].head_local)).normalized()
            A[t_name] = td.rotation_difference(F @ sd)
        elif align == "parent":
            A[t_name] = None        # 用前臂的对齐
        else:
            A[t_name] = Quaternion()
    for s in ("l", "r"):
        if f"hand.{s}" in A:
            A[f"hand.{s}"] = A.get(f"forearm_stretch.{s}", Quaternion())
    s_hip_h = (sw("Hips") - (sw("LeftFoot") + sw("RightFoot")) / 2).z
    k = t_hip_h / max(s_hip_h, 1e-4)
    hips_rest = sw("Hips")
    # 清空伊蕾娜旧动画
    LAST.clear()
    LAST["k"] = k
    rig.animation_data_clear()
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new("MX_" + clip)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    root_R3 = R["root.x"].to_matrix()
    prev = {}
    first_xy = last_xy = None
    samples = []
    for f in range(f0, f1 + 1):
        src_scene.frame_set(f)
        dg = src_scene.view_layers[0].depsgraph or bpy.context.evaluated_depsgraph_get()
        if src_scene.view_layers[0].depsgraph is None:
            src_scene.view_layers[0].update()
            dg = src_scene.view_layers[0].depsgraph
        ev = src.evaluated_get(dg)
        samples.append((f, {p_.name.split(":")[-1]: (Ms @ p_.matrix).to_quaternion() for p_ in ev.pose.bones},
                        (Ms @ ev.pose.bones[sb["Hips"].name].head).copy()))
    first_xy = samples[0][2]
    last_xy = samples[-1][2]
    LAST["drift"] = (F @ ((last_xy - first_xy) * k)).copy()
    LAST["n"] = len(samples)
    n = len(samples)
    for i, (f, Sp, hip) in enumerate(samples):
        fi = i + 1
        D = {}
        for s_name, t_name, _ in MAP:
            if t_name not in TB or s_name not in Sp:
                continue
            Dsrc = Sp[s_name] @ S_rest[s_name].inverted()
            Dt = F @ Dsrc @ Fi
            D[t_name] = Wq.inverted() @ Dt @ A[t_name] @ Wq
        # 父级在前：按层级顺序打帧
        for s_name, t_name, _ in MAP:
            if t_name in D:
                set_from_delta(t_name, D, fi, prev)
        # 髋部位移
        d = hip - hips_rest
        if (clip in IN_PLACE) if in_place is None else in_place:
            # 原地化：去掉整体向前的漂移，只保留左右晃动和上下起伏
            t = i / max(n - 1, 1)
            hx = hip.x - first_xy.x - (last_xy.x - first_xy.x) * t
            hy = hip.y - first_xy.y - (last_xy.y - first_xy.y) * t
            d = Vector((hx, hy, hip.z - hips_rest.z))
        LAST.setdefault("hip", []).append((F @ (d * k)).copy())
        v = root_R3.transposed() @ (W3i @ (F @ (d * k)))
        pr = rig.pose.bones["root.x"]
        pr.location = v
        pr.keyframe_insert("location", frame=fi, group="root.x")
        # 袖口始终下垂
        tt = fi / 24.0
        for s, sgn in (("l", 1), ("r", -1)):
            Df = delta_of(f"forearm_twist.{s}", D)
            for j, nme in enumerate(sleeve_roots[s]):
                bv = (TB[nme].tail_local - TB[nme].head_local).normalized()
                want = (down_a + front_a * (0.10 + 0.05 * math.sin(tt * 0.8 + j)) + left_a * sgn * 0.06).normalized()
                D[nme] = bv.rotation_difference(want)
                set_from_delta(nme, D, fi, prev)
        # 眨眼
        bk = blink(fi)
        for s in ("l", "r"):
            for nm, deg in ((f"eyelid_top.{s}", 30.0 * bk), (f"eyelid_bot.{s}", -7.0 * bk)):
                if nm in TB:
                    set_relative(nm, Quaternion(left_a, math.radians(deg)), fi, prev, D)
        # 头发、衣摆轻摆
        for j, nme in enumerate(hair_roots):
            set_relative(nme, Quaternion(left_a, math.radians(2.0 * math.sin(tt * 1.6 + j * 0.7))) @
                         Quaternion(front_a, math.radians(1.5 * math.sin(tt * 0.8 + j * 0.7))), fi, prev, D)
        for j, nme in enumerate(cloth_roots):
            set_relative(nme, Quaternion(left_a, math.radians(1.4 * math.sin(tt * 0.8 + j * 1.1))) @
                         Quaternion(front_a, math.radians(1.0 * math.sin(tt * 1.6 + j * 1.1))), fi, prev, D)
        for j, (nme, par) in enumerate(second.items()):
            set_relative(nme, Quaternion(left_a, math.radians(1.6 * math.sin(tt * 1.6 + j * 0.9 + 0.8))), fi, prev, D)
    # 删掉源骨架
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    sc.frame_start, sc.frame_end = 1, n
    return n


# ------------------------------------------------------------
# 白模预览：只渲人物 + 一块地面，灰色 Workbench
# ------------------------------------------------------------

def setup_preview():
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "SINGLE"
    sh.single_color = (0.82, 0.82, 0.84)
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    sh.show_shadows = True
    sc.render.use_freestyle = False
    sc.render.use_compositing = False
    sc.render.film_transparent = False
    sc.render.resolution_x, sc.render.resolution_y = 720, 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    try:
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.exposure = 0.0
    except Exception:
        pass
    w = sc.world
    if w and w.node_tree:
        bgn = w.node_tree.nodes.get("Background")
        if bgn:
            bgn.inputs["Color"].default_value = (0.25, 0.28, 0.33, 1)
    vl = sc.view_layers["BG"]
    for c in vl.layer_collection.children:
        c.exclude = c.name not in ("CHAR_人物",)
    for v in sc.view_layers:
        v.use = v.name == "BG"
    cx, cy, cz = builtins.GSD_CHAR_POS
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=1.6, segments=48)
    me = bpy.data.meshes.new("preview_ground")
    bm.to_mesh(me)
    g = bpy.data.objects.new("preview_ground", me)
    g.location = (cx, cy, cz)
    sc.collection.objects.link(g)
    main = sc.camera
    fwd = (main.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    flat = Vector((fwd.x, fwd.y, 0)).normalized()
    center = Vector((cx, cy, cz + 0.75))
    cd = bpy.data.cameras.new("CAM_preview")
    cd.lens = 40
    cam = bpy.data.objects.new("CAM_preview", cd)
    sc.collection.objects.link(cam)
    cam.location = center - flat * 4.4 + Vector((0, 0, 1.3))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam


def preview_main():
    open(LOG, "w", encoding="utf-8").write("")
    t0 = time.time()
    gsd_ns = {"__name__": "__main__", "GSD_ATTACH": True}
    p = os.path.join(ROOT, "blender", "gongshengdao_scene_v4.py")
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), gsd_ns)
    setup_preview()
    info = {}
    for clip in CLIPS:
        try:
            t1 = time.time()
            n = retarget(clip)
            if USE_CLOTH:
                cloth_sim.simulate(rig, 1, n, loop=clip in LOOP_CLIPS, log=log)
            d = os.path.join(OUT_DIR, clip.replace(" ", "_"))
            os.makedirs(d, exist_ok=True)
            sc.render.filepath = os.path.join(d, "f_")
            bpy.ops.render.render(animation=True, layer="BG")
            info[clip] = n
            log(f"[共生岛] {clip}: {n} 帧，重定向 + 渲染 {time.time() - t1:.0f} 秒")
        except Exception:
            import traceback
            log(f"[共生岛] {clip} 出错：\n" + traceback.format_exc())
    json.dump(info, open(os.path.join(OUT_DIR, "clips.json"), "w"), ensure_ascii=False, indent=1)
    log(f"[共生岛] 全部完成 {time.time() - t0:.0f} 秒")


# lib 模式：只提供 retarget() 等函数，给 island_final/build_clips.py 调用
if MODE != "lib":
    preview_main()
