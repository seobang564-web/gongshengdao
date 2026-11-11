# -*- coding: utf-8 -*-
"""
不开界面、在“终端”里后台渲染（省下界面和视口占用的内存/显存）。

用法（终端里一行）：
  /Applications/Blender.app/Contents/MacOS/Blender -b ~/Desktop/共生岛/blender/gongshengdao_scene_v3.blend \
      -P ~/Desktop/共生岛/blender/render_cli.py -- morning draft 50

参数：时段 morning/noon/night/all，质量 draft/medium/final，分辨率百分比
输出：~/Desktop/共生岛/blender/render/cli_<时段>_<质量>.png
"""
import bpy
import builtins
import os
import sys

ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TIME = argv[0] if len(argv) > 0 else "morning"
QUALITY = argv[1] if len(argv) > 1 else "draft"
SCALE = int(argv[2]) if len(argv) > 2 else 50

ns = {"__name__": "__main__", "GSD_ATTACH": True}
p = os.path.join(ROOT, "gongshengdao_scene_v3.py")
exec(compile(open(p, encoding="utf-8").read(), p, "exec"), ns)
p = os.path.join(ROOT, "speed.py")
exec(compile(open(p, encoding="utf-8").read(), p, "exec"), {"__name__": "__main__"})

q = builtins.gsd_q
if QUALITY == "final":
    q.final()
elif QUALITY == "medium":
    q.final()
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 32
    for ps in bpy.data.particles:
        base = ps.get("full_count", ps.count)
        ps.count = int(base * 0.6)
else:
    q.draft()

sc = bpy.context.scene
sc.render.resolution_percentage = SCALE
times = ("morning", "noon", "night") if TIME == "all" else (TIME,)
for t in times:
    builtins.gsd.apply_time(t)
    sc.render.film_transparent = False
    sc.render.use_compositing = True
    sc.render.filepath = os.path.join(ROOT, "render", f"cli_{t}_{QUALITY}.png")
    bpy.ops.render.render(write_still=True, layer="BG")
    print("[共生岛] 已输出", sc.render.filepath)
