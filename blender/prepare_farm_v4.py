# -*- coding: utf-8 -*-
"""
把 gongshengdao_v4_anim.blend 打包成 3 个云渲染文件：farm_v4_morning / farm_v4_noon / farm_v4_night .blend
  · 每个文件渲染第 1–192 帧（8 秒循环，24 帧/秒），输出 PNG 序列
  · 成品质量：光线追踪、体积雾、64 采样、2560×1440
  · 只渲 BG 视图层（含前景和人物）
  · 夜晚版本给灯笼加上轻微闪烁
  · 贴图全部打包进 .blend
用法（终端）：
  "/Applications/Blender 4.5.app/Contents/MacOS/Blender" -b ~/Desktop/共生岛/blender/gongshengdao_v4_anim.blend \
      -P ~/Desktop/共生岛/blender/prepare_farm.py
"""
import bpy
import builtins
import os

ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
ns = {"__name__": "__main__", "GSD_ATTACH": True}
p = os.path.join(ROOT, "gongshengdao_scene_v4.py")
exec(compile(open(p, encoding="utf-8").read(), p, "exec"), ns)
gsd = builtins.gsd
sc = bpy.context.scene

ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("shadow_ray_count", 2),
                  ("shadow_step_count", 10), ("shadow_resolution_scale", 1.0), ("shadow_pool_size", "1024"),
                  ("volumetric_tile_size", "8"), ("volumetric_samples", 64), ("use_volumetric_shadows", True),
                  ("fast_gi_method", "GLOBAL_ILLUMINATION")):
    try:
        setattr(ee, attr, val)
    except Exception:
        pass
sc.render.resolution_x, sc.render.resolution_y = 2560, 1440
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.use_compositing = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.frame_start, sc.frame_end = 1, 192
for ob in bpy.data.objects:
    for md in ob.modifiers:
        if md.type == "PARTICLE_SYSTEM":
            md.show_render = True
atm = bpy.data.objects.get("atmosphere")
if atm:
    atm.hide_render = False
for vl in sc.view_layers:
    vl.use = (vl.name == "BG")
bg = sc.view_layers["BG"]
for name in ("FG_前景遮挡", "CHAR_人物", "LIGHTS_灯光"):
    lc = bg.layer_collection.children.get(name)
    if lc:
        lc.exclude = False

try:
    bpy.ops.file.pack_all()
except Exception as e:
    print("打包贴图出错：", e)
missing = [im.name for im in bpy.data.images if im.source == "FILE" and not im.packed_file]


def add_flicker():
    for ob, _ in ns["LIGHTS"]:
        # 只让灯笼、吊灯、壁灯轻微闪烁（补光、月光、窗光、篝火不加）
        if ob.data.type != "POINT" or not any(k in ob.name for k in ("lamp", "hang", "dock")) or "campfire" in ob.name:
            continue
        if ob.data.energy <= 0:
            continue
        ob.data.keyframe_insert("energy", frame=1)
        act = ob.data.animation_data.action
        try:
            fcs = list(act.fcurves)
        except AttributeError:
            fcs = [fc for l in act.layers for s in l.strips for b in s.channelbags for fc in b.fcurves]
        for fc in fcs:
            if fc.data_path == "energy":
                m = fc.modifiers.new("NOISE")
                m.scale = 3.0
                m.strength = ob.data.energy * 0.12
                m.phase = (hash(ob.name) % 100) / 10.0


for t in ("morning", "noon", "night"):
    gsd.apply_time(t)
    if t == "night":
        add_flicker()
    sc.render.filepath = f"//render/{t}/frame_"
    out = os.path.join(ROOT, f"farm_v4_{t}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True, copy=True)
    print("[共生岛] 已生成", out)
print("=" * 60)
print("[共生岛] 云渲染文件：farm_v4_morning / farm_v4_noon / farm_v4_night .blend，每个渲第 1–192 帧，引擎 EEVEE")
if missing:
    print("         注意，这些贴图没打包进去：", missing)
print("=" * 60)
