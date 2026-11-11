# -*- coding: utf-8 -*-
"""共生岛 · 魔法教室。独立 bpy+bmesh 脚本，Blender 4.2+ / 5.2。
运行：blender -b -P magic_classroom.py
快速检查：blender -b -P magic_classroom.py -- --quick
仅构建：blender -b -P magic_classroom.py -- --no-render
打开 blend 后：在 Text Editor 运行内嵌脚本（已保存为 attach 模式），再在控制台
  cls.apply_time('night'); cls.set_backdrop(False)
不会导入/修改岛屿原文件，不创建人物。
"""
import bpy
import bmesh
import math
import os
import sys
import json
import time
import random
import resource
import traceback
from mathutils import Matrix, Euler, Vector
from bpy_extras.object_utils import world_to_camera_view

# ==================== 集中参数（所有颜色输入均为 sRGB） ====================
SEED = 27
RES_X, RES_Y = 2560, 1440
SAMPLES = 64
PREVIEW_PERCENT = 50
FPS, LOOP_FRAMES = 24, 192
SHOW_BACKDROP = True
RENDER_PREVIEWS = True
DEFAULT_TIME = 'morning'
CAM_AZIMUTH, CAM_ELEVATION = -28.0, 42.0
ROOM_ROTATION = -56.0  # 房间坐标旋转，保留岛屿相机的世界 az=-28，室内为右后视角
LEFT_SAFE = 0.15
DUST_COUNT = 180
BEVEL_SEGMENTS = 3
CURVE_RESOLUTION = 3
VOLUME_SAMPLES = 48
VOLUME_TILE = '8'
HAZE_MULTIPLIER = 0.20
RAYTRACE = True
MAX_TRIANGLES = 3_000_000
ROOM_W, ROOM_D = 9.0, 11.0
OUTPUT_DIR = os.path.dirname(os.path.abspath(globals().get('__file__', bpy.data.filepath or 'magic_classroom.py')))
RENDER_DIR = os.path.join(OUTPUT_DIR, 'render')
BLEND_PATH = os.path.join(OUTPUT_DIR, 'magic_classroom.blend')
LOG_PATH = os.path.join(RENDER_DIR, 'classroom_log.txt')
ARGS = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if '--quick' in ARGS:
    PREVIEW_PERCENT, SAMPLES, VOLUME_SAMPLES = 25, 24, 24
if '--no-render' in ARGS:
    RENDER_PREVIEWS = False
os.makedirs(RENDER_DIR, exist_ok=True)
TOON = None
GLOW_MATS, LIGHTS, FLOATS, FLAMES = [], [], [], []
ROOM_ROOT = None
C, M = {}, {}
START = time.perf_counter()


def log(message):
    line = '[教室 %7.2fs] %s' % (time.perf_counter()-START, message)
    print(line, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line+'\n')


def name_cls(name):
    return name if name.startswith(('cls_', 'CHAR_SPOT_', 'CAM_')) else 'cls_'+name


def new_collection(name, parent=None):
    coll=bpy.data.collections.new(name_cls(name))
    (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def attach(ob, coll, loc=(0,0,0)):
    coll.objects.link(ob)
    if ROOM_ROOT is not None:
        ob.parent=ROOM_ROOT
    ob.location=loc
    return ob


def empty(name, loc, coll):
    ob=attach(bpy.data.objects.new(name_cls(name), None),coll,loc)
    ob.empty_display_type='PLAIN_AXES'
    ob.empty_display_size=.25
    return ob


def parent_local(ob, parent):
    # 保存世界变换：场景根的整体旋转不能丢失。
    bpy.context.view_layer.update()
    world=ob.matrix_world.copy()
    ob.parent=parent
    ob.matrix_world=world


def adopt_group(root, objects):
    for ob in objects:
        if ob is not root:
            parent_local(ob,root)


def mesh_obj(name, verts, faces, mat, coll):
    me=bpy.data.meshes.new(name_cls(name)+'_mesh')
    me.from_pydata(verts,[],faces); me.update()
    ob=attach(bpy.data.objects.new(name_cls(name),me),coll)
    if mat: me.materials.append(mat)
    return ob


def from_bmesh(name,bm,mat,coll,loc=(0,0,0)):
    me=bpy.data.meshes.new(name_cls(name)+'_mesh'); bm.to_mesh(me); bm.free()
    ob=attach(bpy.data.objects.new(name_cls(name),me),coll,loc)
    if mat: me.materials.append(mat)
    return ob


def bevel(ob,width=.025):
    if width>0:
        md=ob.modifiers.new('柔和手作倒角','BEVEL'); md.width=width; md.segments=BEVEL_SEGMENTS
        md.limit_method='ANGLE'
    return ob


def box(name,loc,size,mat,coll,bevel=.025,rot=(0,0,0)):
    bm=bmesh.new(); bmesh.ops.create_cube(bm,size=1)
    for v in bm.verts:
        v.co.x*=size[0]; v.co.y*=size[1]; v.co.z*=size[2]
    ob=from_bmesh(name,bm,mat,coll,loc); ob.rotation_euler=rot
    if bevel>0:
        md=ob.modifiers.new('柔和手作倒角','BEVEL'); md.width=min(bevel,min(size)*.4); md.segments=BEVEL_SEGMENTS
    return ob


def sphere(name,loc,scale,mat,coll,segments=24,rings=12):
    bm=bmesh.new(); bmesh.ops.create_uvsphere(bm,u_segments=segments,v_segments=rings,radius=1)
    for v in bm.verts:
        for k in range(3): v.co[k]*=scale[k]
    ob=from_bmesh(name,bm,mat,coll,loc)
    for p in ob.data.polygons:p.use_smooth=True
    return ob


def cylinder(name,loc,radius,depth,mat,coll,vertices=24,rot=(0,0,0),radius2=None):
    bm=bmesh.new(); bmesh.ops.create_cone(bm,cap_ends=True,cap_tris=False,segments=vertices,
        radius1=radius,radius2=radius if radius2 is None else radius2,depth=depth)
    ob=from_bmesh(name,bm,mat,coll,loc); ob.rotation_euler=rot
    for p in ob.data.polygons:p.use_smooth=abs(p.normal.z)<.5
    bevel(ob,min(.012,radius*.1))
    return ob


def beam(name,a,b,radius,mat,coll):
    a,b=Vector(a),Vector(b);d=b-a
    ob=cylinder(name,(a+b)/2,radius,d.length,mat,coll,vertices=16)
    ob.rotation_euler=d.to_track_quat('Z','Y').to_euler()
    return ob


def tube(name,points,radius,mat,coll,cyclic=False):
    cu=bpy.data.curves.new(name_cls(name)+'_curve','CURVE'); cu.dimensions='3D'
    cu.resolution_u=8;cu.bevel_depth=radius;cu.bevel_resolution=CURVE_RESOLUTION
    sp=cu.splines.new('POLY');sp.points.add(len(points)-1)
    for p,co in zip(sp.points,points):p.co=(*co,1)
    sp.use_cyclic_u=cyclic
    ob=attach(bpy.data.objects.new(name_cls(name),cu),coll)
    if mat:cu.materials.append(mat)
    return ob


def register_float(root,amp=.08,phase=0,spin=.12):
    root['cls_float']=True;root['cls_amp']=amp;root['cls_phase']=phase;root['cls_spin']=spin
    FLOATS.append(root)


def register_flame(ob,phase=0):
    ob['cls_flame']=True;ob['cls_phase']=phase;FLAMES.append(ob)


def add_point(name,loc,rgb,powers,radius=.3,parent=None):
    ld=bpy.data.lights.new(name_cls(name),'POINT');ld.color=lin(rgb);ld.shadow_soft_size=radius
    ob=attach(bpy.data.objects.new(name_cls(name),ld),C['lights'],loc)
    if parent:parent_local(ob,parent)
    ob['cls_powers']=powers;LIGHTS.append(ob)
    return ob
