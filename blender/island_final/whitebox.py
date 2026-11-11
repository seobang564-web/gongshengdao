# 场景内白模预览：Workbench（材质色 + 阴影），每个片段按自己的裁剪区域渲染，50% 分辨率
import bpy, os, sys, json
argv = sys.argv[sys.argv.index("--") + 1:]
ONLY = set(argv[0].split(",")) if argv and argv[0] != "all" else None
sc = bpy.context.scene
reg = json.loads(bpy.data.texts["clips_island.json"].as_string())
RX, RY = reg["resolution"]
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_shadows = True; sh.show_cavity = True; sh.show_object_outline = True
sc.render.use_freestyle = False; sc.render.use_compositing = False; sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.view_settings.exposure = 0
for o in bpy.data.objects:
    nm = o.name.lower()
    if o.type == "MESH" and (any(k in nm for k in ("atmos", "fog", "haze", "mist", "smoke", "sky", "cloud")) or max(o.dimensions) > 60):
        o.hide_render = True
sc.render.resolution_percentage = 50
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 85
rig = bpy.data.objects["rig"]; ROOT = bpy.data.objects["CHAR_root"]
def assign(ob, name):
    a = bpy.data.actions[name]; ob.animation_data_create(); ob.animation_data.action = a
    try:
        ob.animation_data.action_slot = a.slots[0]
    except Exception:
        pass
base = os.path.join(os.path.dirname(bpy.data.filepath), "whitebox")
for c in reg["clips"]:
    if ONLY and c["name"] not in ONLY:
        continue
    d = os.path.join(base, c["name"]); os.makedirs(d, exist_ok=True)
    if len(os.listdir(d)) >= c["frames"]:
        continue
    assign(rig, c["rig_action"]); assign(ROOT, c["root_action"])
    x, y, w, h = c["crop"]
    r = sc.render; r.use_border = True; r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = x / RX, (x + w) / RX
    r.border_min_y, r.border_max_y = 1 - (y + h) / RY, 1 - y / RY
    sc.frame_start, sc.frame_end = 1, c["frames"]
    sc.render.filepath = os.path.join(d, "f_")
    bpy.ops.render.render(animation=True)
    print("WB_DONE", c["name"], flush=True)
print("WHITEBOX_ALL_DONE")
