# -*- coding: utf-8 -*-
"""
共生岛 v4 · 一条命令搭场景并渲染预览（不开界面，省内存）

终端里运行（时段 night/morning/noon/all，分辨率百分比）：
  /Applications/Blender.app/Contents/MacOS/Blender -b -P ~/Desktop/共生岛/blender/preview_v4.py -- night 50

输出：
  ~/Desktop/共生岛/blender/render/v4_night.png      预览图
  ~/Desktop/共生岛/blender/gongshengdao_scene_v4.blend   搭好的场景（之后做动画、云渲染用）
  ~/Desktop/共生岛/blender/render/v4_log.txt        出错时看这里
"""
import bpy
import builtins
import os
import sys
import time
import traceback

ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TIME = argv[0] if len(argv) > 0 else "night"
SCALE = int(argv[1]) if len(argv) > 1 else 50
os.makedirs(os.path.join(ROOT, "render"), exist_ok=True)
LOG = os.path.join(ROOT, "render", "v4_log.txt")


def log(msg):
    print(msg)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


open(LOG, "w", encoding="utf-8").write(f"Blender {bpy.app.version_string}\n")
t0 = time.time()
try:
    p = os.path.join(ROOT, "gongshengdao_scene_v4.py")
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), {"__name__": "__main__"})
    log(f"[共生岛] 场景搭好，用时 {time.time() - t0:.0f} 秒，物体 {len(bpy.data.objects)} 个")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "gongshengdao_scene_v4.blend"))
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 32
    sc.render.resolution_percentage = SCALE
    kids = sc.view_layers["BG"].layer_collection.children
    kids["CHAR_人物"].exclude = False
    kids["FG_前景遮挡"].exclude = False
    for t in (("morning", "noon", "night") if TIME == "all" else (TIME,)):
        t1 = time.time()
        builtins.gsd.apply_time(t)
        sc.render.film_transparent = False
        sc.render.use_compositing = True
        sc.render.filepath = os.path.join(ROOT, "render", f"v4_{t}.png")
        bpy.ops.render.render(write_still=True, layer="BG")
        log(f"[共生岛] 已输出 {sc.render.filepath}，渲染 {time.time() - t1:.0f} 秒")
except Exception:
    log(traceback.format_exc())
    raise
