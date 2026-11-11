# -*- coding: utf-8 -*-
"""
共生岛 · 8 秒无缝循环动画（24 帧/秒，第 1–192 帧，第 193 帧 = 第 1 帧）

人物（伊蕾娜模型，Auto-Rig Pro 绑定经 FBX 导出）：
  · 先把“变形骨骼”按人体结构重新连成链（FBX 导出时约束丢失，骨骼是平铺的）
  · 手臂从 T 字放下、自然下垂，前臂微屈
  · 呼吸（胸口起伏）、重心左右轻移、头部缓慢转动与轻点、两次眨眼
  · 头发、袍子、裙摆随动作轻摆
场景：
  · 海浪漂移、小溪流动、炊烟飘动、萤火虫游走、樱花瓣飘、鸭子和小船随波起伏
  · 草、花随风摆动，树叶抖动

在已搭好 v3 场景（并导入人物）的 Blender 里运行。可以重复运行，会先清掉旧动画。
"""
import bpy
import math
from mathutils import Vector, Quaternion

FPS = 24
LOOP = 192                     # 8 秒
STEP = 4                       # 每 4 帧一个关键帧（贝塞尔插值，足够平滑）
BLINKS = (50, 134, 141)        # 眨眼的帧（第二次连眨两下）
ARM_OUT_DEG = 11               # 手臂离开身体的角度
ELBOW_BEND_DEG = 14            # 肘部弯曲

TAU = 2 * math.pi


# ---------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------
def find_rig():
    coll = bpy.data.collections.get("CHAR_人物")
    for ob in (coll.all_objects if coll else bpy.data.objects):
        if ob.type == "ARMATURE":
            return ob
    raise RuntimeError("场景里找不到人物骨架，请先运行 import_character.py")


def iter_fcurves(action):
    """兼容 4.x（action.fcurves）和 5.x（分层动作）"""
    if action is None:
        return []
    try:
        return list(action.fcurves)
    except AttributeError:
        out = []
        for layer in getattr(action, "layers", []):
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    out.extend(bag.fcurves)
        return out


def clear_anim(idblock):
    if idblock is not None and idblock.animation_data:
        idblock.animation_data_clear()


def set_cyclic(idblock):
    ad = getattr(idblock, "animation_data", None)
    if not ad or not ad.action:
        return
    for fc in iter_fcurves(ad.action):
        if not any(m.type == "CYCLES" for m in fc.modifiers):
            fc.modifiers.new("CYCLES")


def set_linear(idblock):
    ad = getattr(idblock, "animation_data", None)
    if not ad or not ad.action:
        return
    for fc in iter_fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def frames():
    return range(1, LOOP + 2, STEP)


def phase(f):
    return (f - 1) / LOOP          # 0 → 1


# ---------------------------------------------------------------------
# 1. 重建骨骼链
# ---------------------------------------------------------------------
CHAIN = {
    "spine_01.x": "root.x", "spine_02.x": "spine_01.x", "spine_03.x": "spine_02.x",
    "neck.x": "spine_03.x", "head.x": "neck.x",
}
for s in ("l", "r"):
    CHAIN.update({
        f"shoulder.{s}": "spine_03.x", f"arm_stretch.{s}": f"shoulder.{s}",
        f"c_arm_twist_offset.{s}": f"arm_stretch.{s}", f"forearm_stretch.{s}": f"arm_stretch.{s}",
        f"hand.{s}": f"forearm_stretch.{s}",
        f"thigh_stretch.{s}": "root.x", f"thigh_twist.{s}": f"thigh_stretch.{s}",
        f"leg_stretch.{s}": f"thigh_stretch.{s}", f"foot.{s}": f"leg_stretch.{s}",
    })


def fix_hierarchy(rig):
    if rig.get("gsd_chain_fixed"):
        return
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    vl.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    n = 0
    for child, parent in CHAIN.items():
        if child in eb and parent in eb:
            eb[child].use_connect = False
            eb[child].parent = eb[parent]
            n += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    rig["gsd_chain_fixed"] = True
    print(f"[共生岛] 骨骼链已重建：{n} 根")


# ---------------------------------------------------------------------
# 2. 人物动画
# ---------------------------------------------------------------------
class Pose:
    def __init__(self, rig):
        self.rig = rig
        b = rig.data.bones
        self.b = b
        hd = lambda n: b[n].head_local.copy()
        self.up = (hd("neck.x") - hd("root.x")).normalized()
        self.left = (hd("arm_stretch.l") - hd("arm_stretch.r")).normalized()
        self.left = (self.left - self.up * self.left.dot(self.up)).normalized()
        self.front = self.left.cross(self.up).normalized()

    def q(self, axis, deg):
        return Quaternion(axis, math.radians(deg))

    def set(self, name, A, frame):
        """A：骨骼相对父级的旋转（在静止姿势的骨架空间里表达），换算成骨骼本地旋转并打关键帧"""
        if name not in self.rig.pose.bones:
            return
        pb = self.rig.pose.bones[name]
        pb.rotation_mode = "QUATERNION"
        R = self.b[name].matrix_local.to_quaternion()
        pb.rotation_quaternion = R.inverted() @ A @ R
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)

    def aim(self, name, target):
        bone = self.b[name]
        v = (bone.tail_local - bone.head_local).normalized()
        return v.rotation_difference(target.normalized())


def blink_amount(f):
    a = 0.0
    for bf in BLINKS:
        d = f - bf
        if -3 <= d <= 0:
            a = max(a, 1 + d / 3.0)           # 3 帧闭眼
        elif 0 < d <= 5:
            a = max(a, 1 - d / 5.0)           # 5 帧睁开
    return a


def animate_character(rig):
    clear_anim(rig)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    P = Pose(rig)
    up, left, front = P.up, P.left, P.front
    hair_roots = [b.name for b in rig.data.bones
                  if b.name.startswith("Bone") and b.parent and b.parent.name == "head.x"]
    # 袖口：挂在前臂上的布料骨骼，要抵消手臂的转动，让袖子始终往下垂
    sleeve_roots = {s: [b.name for b in rig.data.bones if b.name.startswith("Bone") and b.parent
                        and b.parent.name == f"forearm_twist.{s}"] for s in ("l", "r")}
    sleeve_set = {n for v in sleeve_roots.values() for n in v}
    cloth_roots = [b.name for b in rig.data.bones
                   if b.name.startswith("Bone") and b.parent and not b.parent.name.startswith("Bone")
                   and b.parent.name != "head.x" and b.name not in sleeve_set]
    second = {b.name: b.parent.name for b in rig.data.bones
              if b.name.startswith("Bone") and b.parent and b.parent.name.startswith("Bone")}

    key_frames = sorted(set(frames()) | {f for bf in BLINKS for f in range(bf - 4, bf + 7)})
    for f in key_frames:
        t = phase(f)
        breath = math.sin(TAU * 2 * t)                 # 4 秒一次呼吸
        sway = math.sin(TAU * t)                       # 8 秒一次重心移动
        look = math.sin(TAU * t + 0.6)
        nod = math.sin(TAU * 2 * t + 1.0)
        # 躯干
        P.set("root.x", P.q(front, 1.3 * sway), f)
        P.set("spine_01.x", P.q(front, -0.9 * sway) @ P.q(left, 0.4 * breath), f)
        P.set("spine_02.x", P.q(left, -0.9 * breath), f)
        P.set("spine_03.x", P.q(left, -0.6 * breath) @ P.q(up, 2.0 * look), f)
        P.set("neck.x", P.q(up, 3.0 * look) @ P.q(left, 1.2 * nod), f)
        P.set("head.x", P.q(up, 7.5 * look) @ P.q(left, 2.4 * nod) @ P.q(front, 4.0 - 1.8 * sway), f)   # 轻轻歪头
        # 肩、臂（.l 在角色左侧）
        for s, sgn in (("l", 1), ("r", -1)):
            side = left * sgn
            sh = P.b[f"shoulder.{s}"]
            sv = (sh.tail_local - sh.head_local)
            A_sh = P.aim(f"shoulder.{s}", sv - up * sv.length * math.tan(math.radians(4 + 0.8 * breath)))
            P.set(f"shoulder.{s}", A_sh, f)
            out = math.radians(ARM_OUT_DEG + 1.2 * breath * sgn * 0 + 0.8 * breath)
            fwd = 0.10 + 0.03 * math.sin(TAU * t + (0 if s == "l" else math.pi))
            tgt = -up * math.cos(out) + side * math.sin(out) + front * fwd
            A_arm = P.aim(f"arm_stretch.{s}", tgt)
            P.set(f"arm_stretch.{s}", A_arm, f)
            fa = P.b[f"forearm_stretch.{s}"]
            fv = (fa.tail_local - fa.head_local).normalized()
            A_fore = Quaternion(fv.cross(front).normalized(), math.radians(ELBOW_BEND_DEG + 2 * breath))
            P.set(f"forearm_stretch.{s}", A_fore, f)
            D_parent = A_sh @ A_arm @ A_fore
            for i, n in enumerate(sleeve_roots[s]):
                bv = (P.b[n].tail_local - P.b[n].head_local).normalized()
                swing = math.sin(TAU * t + i + (0 if s == "l" else 2.0))
                want = (-up + front * (0.10 + 0.05 * swing) + side * 0.06).normalized()
                P.set(n, D_parent.inverted() @ bv.rotation_difference(want), f)
            hv = (P.b[f"hand.{s}"].tail_local - P.b[f"hand.{s}"].head_local).normalized()
            P.set(f"hand.{s}", Quaternion(hv.cross(front).normalized(), math.radians(-6)) @ P.q(hv, -12 * sgn), f)
        # 眨眼：上眼睑绕眼球中心向下转，下眼睑略向上
        bk = blink_amount(f)
        for s in ("l", "r"):
            P.set(f"eyelid_top.{s}", P.q(left, 30.0 * bk), f)
            P.set(f"eyelid_bot.{s}", P.q(left, -7.0 * bk), f)
        # 头发、衣摆：根骨和第二节随动作轻摆（相位各不相同）
        for i, n in enumerate(hair_roots):
            ph = i * 0.7
            P.set(n, P.q(left, 2.2 * math.sin(TAU * 2 * t + ph)) @ P.q(front, 1.6 * math.sin(TAU * t + ph)), f)
        for i, n in enumerate(cloth_roots):
            ph = i * 1.1
            P.set(n, P.q(left, 1.4 * math.sin(TAU * t + ph)) @ P.q(front, 1.0 * math.sin(TAU * 2 * t + ph)), f)
        for i, (n, par) in enumerate(second.items()):
            if par in hair_roots or par in cloth_roots or par in sleeve_set:
                ph = i * 0.9 + 0.8
                P.set(n, P.q(left, 1.6 * math.sin(TAU * 2 * t + ph)), f)
    set_cyclic(rig)
    print(f"[共生岛] 人物动画完成：头发骨 {len(hair_roots)} 组，衣摆骨 {len(cloth_roots)} 组，袖口 {len(sleeve_set)} 组")


# ---------------------------------------------------------------------
# 3. 场景循环动画
# ---------------------------------------------------------------------
def key_loc(ob, fn):
    base = ob.location.copy()
    clear_anim(ob)
    for f in frames():
        t = phase(f)
        ob.location = base + Vector(fn(t))
        ob.keyframe_insert("location", frame=f)
    ob.location = base
    set_cyclic(ob)


def key_rot(ob, fn):
    base = ob.rotation_euler.copy()
    clear_anim(ob)
    for f in frames():
        t = phase(f)
        dx, dy, dz = fn(t)
        ob.rotation_euler = (base.x + dx, base.y + dy, base.z + dz)
        ob.keyframe_insert("rotation_euler", frame=f)
    ob.rotation_euler = base
    set_cyclic(ob)


def node_by_type(mat, typ):
    if mat is None or not mat.node_tree:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == typ), None)


def animate_environment():
    n = 0
    # 海浪：浪纹贴图沿圆周漂移（首尾相接）
    sea = bpy.data.materials.get("W_sea")
    mp = node_by_type(sea, "MAPPING")
    if mp:
        clear_anim(sea.node_tree)
        for f in frames():
            t = phase(f)
            mp.inputs["Location"].default_value = (0.8 * math.cos(TAU * t), 0.8 * math.sin(TAU * t), 0)
            mp.inputs["Location"].keyframe_insert("default_value", frame=f)
        set_cyclic(sea.node_tree); n += 1
    # 小溪：波纹相位转一整圈
    st = bpy.data.materials.get("W_stream")
    wv = node_by_type(st, "TEX_WAVE")
    if wv and "Phase Offset" in wv.inputs:
        clear_anim(st.node_tree)
        for f, v in ((1, 0.0), (LOOP + 1, -TAU * 3)):
            wv.inputs["Phase Offset"].default_value = v
            wv.inputs["Phase Offset"].keyframe_insert("default_value", frame=f)
        set_linear(st.node_tree); set_cyclic(st.node_tree); n += 1
    # 浪花：噪声随时间轻微漂移
    fm = bpy.data.materials.get("W_foam")
    nz = node_by_type(fm, "TEX_NOISE")
    if nz and "W" in nz.inputs:
        nz.noise_dimensions = "4D"
        clear_anim(fm.node_tree)
        for f in frames():
            nz.inputs["W"].default_value = 0.6 * math.sin(TAU * phase(f))
            nz.inputs["W"].keyframe_insert("default_value", frame=f)
        set_cyclic(fm.node_tree); n += 1
    ob = bpy.data.objects
    # 炊烟
    if "house_smoke" in ob:
        key_loc(ob["house_smoke"], lambda t: (0.12 * math.sin(TAU * t), 0.06 * math.sin(TAU * 2 * t), 0.08 * math.sin(TAU * t + 1))); n += 1
    # 萤火虫、飘落花瓣
    if "fireflies" in ob:
        key_loc(ob["fireflies"], lambda t: (0.35 * math.sin(TAU * t), 0.35 * math.cos(TAU * t), 0.15 * math.sin(TAU * 2 * t))); n += 1
    if "sakura_petals_air" in ob:
        key_loc(ob["sakura_petals_air"], lambda t: (0.25 * math.sin(TAU * t), 0.15 * math.sin(TAU * t + 2), -0.12 * math.sin(TAU * 2 * t))); n += 1
    if "waterfall_mist" in ob:
        key_loc(ob["waterfall_mist"], lambda t: (0, 0, 0.04 * math.sin(TAU * 4 * t))); n += 1
    # 鸭子、小船、睡莲随波
    for o in list(ob):
        nm = o.name
        if nm.startswith("duck") and not nm.endswith("ripple"):
            i = int(nm[4]) if nm[4].isdigit() else 0
            key_loc(o, lambda t, i=i: (0.06 * math.sin(TAU * t + i), 0.06 * math.cos(TAU * t + i), 0.02 * math.sin(TAU * 4 * t + i))); n += 1
        elif nm.startswith("boat_"):
            key_loc(o, lambda t: (0, 0, 0.03 * math.sin(TAU * 2 * t))); n += 1
    # 草、花随风弯；树叶、花瓣抖动（改的是实例源物体，所有实例一起动）
    for o in list(ob):
        if o.name.startswith(("inst_grass", "inst_flower")):
            md = o.modifiers.get("风") or o.modifiers.new("风", "SIMPLE_DEFORM")
            md.deform_method = "BEND"
            md.deform_axis = "Z"
            clear_anim(o)
            ph = (hash(o.name) % 100) / 100 * TAU
            for f in frames():
                t = phase(f)
                md.angle = math.radians(9 + 7 * math.sin(TAU * 3 * t + ph) + 3 * math.sin(TAU * 5 * t + ph * 2))
                md.keyframe_insert("angle", frame=f)
            set_cyclic(o); n += 1
        elif o.name.startswith(("inst_leaf", "inst_petal")):
            md = o.modifiers.get("抖") or o.modifiers.new("抖", "SIMPLE_DEFORM")
            md.deform_method = "TWIST"
            md.deform_axis = "X"
            clear_anim(o)
            ph = (hash(o.name) % 100) / 100 * TAU
            for f in frames():
                md.angle = math.radians(14 * math.sin(TAU * 6 * phase(f) + ph))
                md.keyframe_insert("angle", frame=f)
            set_cyclic(o); n += 1
    print(f"[共生岛] 场景动画完成：{n} 项")


def setup_timeline():
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, LOOP
    sc.frame_set(1)


def run():
    rig = find_rig()
    fix_hierarchy(rig)
    animate_character(rig)
    animate_environment()
    setup_timeline()
    print(f"[共生岛] 8 秒循环动画已设置：第 1–{LOOP} 帧，{FPS} 帧/秒")


run()
