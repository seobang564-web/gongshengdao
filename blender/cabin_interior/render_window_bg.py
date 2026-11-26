# -*- coding: utf-8 -*-
"""
共生岛 · 木屋室内 · 窗外岛屿背景板（2026-11-25）
================================================
在岛屿成品场景里藏起木屋外壳（墙 / 屋顶 / 门窗 / 常春藤）和人物，站在屋子正中、眼睛高度，
朝「正门方向」（岛屿 −y，对应室内北墙 = 正面）和「西山墙方向」（岛屿 −x，对应室内东墙）各拍一张广角图。
室内脚本把这两张图贴在窗外远处的背景板上（cabin_whitebox.py → build_window_backdrops）。

运行（Mac，无界面）：
  Blender -b ~/Desktop/共生岛/blender/island_final/island_night.blend -P blender/cabin_interior/render_window_bg.py -- --tag night [--pct 50] [--samples 32] [--views front,west]
输出：blender/cabin_interior/backdrop/island_<tag>_<view>.png

坐标换算（室内 → 岛屿）：岛屿 x = XC − 室内 x，岛屿 y = YC − 室内 y，岛屿 z = 室内 z + Z0（绕竖直轴转 180°）。
"""
import bpy, os, sys, math, time
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "backdrop")
os.makedirs(OUT, exist_ok=True)
TAG = arg("--tag", "night")
PCT = int(arg("--pct", "50"))
SAMPLES = int(arg("--samples", "32"))
VIEWS = [v for v in arg("--views", "front,west").split(",") if v]

XC, YC, Z0 = -4.62, 6.55, 0.85          # 岛屿木屋墙体中心、室内地板高度
EYE = 1.25                               # 视点高度（室内）
FOV = 110.0                              # 水平视角
RES = (2400, 1350)
SHELL = ("house_wall", "house_roof", "house_ridge", "house_gable", "house_win", "house_door", "house_beams", "house_fascia",
         "house_ivy", "house_chimney", "house_smoke", "house_floor", "house_hang", "house_wall_lamp", "house_cat")

sc = bpy.context.scene
n_hide = 0
for o in bpy.data.objects:
    base = o.name.split(".")[0]
    if base.startswith(SHELL):
        o.hide_render = True
        n_hide += 1
ch = bpy.data.collections.get("CHAR_人物")
if ch:
    ch.hide_render = True
for vl in sc.view_layers:
    vl.use = vl.name == "BG"
print(f"[backdrop] 藏起木屋外壳 {n_hide} 个物体；只渲 BG 层", flush=True)

cd = bpy.data.cameras.new("CAM_window_bg")
cd.type = "PERSP"
cd.sensor_fit = "HORIZONTAL"
cd.angle = math.radians(FOV)
cd.clip_start, cd.clip_end = 0.05, 400
cam = bpy.data.objects.new("CAM_window_bg", cd)
sc.collection.objects.link(cam)
sc.camera = cam
r = sc.render
r.resolution_x, r.resolution_y, r.resolution_percentage = RES[0], RES[1], PCT
r.use_border = False
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGB"
r.film_transparent = False
r.use_freestyle = False                  # 岛屿工程里还开着 Freestyle（成品已改反转外壳），背景板不需要，关掉省 3/4 时间
try:
    sc.eevee.taa_render_samples = SAMPLES
except Exception:
    pass
eye = Vector((XC, YC, Z0 + EYE))
DIRS = {"front": Vector((0, -1, 0)), "west": Vector((-1, 0, 0))}
for v in VIEWS:
    cam.location = eye
    cam.rotation_euler = DIRS[v].to_track_quat("-Z", "Y").to_euler()
    sc.frame_set(1)
    r.filepath = os.path.join(OUT, f"island_{TAG}_{v}.png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[backdrop] {os.path.basename(r.filepath)}：{time.time() - t:.1f} 秒（{PCT}%，{SAMPLES} 采样）", flush=True)
