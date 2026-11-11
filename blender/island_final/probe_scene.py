import bpy, json, os, sys
from mathutils import Vector
out = {}
sc = bpy.context.scene
out["frames"] = (sc.frame_start, sc.frame_end, sc.render.fps)
out["view_layers"] = {vl.name: [c.name for c in vl.layer_collection.children] for vl in sc.view_layers}
out["collections"] = {c.name: len(c.all_objects) for c in bpy.data.collections}
def bb(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [[round(min(p[i] for p in pts), 3) for i in range(3)], [round(max(p[i] for p in pts), 3) for i in range(3)]]
keys = ("campfire", "dock", "planter", "house_door", "house_porch", "porch", "stairs", "picnic", "terrain", "island", "ground", "CHAR", "path_", "boat", "duck", "lamp", "fence", "bench", "table", "stump", "bird")
objs = {}
for o in bpy.data.objects:
    if any(k in o.name for k in keys):
        try:
            objs[o.name] = {"type": o.type, "loc": [round(v, 3) for v in o.matrix_world.translation], "bb": bb(o) if o.type == "MESH" else None,
                            "parent": o.parent.name if o.parent else None, "colls": [c.name for c in o.users_collection]}
        except Exception as e:
            objs[o.name] = str(e)
out["objs"] = objs
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
out["rig"] = {"name": rig.name, "parent": rig.parent.name if rig.parent else None, "mw": [list(r) for r in rig.matrix_world],
              "action": rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None}
sc.frame_set(1)
pb = rig.pose.bones
out["bones_w"] = {n: [round(v, 3) for v in rig.matrix_world @ pb[n].head] for n in ("root.x", "spine_01.x", "head.x", "foot.l", "foot.r", "toes_01.l", "thigh_stretch.l", "leg_stretch.l") if n in pb}
for n in ("CHAR_root", "CHAR_fit"):
    o = bpy.data.objects.get(n)
    if o:
        out[n] = {"loc": list(o.location), "rot": list(o.rotation_euler), "scale": list(o.scale), "mw_t": list(o.matrix_world.translation),
                  "anim": bool(o.animation_data and o.animation_data.action)}
cam = sc.camera
out["camera"] = {"name": cam.name, "loc": list(cam.location), "rot": list(cam.rotation_euler), "ortho": cam.data.ortho_scale, "type": cam.data.type,
                 "shift": [cam.data.shift_x, cam.data.shift_y], "res": [sc.render.resolution_x, sc.render.resolution_y]}
out["actions"] = [(a.name, list(a.frame_range), a.users) for a in bpy.data.actions]
# 环境动画是否 cyclic
nc = nt = 0
for idb in list(bpy.data.objects) + list(bpy.data.lights) + list(bpy.data.materials) + list(bpy.data.node_groups) + list(bpy.data.worlds):
    ad = getattr(idb, "animation_data", None)
    if ad and ad.action:
        a = ad.action
        fcs = list(a.fcurves) if hasattr(a, "fcurves") and bpy.app.version < (5, 0, 0) else [fc for l in a.layers for s in l.strips for cb in s.channelbags for fc in cb.fcurves]
        for fc in fcs:
            nt += 1
            nc += any(m.type == "CYCLES" for m in fc.modifiers)
out["fcurves_total_cyclic"] = (nt, nc)
drv = [o.name for o in bpy.data.objects if o.animation_data and o.animation_data.drivers]
out["drivers"] = drv[:20]
json.dump(out, open(os.path.join(os.path.dirname(bpy.data.filepath), "island_final", "probe.json"), "w"), ensure_ascii=False, indent=1)
print("PROBE_DONE")
