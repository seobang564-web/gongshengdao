# -*- coding: utf-8 -*-
"""共生岛 · 魔法教室 · 生成 Windows 渲染文件
在 classroom_anim.blend 上无界面运行：算出每个片段的裁剪区域 → 写入片段清单（文本 clips_classroom.json）
→ 设置渲染镜头 / 分辨率 → 打包全部贴图 → 另存 winpkg_build/classroom.blend"""
import bpy, os, json, time
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "winpkg_build"); os.makedirs(PKG, exist_ok=True)
LOG = os.path.join(HERE, "pack_log.txt"); open(LOG, "w", encoding="utf-8").write("")
T0 = time.time()


def log(m):
    m = f"[{time.time() - T0:6.1f}s] {m}"; print(m, flush=True)
    open(LOG, "a", encoding="utf-8").write(m + "\n")


sc = bpy.context.scene
RX, RY = 2560, 1440
CAM = bpy.data.objects["CAM_side_back"]
sc.camera = CAM
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = RX, RY, 100
sc.render.fps = 24
sc.render.use_border = False
TC = bpy.data.collections["TEACHER_老师"]
TARM = next(o for o in TC.all_objects if o.type == "ARMATURE")
TARM.name = "TEACHER_arm"
LAYERS = {"elaina": "CHAR_人物", "teacher": "TEACHER_老师"}


def assign(ob, name):
    a = bpy.data.actions[name]
    ob.animation_data_create(); ob.animation_data.action = a
    try:
        if a.slots:
            ob.animation_data.action_slot = a.slots[0]
    except AttributeError:
        pass


def nframes(act):
    return int(round(bpy.data.actions[act].frame_range[1]))


CLIPS = [
    {"name": "B5_listen", "layer": "elaina", "loop": True, "from": "seat", "to": "seat", "pose_from": "seat", "pose_to": "seat",
     "actions": {"rig": "CLIP_B5_listen", "CHAR_root": "CLIPR_B5_listen"}, "frames": 192},
    {"name": "T1_lecture", "layer": "teacher", "loop": True, "from": "center", "to": "center", "pose_from": "stand", "pose_to": "stand",
     "actions": {"TEACHER_arm": "TEACHER_lecture", "TEACHER_root": "TEACHER_root", "TEACHER_pointer": "TEACHER_pointer"}},
    {"name": "T2_pace", "layer": "teacher", "loop": False, "from": "center", "to": "center", "pose_from": "stand", "pose_to": "stand",
     "actions": {"TEACHER_arm": "TEACHER_pace", "TEACHER_root": "TEACHER_pace_root", "TEACHER_pointer": "TEACHER_pace_pointer"}},
]
for c in CLIPS:
    if "frames" not in c:
        c["frames"] = nframes(c["actions"]["TEACHER_arm"])
    c["fade_out"] = 0

PAD = 80


def crop_for(c):
    for obn, an in c["actions"].items():
        assign(bpy.data.objects[obn], an)
    objs = [o for o in bpy.data.collections[LAYERS[c["layer"]]].all_objects if o.type == "MESH" and not o.hide_render]
    n = c["frames"]
    x0 = y0 = 1e9; x1 = y1 = -1e9
    for f in sorted(set(list(range(1, n + 1, 3)) + [n])):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        P = np.array(CAM.calc_matrix_camera(dg, x=RX, y=RY) @ CAM.matrix_world.inverted())
        for o in objs:
            ev = o.evaluated_get(dg); me = ev.to_mesh()
            if len(me.vertices):
                co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
                co = co.reshape(-1, 3)[::5]
                M = np.array(ev.matrix_world)
                w = co @ M[:3, :3].T + M[:3, 3]
                h = np.c_[w, np.ones(len(w))] @ P.T
                ok = h[:, 3] > 1e-4
                ndc = h[ok, :2] / h[ok, 3:4]
                px = (ndc[:, 0] + 1) / 2 * RX; py = (1 - ndc[:, 1]) / 2 * RY
                if len(px):
                    x0 = min(x0, px.min()); x1 = max(x1, px.max()); y0 = min(y0, py.min()); y1 = max(y1, py.max())
            ev.to_mesh_clear()
    x0 = max(0, int(x0) - PAD); y0 = max(0, int(y0) - PAD)
    x1 = min(RX, int(x1) + PAD); y1 = min(RY, int(y1) + PAD)
    w, h = x1 - x0, y1 - y0
    w -= w % 2; h -= h % 2
    return [x0, y0, w, h]


# 老师模型里设成隐形的叠加层（材质 T_hidden）：渲染看不见，但遮罩会算成人物 → 直接删掉这些面
import bmesh
for o in bpy.data.collections["TEACHER_老师"].all_objects:
    if o.type != "MESH":
        continue
    idx = [i for i, sl in enumerate(o.material_slots) if sl.material and sl.material.name.startswith("T_hidden")]
    if not idx:
        continue
    bm = bmesh.new(); bm.from_mesh(o.data)
    dead = [f for f in bm.faces if f.material_index in idx]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bm.to_mesh(o.data); bm.free(); o.data.update()
    log(f"老师网格 {o.name}：删除隐形叠加层 {len(dead)} 个面")

for c in CLIPS:
    t = time.time()
    c["crop"] = crop_for(c)
    log(f"{c['name']}（{c['layer']}）：{c['frames']} 帧，裁剪 {c['crop']}，{time.time() - t:.1f} 秒")

# 位置（世界坐标，第 1 帧）
sc.frame_set(1)
pos = {"seat": list(bpy.data.objects["CHAR_root"].matrix_world.translation)}
assign(bpy.data.objects["TEACHER_root"], "TEACHER_root"); sc.frame_set(1)
pos["center"] = list(bpy.data.objects["TEACHER_root"].matrix_world.translation)
reg = {"time": "classroom", "loop_frames": 192, "fps": 24, "resolution": [RX, RY], "camera": CAM.name,
       "layers": LAYERS, "positions": {k: [round(v, 3) for v in p] for k, p in pos.items()}, "clips": CLIPS}
txt = bpy.data.texts.get("clips_classroom.json") or bpy.data.texts.new("clips_classroom.json")
txt.clear(); txt.write(json.dumps(reg, ensure_ascii=False, indent=1))
json.dump(reg, open(os.path.join(HERE, "clips_classroom.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 默认动作：伊蕾娜听课 + 老师讲课循环
for c in CLIPS[:2]:
    for obn, an in c["actions"].items():
        assign(bpy.data.objects[obn], an)
sc.frame_start, sc.frame_end = 1, 192
sc.frame_set(1)
# 打包贴图
missing = [im.name for im in bpy.data.images if im.source == "FILE" and not im.packed_file and not os.path.exists(bpy.path.abspath(im.filepath))]
for im in list(bpy.data.images):
    if im.source != "FILE" or im.packed_file:
        continue
    if im.name in missing:
        if im.users == 0:
            bpy.data.images.remove(im)
        continue
    try:
        im.pack()
    except Exception as e:
        log(f"  打包失败 {im.name}: {e}")
packed = sum(1 for im in bpy.data.images if im.packed_file)
log(f"贴图：打包 {packed} 张，找不到 {len(missing)} 张 {missing[:10]}")
OUTB = os.path.join(PKG, "classroom.blend")
bpy.ops.wm.save_as_mainfile(filepath=OUTB, copy=True, compress=True)
log(f"已保存 {OUTB}（{os.path.getsize(OUTB) / 1e6:.1f} MB）")
log("PACK_DONE")
