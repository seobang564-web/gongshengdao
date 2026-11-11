import bpy, json, os
out = {}
for o in bpy.data.objects:
    if o.name.startswith(("campfire_seat", "picnic_top", "dock_planks", "house_step", "campfire_rocks")):
        out[o.name] = {"hide_render": o.hide_render, "hide_viewport": o.hide_viewport, "gsd_show": o.get("gsd_show"),
                       "colls": [c.name for c in o.users_collection], "mods": [m.type for m in o.modifiers],
                       "verts": len(o.data.vertices) if o.type == "MESH" else 0, "scale": list(o.scale), "dims": list(o.dimensions)}
json.dump(out, open(os.path.join(os.path.dirname(bpy.data.filepath), "island_final", "probe2.json"), "w"), indent=1, ensure_ascii=False)
