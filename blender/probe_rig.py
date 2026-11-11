# -*- coding: utf-8 -*-
"""探查人物骨架：骨骼层级、静止位置；袖口附近顶点受哪些骨骼影响 → render/charcheck/rig_probe.json"""
import bpy, json, os
from collections import defaultdict
ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "gongshengdao_v4_anim.blend"))
coll = bpy.data.collections["CHAR_人物"]
rig = next(o for o in coll.all_objects if o.type == "ARMATURE")
out = {"bones": [], "meshes": {}}
for b in rig.data.bones:
    out["bones"].append([b.name, b.parent.name if b.parent else None, [round(v, 3) for v in b.head_local],
                         [round(v, 3) for v in b.tail_local], b.use_deform])
# 手臂方向：用 arm_stretch 静止位置判断左右
bl = rig.data.bones
sl = bl["arm_stretch.l"].head_local
sr = bl["arm_stretch.r"].head_local
half = abs(sl.x - sr.x) / 2
cx = (sl.x + sr.x) / 2
for o in coll.all_objects:
    if o.type != "MESH":
        continue
    me = o.data
    names = {g.index: g.name for g in o.vertex_groups}
    infl = defaultdict(float)
    far = 0
    M = rig.matrix_world.inverted() @ o.matrix_world
    for v in me.vertices:
        p = M @ v.co
        if abs(p.x - cx) > half * 1.6:          # 比肩膀更外侧的顶点（T 姿势下的手臂、袖子）
            far += 1
            for g in v.groups:
                if g.weight > 0.05:
                    infl[names.get(g.group, "?")] += g.weight
    if far:
        top = sorted(infl.items(), key=lambda kv: -kv[1])[:25]
        out["meshes"][o.name] = {"far_verts": far, "groups": [[k, round(w, 1)] for k, w in top]}
out["arm_half"] = round(half, 3)
json.dump(out, open(os.path.join(ROOT, "render", "charcheck", "rig_probe.json"), "w"), ensure_ascii=False, indent=1)
print("probe done")
