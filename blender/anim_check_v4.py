# -*- coding: utf-8 -*-
"""
检查人物动画：搭好 v4 + 动画（存成 gongshengdao_v4_anim.blend），
然后只渲人物层（透明背景），全身和脸部各抽若干帧 → render/charcheck/
终端：Blender -b -P ~/Desktop/共生岛/blender/anim_check_v4.py
"""
import bpy
import builtins
import os
import time
import traceback
from mathutils import Vector

ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
OUT = os.path.join(ROOT, "render", "charcheck")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "log.txt")
FRAMES = [1, 24, 46, 49, 50, 52, 72, 96, 120, 139, 140, 168]


def log(m):
    print(m)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


open(LOG, "w", encoding="utf-8").write("")
t0 = time.time()
try:
    p = os.path.join(ROOT, "build_anim_v4.py")
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), {"__name__": "__main__"})
    log(f"搭建 + 动画完成 {time.time() - t0:.0f} 秒")
    sc = bpy.context.scene
    builtins.gsd.apply_time("noon")
    main = sc.camera
    fwd = (main.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    cx, cy, cz = builtins.GSD_CHAR_POS
    center = Vector((cx, cy, cz + 0.85))
    # 全身相机：沿主镜头方向看人物，50mm
    cd = bpy.data.cameras.new("CAM_body")
    cd.lens = 50
    body = bpy.data.objects.new("CAM_body", cd)
    sc.collection.objects.link(body)
    flat = Vector((fwd.x, fwd.y, 0)).normalized()
    body.location = center - flat * 4.6 + Vector((0, 0, 0.9))
    body.rotation_euler = (center - body.location).to_track_quat("-Z", "Y").to_euler()
    face = bpy.data.objects.get("CAM_closeup")
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = 16
    sc.render.film_transparent = True
    sc.render.use_compositing = False
    for f in FRAMES:
        sc.frame_set(f)
        for nm, cam in (("body", body), ("face", face)):
            if cam is None:
                continue
            sc.camera = cam
            sc.render.filepath = os.path.join(OUT, f"{nm}_{f:03d}.png")
            bpy.ops.render.render(write_still=True, layer="CHAR")
        log(f"帧 {f} 完成 {time.time() - t0:.0f} 秒")
    sc.camera = main
    log("全部完成")
except Exception:
    log(traceback.format_exc())
    raise
