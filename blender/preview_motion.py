# -*- coding: utf-8 -*-
"""
本地快速预览动作：用最轻量的 Workbench 引擎出一段低清 MP4（只看动作和构图，不看光影）
  render/motion_preview.mp4（640×360，8 秒循环）
另外用草稿质量的 EEVEE 渲第 1 帧看光影：render/frame1_draft.png
"""
import bpy, os
ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
sc = bpy.context.scene
atm = bpy.data.objects.get("atmosphere")

# 1) EEVEE 草稿单帧
ee = sc.eevee
for a, v in (("taa_render_samples", 12), ("use_raytracing", False), ("volumetric_tile_size", "16"),
             ("volumetric_samples", 16), ("use_volumetric_shadows", False), ("shadow_resolution_scale", 0.5)):
    try:
        setattr(ee, a, v)
    except Exception:
        pass
sc.render.resolution_percentage = 33
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = os.path.join(ROOT, "render", "frame1_draft.png")
sc.frame_set(1)
bpy.ops.render.render(write_still=True, layer="BG")
print("[共生岛] 草稿单帧：", sc.render.filepath)

# 2) Workbench 动作预览
eng = sc.render.engine
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "MATERIAL"
sh.show_shadows = True
sh.show_cavity = True
if atm:
    atm.hide_render = True
sc.render.resolution_percentage = 25
sc.render.use_compositing = False
sc.render.image_settings.file_format = "FFMPEG"
sc.render.ffmpeg.format = "MPEG4"
sc.render.ffmpeg.codec = "H264"
sc.render.ffmpeg.constant_rate_factor = "MEDIUM"
sc.render.filepath = os.path.join(ROOT, "render", "motion_preview.mp4")
bpy.ops.render.render(animation=True, layer="BG")
print("[共生岛] 动作预览：", sc.render.filepath)
sc.render.engine = eng
if atm:
    atm.hide_render = False
