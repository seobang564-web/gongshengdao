import bpy, os
from mathutils import Vector
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "FLAT"; sh.color_type = "MATERIAL"
for o in bpy.data.objects:
    nm = o.name.lower()
    if o.type == "MESH" and (max(o.dimensions) > 30 or any(k in nm for k in ("atmos", "sky", "cloud", "haze", "fog", "sea", "star", "moon", "far"))):
        o.hide_render = True
sc.world.color = (0.1, 0.2, 0.4)
sh.show_object_outline = True
sc.render.use_freestyle = False; sc.render.use_compositing = False
for v in sc.view_layers: v.use = v.name == "BG"
X0, X1, Y0, Y1 = -13.5, 3.5, -7.0, 8.5
cd = bpy.data.cameras.new("TOP"); cd.type = "ORTHO"; cd.ortho_scale = max(X1 - X0, Y1 - Y0)
cam = bpy.data.objects.new("TOP", cd); sc.collection.objects.link(cam)
cam.location = ((X0 + X1) / 2, (Y0 + Y1) / 2, 40); cam.rotation_euler = (0, 0, 0)
sc.camera = cam
sc.render.resolution_x = sc.render.resolution_y = 1700
sc.render.resolution_percentage = 100
# 网格线：每 1 米一根细条
mat = bpy.data.materials.new("grid"); mat.diffuse_color = (1, 0, 0, 1)
import bmesh
for i in range(int(X0), int(X1) + 1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(i, (Y0 + Y1) / 2, 3)); o = bpy.context.object
    o.scale = (0.02 if i % 5 else 0.06, Y1 - Y0, 0.01); o.data.materials.append(mat)
for j in range(int(Y0), int(Y1) + 1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((X0 + X1) / 2, j, 3)); o = bpy.context.object
    o.scale = (X1 - X0, 0.02 if j % 5 else 0.06, 0.01); o.data.materials.append(mat)
sc.render.filepath = os.path.join(os.path.dirname(bpy.data.filepath), "island_final", "top.png")
bpy.ops.render.render(write_still=True)
print("TOP_DONE")
