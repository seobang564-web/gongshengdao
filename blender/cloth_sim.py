# -*- coding: utf-8 -*-
"""
共生岛 · 斗篷 / 衣摆的弹簧摆动（二级动画）
  · 斗篷 6 条骨骼链都挂在 spine_01 上，原来会和上身连成一块硬板
  · 这里对每节骨骼的末端做弹簧-阻尼模拟（世界空间）：惯性滞后 + 重力 + 微风 + 腿 / 胯部碰撞
  · 循环片段先空跑一整圈再记录，首尾自然衔接；一次性片段先在第 1 帧静置 24 帧让衣摆稳定
用法：
  import cloth_sim; cloth_sim.simulate(rig, 1, n, loop=True)
"""
import bpy
import math
from mathutils import Vector, Matrix, Quaternion

# 按绕身体一圈的顺序排列：左侧 → 左后 → 后左 → 后右 → 右后 → 右侧（相邻链会互相拉平）
CAPE_ROOTS = ["Bone.075", "Bone.077", "Bone.078", "Bone.096", "Bone.093", "Bone.088"]
STIFF = (0.34, 0.24, 0.17)      # 每节骨骼往「静止形状」回弹的力度：根部硬、末端软
DAMP = 0.72                     # 速度保留比例（越大荡得越久）
GRAV = 0.0010                   # 每帧重力（米）
WIND = 0.0005                   # 微风幅度（米 / 帧），按片段长度做整周期，循环不断
R_LEG, R_HIP = 0.085, 0.14      # 腿、胯部碰撞半径（米）
MAX_DEG = (14.0, 20.0, 26.0)     # 每节骨骼相对「跟随身体的静止形状」最多偏多少度
NEIGH = 0.45                     # 和相邻链平均的比例（防止斗篷撕成一条一条）


def chains(rig, roots=CAPE_ROOTS):
    out = []
    for r in roots:
        if r not in rig.data.bones:
            continue
        c, b = [r], rig.data.bones[r]
        while b.children:
            b = b.children[0]
            c.append(b.name)
        out.append(c)
    return out


def _closest(p, a, b):
    ab = b - a
    t = (p - a).dot(ab) / max(ab.length_squared, 1e-9)
    return a + ab * max(0.0, min(1.0, t))


def simulate(rig, f0, f1, loop=False, roots=CAPE_ROOTS, log=print, pin_start=None, pin_end=None, pin_len=12):
    """pin_start / pin_end：{骨骼名: 四元数}，片段头尾 pin_len 帧内把衣摆平滑拉到这个姿势（和相邻片段严丝合缝）"""
    sc = bpy.context.scene
    CH = chains(rig, roots)
    if not CH:
        log("[衣摆] 没找到斗篷骨骼，跳过")
        return
    bones, pbs = rig.data.bones, rig.pose.bones
    frames = list(range(f0, f1 + 1))
    n = len(frames)
    # 1) 逐帧记录：斗篷父骨骼的世界矩阵 + 碰撞体
    rec = []
    for f in frames:
        sc.frame_set(f)
        Mw = rig.matrix_world.copy()
        par = {c[0]: Mw @ pbs[c[0]].parent.matrix for c in CH}
        P = lambda nm: Mw @ pbs[nm].head
        col = []
        for s in ("l", "r"):
            if f"thigh_stretch.{s}" in pbs and f"leg_stretch.{s}" in pbs and f"foot.{s}" in pbs:
                col.append((P(f"thigh_stretch.{s}"), P(f"leg_stretch.{s}"), R_LEG))
                col.append((P(f"leg_stretch.{s}"), P(f"foot.{s}"), R_LEG * 0.8))
        if "spine_02.x" in pbs:
            col.append((P("root.x"), P("spine_02.x"), R_HIP))
        rec.append((par, col))
    # 2) 模拟
    order = (list(range(n)) * 2) if loop else ([0] * 24 + list(range(n)))
    warm = n if loop else 24
    state, out = {}, {}
    for step, i in enumerate(order):
        par, col = rec[i]
        wind = Vector((WIND * math.sin(2 * math.pi * 2 * i / n), WIND * 0.6 * math.sin(2 * math.pi * 3 * i / n + 1.3), 0))
        res = {}
        Mpar = {ci: par[c[0]] for ci, c in enumerate(CH)}
        Lpar = {ci: bones[c[0]].parent.matrix_local for ci, c in enumerate(CH)}
        depth = max(len(c) for c in CH)
        for k in range(depth):
            idx = [ci for ci, c in enumerate(CH) if k < len(c)]
            tmp = {}
            for ci in idx:
                nm = CH[ci][k]
                Lk = bones[nm].matrix_local
                target = Mpar[ci] @ Lpar[ci].inverted() @ Lk
                head = target.translation.copy()
                tail_t = head + target.to_3x3() @ Vector((0, bones[nm].length, 0))
                if nm not in state:
                    state[nm] = (tail_t.copy(), tail_t.copy())
                p, pp = state[nm]
                s_ = STIFF[min(k, len(STIFF) - 1)]
                pn = p + (p - pp) * DAMP + (tail_t - p) * s_ + Vector((0, 0, -GRAV)) + wind * (k + 1)
                for a, b, r in col:
                    q = _closest(pn, a, b)
                    d = pn - q
                    if 1e-6 < d.length < r:
                        pn = q + d.normalized() * r
                tmp[ci] = (nm, Lk, target, head, tail_t, (tail_t - head).rotation_difference(pn - head), p)
            # 相邻链拉平 + 限制最大摆角
            Q = Quaternion
            for ci in idx:
                nm, Lk, target, head, tail_t, rot, p = tmp[ci]
                nb = [tmp[j][5] for j in (ci - 1, ci + 1) if j in tmp]
                if nb:
                    avg = nb[0] if len(nb) == 1 else nb[0].slerp(nb[1], 0.5)
                    rot = rot.slerp(avg, NEIGH)
                lim = math.radians(MAX_DEG[min(k, len(MAX_DEG) - 1)])
                ax, ang = rot.to_axis_angle()
                if ang > math.pi:
                    ang -= 2 * math.pi
                if abs(ang) > lim:
                    rot = Q(ax, math.copysign(lim, ang))
                L = (tail_t - head).length
                pn = head + rot @ (tail_t - head)
                state[nm] = (pn, p)
                Md = Matrix.Translation(head) @ (rot.to_matrix() @ target.to_3x3()).to_4x4()
                res[nm] = (target.inverted() @ Md).to_quaternion().normalized()
                Mpar[ci], Lpar[ci] = Md, Lk
        if step >= warm:
            out[i] = res
    # 3) 循环：末尾 12 帧往第 1 帧收拢，消掉残差
    if loop and n >= 96:
        for j in range(12):
            i = n - 12 + j
            w = (j + 1) / 13.0
            for nm in out[i]:
                out[i][nm] = out[i][nm].slerp(out[0][nm], w * w)
    # 3b) 头尾固定到相邻片段的衣摆姿势
    for pins, is_end in ((pin_start, False), (pin_end, True)):
        if not pins:
            continue
        rng = range(max(0, n - pin_len), n) if is_end else range(min(pin_len, n))
        for i in rng:
            t = (i - (n - pin_len) + 1) / pin_len if is_end else 1 - i / pin_len
            w = 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, t)))
            for nm in out[i]:
                if nm in pins:
                    q = pins[nm].copy()
                    q.make_compatible(out[i][nm])
                    out[i][nm] = out[i][nm].slerp(q, w)
    # 4) 打关键帧（覆盖原来的小幅正弦摆动）
    prev = {}
    for i in range(n):
        for nm, q in out[i].items():
            pb = pbs[nm]
            pb.rotation_mode = "QUATERNION"
            if nm in prev:
                q.make_compatible(prev[nm])
            prev[nm] = q.copy()
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=frames[i], group=nm)
    err = max((out[0][nm].rotation_difference(out[n - 1][nm]).angle for nm in out[0]), default=0)
    log(f"[衣摆] {len(CH)} 条链，{n} 帧，{'循环' if loop else '一次性'}，首尾最大角差 {math.degrees(err):.1f}°")
    return out
