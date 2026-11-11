# -*- coding: utf-8 -*-
"""探查 动作/ 文件夹里的 Mixamo FBX：骨骼名、帧范围、帧率、髋部位移 → 动作/_probe.json"""
import bpy, os, json, glob
ROOT = os.path.expanduser("~/Desktop/共生岛")
D = os.path.join(ROOT, "动作")
out = {}
for p in sorted(glob.glob(os.path.join(D, "*.fbx"))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=p, use_anim=True, automatic_bone_orientation=False, ignore_leaf_bones=True)
    rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if rig is None:
        out[os.path.basename(p)] = "no armature"
        continue
    act = rig.animation_data.action if rig.animation_data else None
    fr = tuple(act.frame_range) if act else None
    sc = bpy.context.scene
    names = [b.name for b in rig.data.bones]
    hips = next((b for b in rig.pose.bones if b.name.split(":")[-1] == "Hips"), None)
    traj = []
    if act and hips:
        for f in range(int(fr[0]), int(fr[1]) + 1, max(1, int((fr[1] - fr[0]) / 8))):
            sc.frame_set(f)
            h = rig.matrix_world @ hips.head
            traj.append([f, round(h.x, 3), round(h.y, 3), round(h.z, 3)])
    out[os.path.basename(p)] = {"bones": len(names), "sample": names[:6], "frames": fr, "fps": sc.render.fps,
                                "rig_rot": [round(v, 3) for v in rig.rotation_euler], "rig_scale": [round(v, 4) for v in rig.scale],
                                "hips_traj": traj}
json.dump(out, open(os.path.join(D, "_probe.json"), "w"), ensure_ascii=False, indent=1)
print("probe done", len(out))
