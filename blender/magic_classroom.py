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


# 原 v3 材质函数复用；Toon 色带输入统一作 sRGB 转换。
def lin(rgb):
    """sRGB(屏幕上看到的颜色) → 线性值（Blender 材质颜色按线性解释）"""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)

def build_toon_group():
    """输出 = 底色 × (阶梯明暗 × 时段色调 × 0.78 + 实际光照颜色 × 0.32)
    阶梯明暗给出卡通分层；实际光照颜色让灯笼、窗户的暖光能染到地面上。"""
    ng = bpy.data.node_groups.new("cls_ToonCore", "ShaderNodeTree")
    ng.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    n, l = ng.nodes, ng.links
    gi = n.new("NodeGroupInput"); gi.location = (-900, 0)
    go = n.new("NodeGroupOutput"); go.location = (900, 0)
    diff = n.new("ShaderNodeBsdfDiffuse"); diff.location = (-700, 250)
    s2r = n.new("ShaderNodeShaderToRGB"); s2r.location = (-500, 250)
    ramp = n.new("ShaderNodeValToRGB"); ramp.location = (-300, 350)
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*lin((0.34, 0.32, 0.50)), 1)   # 阴影：偏冷紫
    cr.elements[1].position = 0.16
    cr.elements[1].color = (*lin((0.62, 0.60, 0.70)), 1)   # 过渡
    e = cr.elements.new(0.42)
    e.color = (1.0, 1.0, 1.0, 1)                    # 受光
    tint = n.new("ShaderNodeRGB"); tint.name = "TimeTint"; tint.label = "时段色调"
    tint.location = (-300, 50)
    tint.outputs[0].default_value = (1, 1, 1, 1)
    m_tint = n.new("ShaderNodeVectorMath"); m_tint.operation = "MULTIPLY"; m_tint.location = (0, 300)
    s_tone = n.new("ShaderNodeVectorMath"); s_tone.operation = "SCALE"; s_tone.location = (180, 300)
    s_tone.inputs["Scale"].default_value = 0.78
    clamp = n.new("ShaderNodeVectorMath"); clamp.operation = "MINIMUM"; clamp.location = (0, 100)
    clamp.inputs[1].default_value = (1.6, 1.6, 1.6)
    s_light = n.new("ShaderNodeVectorMath"); s_light.operation = "SCALE"; s_light.location = (180, 100)
    s_light.inputs["Scale"].default_value = 0.32
    add = n.new("ShaderNodeVectorMath"); add.operation = "ADD"; add.location = (380, 200)
    mul = n.new("ShaderNodeVectorMath"); mul.operation = "MULTIPLY"; mul.location = (560, 100)
    emit = n.new("ShaderNodeEmission"); emit.location = (740, 0)
    l.new(diff.outputs["BSDF"], s2r.inputs["Shader"])
    l.new(s2r.outputs["Color"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], m_tint.inputs[0])
    l.new(tint.outputs["Color"], m_tint.inputs[1])
    l.new(m_tint.outputs["Vector"], s_tone.inputs[0])
    l.new(s2r.outputs["Color"], clamp.inputs[0])
    l.new(clamp.outputs["Vector"], s_light.inputs[0])
    l.new(s_tone.outputs["Vector"], add.inputs[0])
    l.new(s_light.outputs["Vector"], add.inputs[1])
    l.new(add.outputs["Vector"], mul.inputs[0])
    l.new(gi.outputs["Color"], mul.inputs[1])
    l.new(mul.outputs["Vector"], emit.inputs["Color"])
    l.new(emit.outputs["Emission"], go.inputs["Shader"])
    return ng

def _new_material(name):
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    m.node_tree.nodes.clear()
    return m

def toon(name, rgb):
    rgb = lin(rgb)
    m = _new_material(name)
    nt = m.node_tree
    g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = TOON
    g.inputs["Color"].default_value = (*rgb, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(g.outputs["Shader"], out.inputs["Surface"])
    m.diffuse_color = (*rgb, 1)
    return m

def glow(name, rgb, strengths):
    """自发光材质。strengths = {"morning": x, "noon": y, "night": z}"""
    rgb = lin(rgb)
    m = _new_material(name)
    nt = m.node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1)
    em.inputs["Strength"].default_value = strengths["night"]
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = (*rgb, 1)
    GLOW_MATS.append((m, strengths))
    m["gsd_strengths"] = strengths
    return m

PALETTE = {
    # 水
    "sea": (0.14, 0.42, 0.72), "shallow": (0.30, 0.68, 0.82), "stream": (0.42, 0.78, 0.92), "foam": (0.92, 0.97, 1.0),
    # 地面
    "grass": (0.47, 0.72, 0.28), "grass_light": (0.62, 0.82, 0.36), "grass_dark": (0.30, 0.54, 0.20),
    "cliff": (0.58, 0.46, 0.34), "dirt": (0.50, 0.38, 0.26), "path": (0.88, 0.75, 0.53), "path_edge": (0.74, 0.60, 0.42),
    "soil": (0.42, 0.29, 0.20),
    # 石头
    "rock": (0.62, 0.62, 0.64), "rock_dark": (0.45, 0.46, 0.50), "rock_warm": (0.66, 0.60, 0.54), "moss": (0.38, 0.56, 0.26),
    # 木头与房屋
    "wood": (0.50, 0.32, 0.19), "wood_dark": (0.36, 0.22, 0.13), "wood_light": (0.76, 0.56, 0.36),
    "wall": (0.95, 0.88, 0.74), "roof": (0.30, 0.47, 0.40), "roof_dark": (0.22, 0.37, 0.32), "stone": (0.68, 0.64, 0.58),
    "glass_day": (0.55, 0.70, 0.80),
    # 植物
    "trunk": (0.42, 0.28, 0.18), "leaf": (0.33, 0.60, 0.26), "leaf2": (0.42, 0.68, 0.30), "leaf3": (0.55, 0.76, 0.34),
    "pine": (0.18, 0.43, 0.28), "pine2": (0.24, 0.52, 0.32),
    "sakura": (0.99, 0.74, 0.83), "sakura2": (0.96, 0.60, 0.74), "sakura3": (1.0, 0.86, 0.90),
    "reed": (0.52, 0.66, 0.30), "cattail": (0.48, 0.32, 0.20), "lily": (0.32, 0.58, 0.32),
    # 花
    "white": (0.97, 0.96, 0.92), "pink": (0.98, 0.56, 0.70), "purple": (0.62, 0.52, 0.92), "yellow": (0.99, 0.84, 0.32),
    "orange": (0.98, 0.62, 0.28), "red": (0.88, 0.32, 0.30), "blue": (0.45, 0.62, 0.95),
    # 道具
    "boat": (0.64, 0.46, 0.28), "laptop": (0.78, 0.80, 0.84), "screen": (0.25, 0.30, 0.40), "mug": (0.95, 0.94, 0.90),
    "book_red": (0.80, 0.36, 0.34), "book_blue": (0.36, 0.52, 0.78), "book_green": (0.40, 0.62, 0.42),
    "rope": (0.82, 0.72, 0.52), "metal": (0.30, 0.30, 0.34), "pot": (0.78, 0.46, 0.32),
    "cat": (0.98, 0.66, 0.32), "beak": (0.98, 0.62, 0.20), "black": (0.12, 0.10, 0.10),
    # 人物
    "skin": (1.0, 0.86, 0.76), "hair": (0.44, 0.28, 0.18), "shirt": (0.97, 0.93, 0.85), "skirt": (0.26, 0.40, 0.32),
    "shoe": (0.40, 0.26, 0.18), "eye": (0.20, 0.14, 0.12), "leaf_clip": (0.45, 0.72, 0.36),
    # 远景
    "far_island": (0.38, 0.60, 0.44), "far_tree": (0.30, 0.52, 0.38),
}

MOSS_RGB = (0.36, 0.52, 0.22)

def _sock(sockets, name, typ=None):
    for s in sockets:
        if s.name == name and (typ is None or s.type == typ) and s.enabled:
            return s
    for s in sockets:
        if s.name == name and (typ is None or s.type == typ):
            return s
    raise KeyError(name)

def mix_color(nt, fac, a, b):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    nt.links.new(fac, _sock(m.inputs, "Factor", "VALUE"))
    for sock, val in ((_sock(m.inputs, "A", "RGBA"), a), (_sock(m.inputs, "B", "RGBA"), b)):
        if isinstance(val, tuple):
            sock.default_value = (*val, 1) if len(val) == 3 else val
        else:
            nt.links.new(val, sock)
    return _sock(m.outputs, "Result", "RGBA")

def _set(sockets, name, val):
    try:
        sockets[name].default_value = val
    except (KeyError, TypeError):
        pass

def pbr(name, rgb, var=0.12, scale=3.0, rough=0.82, moss=False, sss=0.0, spec=0.25, grad=None, grad_axis="X"):
    """风格化 PBR：底色 × 噪声明暗起伏 →（青苔/根部渐变）→ 环境光遮蔽 → Principled"""
    m = _new_material(name)
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    noise = N.new("ShaderNodeTexNoise"); noise.location = (-700, 0)
    _set(noise.inputs, "Scale", scale); _set(noise.inputs, "Detail", 4.0); _set(noise.inputs, "Roughness", 0.6)
    Lk.new(tc.outputs["Object"], noise.inputs["Vector"])
    mr = N.new("ShaderNodeMapRange"); mr.location = (-500, 0)
    _set(mr.inputs, "From Min", 0.3); _set(mr.inputs, "From Max", 0.7)
    _set(mr.inputs, "To Min", 1 - var); _set(mr.inputs, "To Max", 1 + var)
    Lk.new(noise.outputs["Fac"], mr.inputs["Value"])
    hs = N.new("ShaderNodeHueSaturation"); hs.location = (-300, 0)
    hs.inputs["Color"].default_value = (*lin(rgb), 1)
    Lk.new(mr.outputs["Result"], hs.inputs["Value"])
    col = hs.outputs["Color"]
    if grad is not None:
        sep = N.new("ShaderNodeSeparateXYZ")
        Lk.new(tc.outputs["Generated"], sep.inputs["Vector"])
        col = mix_color(nt, sep.outputs[grad_axis], tuple(lin(grad)), col)
    if moss:
        geo = N.new("ShaderNodeNewGeometry")
        sep = N.new("ShaderNodeSeparateXYZ")
        Lk.new(geo.outputs["Normal"], sep.inputs["Vector"])
        mr2 = N.new("ShaderNodeMapRange")
        _set(mr2.inputs, "From Min", 0.55); _set(mr2.inputs, "From Max", 0.9)
        Lk.new(sep.outputs["Z"], mr2.inputs["Value"])
        n2 = N.new("ShaderNodeTexNoise"); _set(n2.inputs, "Scale", scale * 2.5); _set(n2.inputs, "Detail", 5.0)
        Lk.new(tc.outputs["Object"], n2.inputs["Vector"])
        mr3 = N.new("ShaderNodeMapRange")
        _set(mr3.inputs, "From Min", 0.45); _set(mr3.inputs, "From Max", 0.6)
        Lk.new(n2.outputs["Fac"], mr3.inputs["Value"])
        mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
        Lk.new(mr2.outputs["Result"], mul.inputs[0]); Lk.new(mr3.outputs["Result"], mul.inputs[1])
        col = mix_color(nt, mul.outputs[0], col, tuple(lin(MOSS_RGB)))
    ao = N.new("ShaderNodeAmbientOcclusion"); ao.location = (300, 0)
    _set(ao.inputs, "Distance", 0.5)
    Lk.new(col, ao.inputs["Color"])
    Lk.new(ao.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf.inputs, "Roughness", rough)
    _set(bsdf.inputs, "Specular IOR Level", spec)
    if sss:
        _set(bsdf.inputs, "Subsurface Weight", sss)
        _set(bsdf.inputs, "Subsurface Radius", (0.3, 0.5, 0.15))
        _set(bsdf.inputs, "Subsurface Scale", 0.05)
    Lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    m.diffuse_color = (*lin(rgb), 1)
    return m

TIMES = {
    # el/az: 太阳高度角、方位角；sun/power: 阳光颜色强度；sky: 环境光；tint: 整体色调；
    # bloom: 光晕强度；line: 描边颜色
    "morning": dict(el=16, az=-125, sun=(1.0, 0.78, 0.56), power=4.2, sky=(0.98, 0.80, 0.66), sky_power=0.85,
                    tint=(1.0, 0.90, 0.80), bloom=0.5, line=(0.30, 0.18, 0.14), haze=0.010, haze_col=(1.0, 0.86, 0.70)),
    "noon":    dict(el=58, az=-150, sun=(1.0, 0.97, 0.92), power=4.8, sky=(0.62, 0.80, 1.00), sky_power=1.0,
                    tint=(1.0, 1.0, 1.0), bloom=0.3, line=(0.24, 0.17, 0.13), haze=0.004, haze_col=(0.85, 0.92, 1.0)),
    "night":   dict(el=42, az=-115, sun=(0.55, 0.68, 1.0), power=0.7, sky=(0.07, 0.10, 0.22), sky_power=0.35,
                    tint=(0.42, 0.48, 0.72), bloom=1.1, line=(0.08, 0.08, 0.14), haze=0.012, haze_col=(0.55, 0.65, 0.95)),
}


def build_materials():
    global TOON
    TOON=build_toon_group()
    palette=dict(PALETTE)
    palette.update(paper=(.94,.88,.72),ink=(.09,.11,.18),brass=(.72,.53,.25),
        board=(.055,.12,.11),board_ui=(.035,.065,.065))
    mats={k:pbr('cls_'+k,v,var=.08 if k in ('wall','paper','board','board_ui') else .12,
        rough=.82,spec=.25,moss=k=='stone') for k,v in palette.items()}
    # 青苔仅用于窗台/石材朝上面；金属光泽克制。
    mats['brass']=pbr('cls_brass_polished',palette['brass'],var=.07,rough=.4,spec=.4)
    mats['purple']=toon('cls_toon_lilac',palette['purple'])
    mats['blue']=toon('cls_toon_blue',palette['blue'])
    for k,col,strength in (
        ('magic_lilac',(.62,.52,.92),(.7,.5,3.8)),
        ('magic_blue',(.45,.62,.95),(.6,.4,3)),
        ('flame',(1,.65,.24),(3,1.5,7)),
        ('liquid_a',(.43,.81,.72),(.4,.2,2.5)),
        ('liquid_b',(.66,.43,.91),(.4,.2,3)),
        ('liquid_c',(.95,.65,.28),(.4,.2,2.8)),
        ('star',(.85,.85,1),(1,.7,5)),
        ('plant_glow',(.42,.85,.64),(.4,.25,3))):
        mats[k]=glow('cls_'+k,col,dict(zip(('morning','noon','night'),strength)))
    # EE VEE 友好的玻璃：轻度透射，发光液芯作为独立网格。
    g=pbr('cls_glass',(.72,.86,.88),var=.025,rough=.16,spec=.4)
    b=next(n for n in g.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    _set(b.inputs,'Transmission Weight',.65);_set(b.inputs,'IOR',1.36)
    mats['glass']=g
    for k in ('backdrop_sky','backdrop_island','backdrop_far'):
        mats[k]=glow('cls_'+k,(.5,.65,.8),dict(morning=.75,noon=.85,night=.4))
    return mats


# 建筑：真实拱窗、细分木地板、半木框架与保留中央净区的黑板。

def _cls_architecture_bevel(obj, width=.025, segments=2):
    # 小尺度倒角使轮廓保留手工模型的柔和高光。
    if width > 0:
        modifier = obj.modifiers.new('cls_手工倒角', 'BEVEL')
        modifier.width = width
        modifier.segments = segments
        modifier.limit_method = 'ANGLE'
    return obj


def _cls_x_prism(name, profile, x0, x1, mat, coll, bevel=0):
    # 沿 X 挤出任意 YZ 截面；拱窗墙体直接建模，不依赖布尔结果。
    n = len(profile)
    vertices = [(x0, y, z) for y, z in profile]
    vertices += [(x1, y, z) for y, z in profile]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return _cls_architecture_bevel(mesh_obj(name, vertices, faces, mat, coll), bevel)


def _cls_timber_arch(name, y, angle_a, angle_b, mat, coll, low=False):
    # 每段梁都是实体矩形截面；后方仅留低短梁，中央不封顶。
    count = max(5, int(abs(angle_b - angle_a) * 16))
    spring = 3.13 if low else 4.47
    rise = .78 if low else 1.33
    vertices = []
    for i in range(count + 1):
        t = angle_a + (angle_b - angle_a) * i / count
        for radius_x, radius_z, offset_y in ((4.48, rise, -.13),
                                            (4.26, rise - .19, -.13),
                                            (4.48, rise, .13),
                                            (4.26, rise - .19, .13)):
            vertices.append((radius_x * math.cos(t), y + offset_y,
                             spring + radius_z * math.sin(t)))
    faces = [(0, 2, 3, 1)]
    for i in range(count):
        j, k = 4 * i, 4 * (i + 1)
        faces.extend([(j, k, k + 1, j + 1), (j + 2, j + 3, k + 3, k + 2),
                      (j, j + 2, k + 2, k), (j + 1, k + 1, k + 3, j + 3)])
    j = 4 * count
    faces.append((j, j + 1, j + 3, j + 2))
    return _cls_architecture_bevel(mesh_obj(name, vertices, faces, mat, coll), .025)


def build_architecture(M, C):
    coll = C['architecture']
    rng = random.Random(84021)
    # 悬浮剖面的厚底座与逐块铺设的错缝地板，正面不设墙体。
    box('cls_floor_foundation', (0, 0, -.23), (9.36, 11.36, .42), M['wood_dark'], coll, .12)
    box('cls_floor_lower_rim', (0, 0, -.43), (9.18, 11.18, .10), M['brass'], coll, .025)
    box('cls_floor_front_fascia', (0, -5.57, -.18), (9.34, .13, .35), M['wood'], coll, .035)
    box('cls_floor_right_fascia', (4.56, 0, -.18), (.13, 11.1, .35), M['wood'], coll, .035)
    plank_count = 0
    # 三十条窄板以 1.48 米为节距，交错半格接缝，总数超过二百。
    for row in range(30):
        x = -4.5 + (row + .5) * .3
        start = -5.5 - (.74 if row % 2 else 0)
        index = 0
        while start < 5.5:
            end = min(5.5, start + 1.48)
            lo = max(-5.5, start)
            length = end - lo
            if length > .06:
                y = (lo + end) / 2
                material = M['wood_light'] if rng.random() < .31 else M['wood']
                box('cls_floor_plank_%02d_%02d' % (row, index), (x, y, .015),
                    (.289, length - .014, .075), material, coll, .012)
                plank_count += 1
                if (row + index) % 4 == 0 and length > .4:
                    # 细长木纹采用低矮实体，避免大面积重复的贴图感。
                    grain_x = x + rng.uniform(-.085, .085)
                    tube('cls_floor_grain_%02d_%02d' % (row, index),
                         [(grain_x, lo + .12, .054),
                          (grain_x + .012, y, .055),
                          (grain_x - .008, end - .12, .054)],
                         .0028, M['wood_dark'], coll)
                if (row + index) % 3 == 0 and length > .35:
                    for k, nail_y in enumerate((lo + .075, end - .075)):
                        cylinder('cls_floor_pin_%02d_%02d_%d' % (row, index, k),
                                 (x + .085, nail_y, .055), .009, .006,
                                 M['metal'], coll, vertices=8)
            start += 1.48
            index += 1
    # 讲台高度较低，C1 占位区仍从台面以上获得完整净空。
    box('cls_stage_base', (0, 4.30, .085), (8.75, 2.40, .12), M['wood_dark'], coll, .045)
    for i in range(29):
        box('cls_stage_plank_%02d' % i, (-4.35 + (i + .5) * .3, 4.30, .1475),
            (.288, 2.36, .065), M['wood_light'] if i % 5 == 0 else M['wood'], coll, .012)
    box('cls_stage_front_nosing', (0, 3.1, .1175), (8.78, .10, .125), M['wood_light'], coll, .03)
    box('cls_stage_step', (0, 2.91, .075), (3.65, .36, .10), M['wood'], coll, .035)
    # 左墙下部为三层圆润砌石；所有窗洞从 1.10 米开始完全贯通。
    box('cls_left_lower_core', (-4.5, 0, .49), (.42, 11.0, .98), M['stone'], coll, .03)
    box('cls_front_lower_core', (0, 5.49, .49), (9.0, .42, .98), M['stone'], coll, .03)
    for wall in ('left', 'front'):
        span = 11.0 if wall == 'left' else 9.0
        for row in range(3):
            start = -span / 2 - (.41 if row % 2 else 0)
            index = 0
            while start < span / 2:
                end = min(span / 2, start + .82)
                lo = max(-span / 2, start)
                width = end - lo
                if width > .08:
                    center = (lo + end) / 2
                    z = .17 + row * .325 + rng.uniform(-.009, .009)
                    mat = M['rock_warm'] if rng.random() < .24 else M['stone']
                    if wall == 'left':
                        loc, size = (-4.475, center, z), (.52, width - .025, .30)
                    else:
                        loc, size = (center, 5.465, z), (width - .025, .52, .30)
                    box('cls_masonry_%s_%d_%02d' % (wall, row, index), loc, size, mat, coll, .045)
                start += .82
                index += 1
    box('cls_left_sill_rail', (-4.48, 0, 1.055), (.56, 11.07, .12), M['wood_dark'], coll, .024)
    box('cls_front_dado_rail', (0, 5.23, 1.055), (9.0, .12, .12), M['wood_dark'], coll, .024)
    # 前墙为连续抹灰板，左墙在窗洞外单独构建墙墩和拱上墙。
    box('cls_front_plaster', (0, 5.49, 2.8), (9.0, .40, 3.4), M['wall'], coll, .025)
    window_centers = (-2.8, .3, 3.4)
    radius, spring, wall_top = .975, 3.325, 4.5
    intervals = [(-5.5, window_centers[0] - radius)]
    intervals += [(window_centers[i] + radius, window_centers[i + 1] - radius) for i in range(2)]
    intervals.append((window_centers[-1] + radius, 5.5))
    for i, (a, b) in enumerate(intervals):
        box('cls_left_wall_pier_%d' % i, (-4.5, (a + b) / 2, 2.8),
            (.40, b - a, 3.4), M['wall'], coll, .012)
    for wi, center in enumerate(window_centers):
        # 上缘沿拱曲线取样，窗内没有用于伪装开口的深色平面。
        profile = []
        for j in range(33):
            angle = math.pi - math.pi * j / 32
            profile.append((center + radius * math.cos(angle), spring + radius * math.sin(angle)))
        profile += [(center + radius, wall_top), (center - radius, wall_top)]
        _cls_x_prism('cls_window_spandrel_%d' % wi, profile, -4.70, -4.30, M['wall'], coll)
        box('cls_window_sill_%d' % wi, (-4.46, center, 1.105), (.68, 2.24, .13), M['stone'], coll, .04)
        # 拱券与窗边立石独立分块，使每一块石头都有柔和的边缘。
        for j in range(13):
            a = math.pi * j / 13 + .009
            b = math.pi * (j + 1) / 13 - .009
            profile = [(center + r * math.cos(t), spring + r * math.sin(t))
                       for r, t in ((radius, a), (1.125, a), (1.125, b), (radius, b))]
            _cls_x_prism('cls_window_arch_stone_%d_%02d' % (wi, j), profile,
                         -4.76, -4.23, M['rock_warm'] if j % 4 == 0 else M['stone'], coll, .017)
        for side in (-1, 1):
            for j in range(6):
                h = (spring - 1.17) / 6
                box('cls_window_jamb_%d_%d_%d' % (wi, side, j),
                    (-4.49, center + side * 1.05, 1.17 + (j + .5) * h),
                    (.53, .15, h - .018), M['stone'], coll, .022)
        # 纤细木窗棂不会填满洞口，背后的天空可直接透过。
        rim = [(-4.275, center - .955, 1.18), (-4.275, center - .955, spring)]
        rim += [(-4.275, center + .955 * math.cos(math.pi - j * math.pi / 24),
                 spring + .955 * math.sin(math.pi - j * math.pi / 24)) for j in range(25)]
        rim += [(-4.275, center + .955, 1.18)]
        tube('cls_window_wood_rim_%d' % wi, rim, .035, M['wood_dark'], coll)
        box('cls_window_mullion_%d' % wi, (-4.278, center, 2.665), (.067, .055, 2.97), M['wood_dark'], coll, .012)
        box('cls_window_transom_%d' % wi, (-4.278, center, 3.18), (.067, 1.88, .05), M['wood_dark'], coll, .01)
        # 窗台前端的暖铜饰钉和左右小托臂。
        for side in (-1, 1):
            box('cls_window_sill_bracket_%d_%d' % (wi, side),
                (-4.19, center + side * .78, .945), (.18, .12, .23), M['wood'], coll, .025)
    # 木框架遵循墙墩布局，避免穿过三个真正的窗洞。
    for i, y in enumerate((-5.43, -1.25, 1.85, 5.40)):
        box('cls_left_timber_post_%d' % i, (-4.235, y, 2.80), (.17, .17, 3.42), M['wood_dark'], coll, .025)
        box('cls_left_post_cap_%d' % i, (-4.22, y, 4.40), (.26, .29, .13), M['wood_light'], coll, .025)
    box('cls_left_top_beam', (-4.23, 0, 4.49), (.21, 11.12, .20), M['wood_dark'], coll, .035)
    for i, x in enumerate((-4.36, -3.55, 2.65, 4.36)):
        box('cls_front_timber_post_%d' % i, (x, 5.245, 2.79), (.17, .15, 3.43), M['wood_dark'], coll, .025)
    box('cls_front_top_beam', (0, 5.245, 4.49), (9.12, .23, .22), M['wood_dark'], coll, .035)
    # 四道连续木拱构成无屋面的穹顶，颜色与室内承重木框架统一。
    for i, y in enumerate((-4.9, -2.2, 1.0, 4.94)):
        name = 'cls_roof_arch_front' if i == 3 else 'cls_roof_arch_full_%d' % i
        _cls_timber_arch(name, y, 0, math.pi, M['wood_dark'], coll)
    # 右侧纵向檩条连接拱脚，消除悬空的截断梁端。
    box('cls_roof_right_eave', (4.38, .02, 4.47), (.20, 10.10, .20), M['wood_dark'], coll, .025)
    # 右侧保留两根细支柱，右墙整体敞开。
    for i, (y, top) in enumerate(((4.94, 4.47), (-4.9, 4.47))):
        box('cls_right_open_post_%d' % i, (4.38, y, top / 2), (.19, .21, top), M['wood_dark'], coll, .028)
        box('cls_right_post_foot_%d' % i, (4.38, y, .19), (.31, .33, .31), M['stone'], coll, .055)
        box('cls_right_post_collar_%d' % i, (4.38, y, top - .10), (.28, .28, .15), M['brass'], coll, .025)
    # 前拱的横向细金属箍只位于梁上，不横穿室内视线。
    for i, angle in enumerate((.34, .86, math.pi / 2, math.pi - .86, math.pi - .34)):
        x = 4.37 * math.cos(angle)
        z = 4.47 + 1.23 * math.sin(angle)
        sphere('cls_arch_front_bolt_%d' % i, (x, 4.795, z), (.043, .018, .043), M['brass'], coll, segments=12, rings=6)
    log('建筑完成：%d 块地板，3 个真实拱窗，开放右墙/后墙/顶面。' % plank_count)


def _cls_board_text(name, value, x, z, size, material, coll, align='CENTER'):
    # 使用 Blender 内置字体，避免外部字体依赖；文字面朝室内负 Y。
    curve = bpy.data.curves.new(name + '_font', 'FONT')
    curve.body = value
    curve.size = size
    curve.align_x = align
    curve.align_y = 'CENTER'
    curve.extrude = 0
    curve.space_character = 1.12
    obj = bpy.data.objects.new(name, curve)
    coll.objects.link(obj)
    obj.parent = ROOM_ROOT
    obj.location = (x, 5.112, z)
    obj.rotation_euler = (math.pi / 2, 0, 0)
    curve.materials.append(material)
    return obj


def build_board(M, C):
    coll = C['architecture']
    cx, cy, cz = -.6, 5.20, 2.65
    width, height = 5.0, 2.15
    ui_width, ui_height = width * math.sqrt(.60), height * math.sqrt(.60)
    box('cls_board_back', (cx, cy + .025, cz), (5.29, .16, 2.44), M['wood_dark'], coll, .045)
    box('cls_board_chalk_surface', (cx, cy, cz), (width, .13, height), M['board'], coll, .014)
    # 中心独立面片精确占 60% 面积：材质、对象均有稳定名称供后续定位。
    x0, x1 = cx - ui_width / 2, cx + ui_width / 2
    z0, z1 = cz - ui_height / 2, cz + ui_height / 2
    panel = mesh_obj('cls_board_ui_panel', [(x0, 5.120, z0), (x1, 5.120, z0),
                                           (x1, 5.120, z1), (x0, 5.120, z1)],
                     [(0, 1, 2, 3)], M['board_ui'], coll)
    panel['ui_area_fraction'] = .60
    panel['ui_width'] = ui_width
    panel['ui_height'] = ui_height
    panel['clear_region'] = True
    # 粉笔痕、文字与符文全部约束在中央面片之外的边缘区域。
    for side in (-1, 1):
        x = cx + side * (width / 2 + .073)
        box('cls_board_frame_side_%d' % side, (x, 5.135, cz), (.145, .16, 2.45), M['wood'], coll, .023)
        box('cls_board_frame_side_inlay_%d' % side, (x, 5.045, cz), (.022, .012, 2.25), M['brass'], coll, .004)
    for side in (-1, 1):
        z = cz + side * (height / 2 + .074)
        box('cls_board_frame_horizontal_%d' % side, (cx, 5.135, z), (5.26, .16, .147), M['wood_light'], coll, .025)
        box('cls_board_frame_horizontal_inlay_%d' % side, (cx, 5.045, z), (5.06, .012, .022), M['brass'], coll, .004)
    box('cls_board_chalk_ledge', (cx, 4.985, 1.47), (5.38, .40, .105), M['wood'], coll, .025)
    box('cls_board_ledge_lip', (cx, 4.805, 1.505), (5.38, .055, .085), M['wood_light'], coll, .015)
    for i in range(4):
        cylinder('cls_board_chalk_%d' % i, (1.15 + i * .11, 4.985, 1.537), .016, .15,
                 M['paper'] if i < 3 else M['magic_lilac'], coll, vertices=10, rot=(0, math.pi / 2, -.13 * i))
    box('cls_board_eraser', (-2.61, 4.975, 1.56), (.28, .12, .09), M['wood_dark'], coll, .018)
    box('cls_board_eraser_felt', (-2.61, 4.975, 1.515), (.29, .13, .025), M['black'], coll, .006)
    # 左右各三枚小型阵法，圆弧半径与星芒都小于边缘带宽。
    for side in (-1, 1):
        x = cx + side * 2.205
        for i, z in enumerate((2.04, 2.65, 3.26)):
            for ri, radius in enumerate((.166, .192)):
                pts = [(x + radius * math.cos(j * math.tau / 32), 5.112,
                        z + radius * math.sin(j * math.tau / 32)) for j in range(32)]
                tube('cls_board_rune_circle_%d_%d_%d' % (side, i, ri), pts,
                     .0045 if ri else .006, M['paper'], coll, cyclic=True)
            count = 3 if i != 1 else 4
            pts = [(x + .137 * math.cos(math.pi / 2 + j * math.tau / count), 5.110,
                    z + .137 * math.sin(math.pi / 2 + j * math.tau / count)) for j in range(count)]
            tube('cls_board_rune_polygon_%d_%d' % (side, i), pts, .0055,
                 M['magic_lilac'] if i == 1 else M['paper'], coll, cyclic=True)
            tube('cls_board_rune_axis_%d_%d' % (side, i),
                 [(x - .07, 5.109, z), (x + .07, 5.109, z)], .004, M['paper'], coll)
            _cls_board_text('cls_board_rune_note_%d_%d' % (side, i),
                            ('I', 'II', 'III')[i], x, z - .252, .068, M['paper'], coll)
    _cls_board_text('cls_board_top_equation', 'L U M E N  +  A E T H E R   =   V I T A',
                    cx, 3.602, .09, M['paper'], coll)
    _cls_board_text('cls_board_bottom_equation', '01  /  INTENTIO     *     MOTUS     *     HARMONIA  /  03',
                    cx, 1.686, .075, M['paper'], coll)
    # 四个定位短线在净区外侧，中心区域绝无装饰跨越。
    for sx in (-1, 1):
        for sz in (-1, 1):
            x = cx + sx * (ui_width / 2 + .025)
            z = cz + sz * (ui_height / 2 + .025)
            tube('cls_board_ui_corner_%d_%d' % (sx, sz),
                 [(x + sx * .09, 5.111, z), (x, 5.111, z), (x, 5.111, z + sz * .065)],
                 .0045, M['magic_lilac'], coll)
    log('黑板完成：中心 UI %.5f × %.5f 米，占面板面积 60%%。' % (ui_width, ui_height))
    return panel


def _cls_backdrop_shadowless(material):
    # 阴影光线看到透明着色，天空与浮岛仍由原发光节点负责时段切换。
    nt = material.node_tree
    if nt.nodes.get('cls_backdrop_shadow_mix'):
        return
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    source = out.inputs['Surface'].links[0].from_socket
    light_path = nt.nodes.new('ShaderNodeLightPath')
    light_path.name = 'cls_backdrop_ray_type'
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.name = 'cls_backdrop_shadow_mix'
    nt.links.new(light_path.outputs['Is Shadow Ray'], mix.inputs[0])
    nt.links.new(source, mix.inputs[1])
    nt.links.new(transparent.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    if hasattr(material, 'surface_render_method'):
        material.surface_render_method = 'DITHERED'
    if hasattr(material, 'use_transparent_shadow'):
        material.use_transparent_shadow = True
    if hasattr(material, 'shadow_method'):
        material.shadow_method = 'NONE'


def _cls_clip_window_polygon(polygon, aperture):
    # 用凸拱形逐边裁剪二维轮廓，所有背景岛屿都严格留在窗洞内部。
    result = list(polygon)
    for a, b in zip(aperture, aperture[1:] + aperture[:1]):
        if not result:
            break
        def distance(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        previous = result[-1]
        dp = distance(previous)
        output = []
        for current in result:
            dc = distance(current)
            if (dc >= -1e-9) != (dp >= -1e-9):
                t = dp / (dp - dc)
                output.append((previous[0] + t * (current[0] - previous[0]),
                               previous[1] + t * (current[1] - previous[1])))
            if dc >= -1e-9:
                output.append(current)
            previous, dp = current, dc
        result = output
    return result


def build_backdrop(M, C):
    coll = C['backdrop']
    # 天空总网格只有三片拱窗大小的面，紧贴外墙，不在剖面外形成巨幅背景板。
    for key in ('backdrop_sky', 'backdrop_far', 'backdrop_island'):
        _cls_backdrop_shadowless(M[key])
    radius, spring, sill = .975, 3.325, 1.10
    apertures, vertices, faces = [], [], []
    for center in (-2.8, .3, 3.4):
        profile = [(center - radius, sill), (center + radius, sill), (center + radius, spring)]
        profile += [(center + radius * math.cos(j * math.pi / 32),
                     spring + radius * math.sin(j * math.pi / 32)) for j in range(1, 33)]
        apertures.append(profile)
        start = len(vertices)
        vertices.extend([(-4.705, y, z) for y, z in profile])
        faces.append(tuple(range(start, len(vertices))))
    sky = mesh_obj('cls_backdrop', vertices, faces, M['backdrop_sky'], coll)
    if hasattr(sky, 'visible_shadow'):
        sky.visible_shadow = False
    rng = random.Random(112)
    for wi, (center, aperture) in enumerate(zip((-2.8, .3, 3.4), apertures)):
        for layer, offset, top, width, depth in ((0, -.42, 3.20, .75, .64),
                                                (1, .44, 2.50, .65, .83),
                                                (2, -.30, 1.68, .46, .51)):
            cy = center + offset
            outline = [(cy - width, top), (cy - width * .65, top + .09),
                       (cy - width * .15, top + .13), (cy + width * .40, top + .08),
                       (cy + width, top), (cy + width * .55, top - .18),
                       (cy + width * .21, top - depth * .40), (cy + width * .06, top - depth),
                       (cy - width * .20, top - depth * .62), (cy - width * .60, top - .20)]
            material = M['backdrop_far'] if layer == 0 else M['backdrop_island']
            x = -4.702 + layer * .003
            clipped = _cls_clip_window_polygon(outline, aperture)
            if len(clipped) >= 3:
                ob = mesh_obj('cls_backdrop_island_%d_%d' % (wi, layer),
                              [(x, y, z) for y, z in clipped], [tuple(range(len(clipped)))], material, coll)
                if hasattr(ob, 'visible_shadow'):
                    ob.visible_shadow = False
            for ti in range(3):
                ty = cy + (ti - 1) * width * .45
                height = rng.uniform(.15, .28)
                zz = top + .08
                w = height * .28
                tree = [(ty - w, zz), (ty, zz + height), (ty + w, zz)]
                clipped = _cls_clip_window_polygon(tree, aperture)
                if len(clipped) >= 3:
                    ob = mesh_obj('cls_backdrop_tree_%d_%d_%d' % (wi, layer, ti),
                                  [(x + .001, y, z) for y, z in clipped], [tuple(range(len(clipped)))], material, coll)
                    if hasattr(ob, 'visible_shadow'):
                        ob.visible_shadow = False
    log('窗外背景完成：三片贴合真实窗洞的天空与裁剪浮岛，阴影光线透明。')


# 家具、书籍与悬浮教具。所有尺寸为米；不依赖外部资源。
# 这段与基础工具拼接；每个动态道具保留独立根节点以便投影避让。


def _cls_prop_parent(ob, root):
    basis = ob.matrix_basis.copy()
    ob.parent = root
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = basis
    return ob


def _cls_prop_box(name, loc, size, mat, coll, root=None, bevel=.025, rot=(0, 0, 0)):
    ob = box(name, loc, size, mat, coll, bevel=bevel, rot=rot)
    for mod in ob.modifiers:
        if mod.type == 'BEVEL':
            mod.segments = 2 if min(size) > .065 else 1
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_sphere(name, loc, size, mat, coll, root=None, segments=16, rings=8):
    ob = sphere(name, loc, size, mat, coll, segments=segments, rings=rings)
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_tube(name, points, radius, mat, coll, root=None, cyclic=False):
    ob = tube(name, points, radius, mat, coll, cyclic=cyclic)
    ob.data.bevel_resolution = 1 if radius >= .008 else 0
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_cyl(name, loc, radius, depth, mat, coll, root=None,
                  vertices=20, rot=(0, 0, 0), radius2=None):
    ob = cylinder(name, loc, radius, depth, mat, coll,
                  vertices=vertices, rot=rot, radius2=radius2)
    for mod in ob.modifiers:
        if mod.type == 'BEVEL':
            mod.segments = 1
    return _cls_prop_parent(ob, root) if root else ob


def _cls_prop_multibox(name, blocks, materials, coll, bevel=.006):
    """一本书合并成单网格，全部书架实例共享少量网格。"""
    verts, faces, indices = [], [], []
    for center, size, material_index in blocks:
        x, y, z = center
        a, b, c = (v * .5 for v in size)
        n = len(verts)
        verts.extend([(x-a, y-b, z-c), (x+a, y-b, z-c),
                      (x+a, y+b, z-c), (x-a, y+b, z-c),
                      (x-a, y-b, z+c), (x+a, y-b, z+c),
                      (x+a, y+b, z+c), (x-a, y+b, z+c)])
        faces.extend([tuple(n+j for j in f) for f in
                      [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                       (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]])
        indices.extend([material_index] * 6)
    ob = mesh_obj(name, verts, faces, materials[0], coll)
    for mat in materials[1:]:
        ob.data.materials.append(mat)
    for polygon, index in zip(ob.data.polygons, indices):
        polygon.material_index = index
    if bevel:
        mod = ob.modifiers.new('cls_soft_book_edges', 'BEVEL')
        mod.width, mod.segments = bevel, 1
        # 封皮与纸块倒角，极小的烫金细带保持平直，共享实例更轻巧。
        mod.limit_method = 'WEIGHT'
        weights = ob.data.attributes.new('bevel_weight_edge', 'FLOAT', 'EDGE')
        for edge in ob.data.edges:
            weights.data[edge.index].value = 1.0 if edge.vertices[0] < 32 else 0.0
    return ob


def _cls_book_source(name, cover, M, coll):
    # 原点在书底，脊背朝 -Y；书架旋转后朝教室内。
    blocks = [((0, 0, .215), (.104, .255, .405), 0),
              ((-.061, 0, .215), (.018, .282, .43), 1),
              (( .061, 0, .215), (.018, .282, .43), 1),
              ((0, -.135, .215), (.139, .024, .43), 1)]
    for z in (.063, .101, .328, .367):
        blocks.append(((0, -.151, z), (.143, .013, .011), 2))
    blocks.append(((0, -.153, .234), (.080, .010, .071), 2))
    blocks.append(((0, -.160, .234), (.056, .005, .047), 1))
    return _cls_prop_multibox(name, blocks, [M['paper'], cover, M['brass']], coll)


def _cls_book_instance(source, name, coll, root, loc, scale=(1, 1, 1), rz=0, lean=0):
    ob = source.copy()
    ob.data = source.data
    ob.name = name if name.startswith('cls_') else 'cls_' + name
    coll.objects.link(ob)
    ob.parent = root
    ob.location = loc
    ob.rotation_euler = (0, lean, rz)
    ob.scale = scale
    return ob


def _cls_open_book(name, pos, scale, angle, M, coll, cover='book_red', root=None):
    """弧形书页、分层纸边和非文字符号；页面厚度无需细分修改器。"""
    book = empty(name + '_root', pos, coll)
    if root:
        _cls_prop_parent(book, root)
    book.scale = (scale, scale, scale)
    book.rotation_euler.z = angle
    _cls_prop_box(name + '_left_cover', (-.172, 0, .017), (.345, .46, .028),
                  M[cover], coll, book, .018, (0, -.065, 0))
    _cls_prop_box(name + '_right_cover', (.172, 0, .017), (.345, .46, .028),
                  M[cover], coll, book, .018, (0, .065, 0))
    _cls_prop_cyl(name + '_spine', (0, 0, .029), .028, .465, M[cover], coll,
                  book, vertices=16, rot=(math.pi/2, 0, 0))
    def surface(u, side, y, lift=0):
        return (side * (.018 + .313*u), y,
                .053 + .030*math.sin(math.pi*u) + .012*u + lift)
    for side in (-1, 1):
        verts, faces = [], []
        for row in range(2):
            for i in range(13):
                verts.append(surface(i / 12, side, -.211 if row == 0 else .211))
        for i in range(12):
            face = (i, i+1, i+14, i+13)
            faces.append(face if side == 1 else tuple(reversed(face)))
        page = mesh_obj(name + '_curved_page_' + str(side), verts, faces, M['paper'], coll)
        _cls_prop_parent(page, book)
        solid = page.modifiers.new('cls_paper_block_thickness', 'SOLIDIFY')
        solid.thickness = .024
        for poly in page.data.polygons:
            poly.use_smooth = True
        for j in range(3):
            for yy in (-.212, .212):
                points = [surface(i/12, side, yy, -.006-j*.007) for i in range(13)]
                _cls_prop_tube(name + '_layered_page_edge', points, .0018,
                               M['wood_light'], coll, book)
        # 细短行、圆形符文以及三角星图，避免依赖字体。
        for line in range(5):
            yy = -.145 + line*.052
            end = .88 if line % 2 else .75
            points = [surface(u, side, yy, .003) for u in (.16, .35, .54, end)]
            if line != 2 or side == -1:
                _cls_prop_tube(name + '_ink_line', points, .0023, M['ink'], coll, book)
        if side == 1:
            pts = [surface(.52+.20*math.cos(t), side, .018+.044*math.sin(t), .005)
                   for t in [i*math.tau/24 for i in range(24)]]
            _cls_prop_tube(name + '_page_sigil', pts, .003, M['brass'], coll, book, True)
            pts = [surface(u, side, y, .006) for u, y in
                   ((.52, .076), (.75, -.025), (.29, -.025), (.52, .076))]
            _cls_prop_tube(name + '_page_triangle', pts, .0025, M['ink'], coll, book)
    _cls_prop_tube(name + '_ribbon', [(0, -.15, .057), (.01, -.245, .04),
                                    (.023, -.285, .015), (.042, -.31, .009)],
                   .007, M['book_red'], coll, book)
    return book


def _cls_bottle(name, pos, size, color, M, coll, root=None, shared=None):
    bottle = empty(name + '_root', pos, coll)
    if root:
        _cls_prop_parent(bottle, root)
    bottle.scale = (size, size, size)
    # 液体外观采用玻璃壳 + 明亮核心，避免把装饰瓶变成不可读透明球。
    pieces = []
    pieces.append(_cls_prop_sphere(name + '_glass', (0, 0, .105), (.09, .09, .105),
                                   M['glass'], coll, bottle, 16, 8))
    pieces.append(_cls_prop_sphere(name + '_elixir', (0, 0, .086), (.073, .073, .072),
                                   M[color], coll, bottle, 16, 8))
    pieces.append(_cls_prop_cyl(name + '_neck', (0, 0, .212), .039, .086,
                                M['glass'], coll, bottle, vertices=16))
    pieces.append(_cls_prop_cyl(name + '_lip', (0, 0, .248), .049, .023,
                                M['brass'], coll, bottle, vertices=16))
    pieces.append(_cls_prop_cyl(name + '_cork', (0, 0, .268), .034, .037,
                                M['wood_light'], coll, bottle, vertices=12))
    pieces.append(_cls_prop_box(name + '_label', (0, -.086, .113), (.068, .008, .045),
                                M['paper'], coll, bottle, .008))
    pieces.append(_cls_prop_box(name + '_seal', (0, -.093, .113), (.018, .008, .024),
                                M['brass'], coll, bottle, .004))
    # 同色、同形瓶的部件共享几何，变体靠父级缩放产生。
    if shared is not None:
        key = color
        if key in shared:
            for ob, source in zip(pieces, shared[key]):
                old = ob.data
                ob.data = source.data
                if old.users == 0:
                    bpy.data.meshes.remove(old)
        else:
            shared[key] = pieces
    return bottle


def _cls_quill(name, pos, angle, M, coll, root):
    quill = empty(name + '_root', pos, coll)
    _cls_prop_parent(quill, root)
    quill.rotation_euler.z = angle
    _cls_prop_cyl(name + '_inkwell', (0, 0, .037), .058, .074, M['ink'], coll, quill)
    _cls_prop_cyl(name + '_rim', (0, 0, .08), .039, .014, M['brass'], coll, quill)
    points = [(0, 0, .075), (.025, .006, .17), (.085, .02, .30), (.16, .026, .44)]
    _cls_prop_tube(name + '_shaft', points, .005, M['brass'], coll, quill)
    verts = [(.025,.009,.17), (.014,.009,.26), (.025,.012,.34),
             (.080,.020,.41), (.16,.026,.44), (.127,.025,.34),
             (.107,.023,.25), (.065,.015,.18), (.085,.020,.30)]
    faces = [(8, i, (i+1) % 8) for i in range(8)]
    feather = mesh_obj(name + '_feather', verts, faces, M['paper'], coll)
    _cls_prop_parent(feather, quill)
    for i in range(4):
        z = .24+i*.035
        x = .055+i*.024
        _cls_prop_tube(name + '_barb', [(x-.035, .018, z+.025), (x, .021, z),
                                      (x+.027, .023, z-.025)],
                       .0018, M['wood_light'], coll, quill)


def _cls_crystal_triad(name, pos, M, coll, root):
    stand = empty(name + '_root', pos, coll)
    _cls_prop_parent(stand, root)
    _cls_prop_box(name + '_tray', (0, 0, .013), (.36, .17, .026), M['wood_dark'],
                  coll, stand, .03)
    for index, (x, r, mat) in enumerate(((-.112,.049,'magic_lilac'),
                                       (0,.060,'magic_blue'), (.112,.043,'star'))):
        _cls_prop_cyl(name + '_cup_' + str(index), (x, 0, .037), r*.78, .022,
                      M['brass'], coll, stand, vertices=16)
        _cls_prop_sphere(name + '_orb_' + str(index), (x, 0, .07+r*.4), (r,r,r),
                         M['glass'], coll, stand, 16, 8)
        _cls_prop_sphere(name + '_heart_' + str(index), (x, 0, .07+r*.4),
                         (r*.52,r*.52,r*.52), M[mat], coll, stand, 12, 6)


def _cls_student_desk(index, x, y, M, coll):
    root = empty('desk_%02d_root' % index, (x, y, 0), coll)
    for j in range(3):
        _cls_prop_box('desk_%02d_top_plank_%d' % (index,j), (0, (j-1)*.232, .735),
                      (1.9, .224, .09), M['wood_light'], coll, root, .045)
    for xx in (-.73, .73):
        for yy in (-.235,.235):
            _cls_prop_box('desk_%02d_leg' % index, (xx, yy, .355), (.085,.095,.70),
                          M['wood'], coll, root, .015, (0, -.035 if xx<0 else .035, 0))
            _cls_prop_cyl('desk_%02d_joinery_peg' % index, (xx, yy-.052, .61), .022,
                          .016, M['wood_dark'], coll, root, 12, (math.pi/2,0,0))
        _cls_prop_box('desk_%02d_end_stretcher' % index, (xx, 0, .20), (.075,.57,.07),
                      M['wood'], coll, root, .012)
    _cls_prop_box('desk_%02d_long_stretcher' % index, (0, .05, .24), (1.52,.07,.07),
                  M['wood_dark'], coll, root, .012)
    _cls_prop_box('desk_%02d_apron' % index, (0, -.285, .63), (1.62,.055,.11),
                  M['wood'], coll, root, .012)
    # 长凳的圆端、榫头与横撑在近景仍有结构。
    _cls_prop_box('bench_%02d_seat' % index, (0,-.75,.405), (1.48,.33,.09),
                  M['wood_light'], coll, root, .035)
    for xx in (-.74,.74):
        _cls_prop_cyl('bench_%02d_round_end' % index, (xx,-.75,.405), .165,.09,
                      M['wood_light'], coll, root, 24)
    for xx in (-.58,.58):
        for yy in (-.855,-.645):
            _cls_prop_box('bench_%02d_leg' % index, (xx,yy,.19), (.075,.075,.38),
                          M['wood'], coll, root, .012)
    _cls_prop_box('bench_%02d_stretcher' % index, (0,-.75,.14), (1.25,.065,.065),
                  M['wood_dark'], coll, root, .01)
    for xx in (-.61,.61):
        _cls_prop_box('bench_%02d_crosspiece' % index, (xx,-.75,.24), (.085,.35,.065),
                      M['wood'], coll, root, .012)
    _cls_open_book('desk_%02d_book' % index, (-.27,-.03,.785), .94,
                   (-.085,.04,.09,-.055,.03,-.12)[index], M, coll,
                   ('book_red','book_green','book_blue')[index % 3], root)
    _cls_quill('desk_%02d_quill' % index, (-.76,.12,.785), -.25+index*.13, M, coll, root)
    _cls_bottle('desk_%02d_potion' % index, (.67,.12,.785), .84+index*.025,
                ('liquid_a','liquid_b','liquid_c')[index % 3], M, coll, root)
    _cls_crystal_triad('desk_%02d_crystals' % index, (.41,-.14,.785), M, coll, root)
    return root


def _cls_bookcase(M, coll):
    root = empty('library_low_bookcase_root', (4.10,.48,0), coll)
    length = 4.95
    # 随右墙作剖切：省略背板，让主相机能看到藏书而不是封闭柜背。
    for yy in (-length/2, -length/6, length/6, length/2):
        _cls_prop_box('library_divider', (0,yy,1.10), (.62,.075,2.20),
                      M['wood'], coll, root, .025)
    for height in (.13,.635,1.14,1.645,2.16):
        _cls_prop_box('library_shelf', (-.005,0,height), (.65,length+.10,.075),
                      M['wood_light'], coll, root, .022)
        _cls_prop_box('library_shelf_moulding', (-.335,0,height-.015), (.035,length+.10,.09),
                      M['wood'], coll, root, .012)
    _cls_prop_box('library_crown', (0,0,2.215), (.70,length+.20,.09),
                  M['wood'], coll, root, .035)
    rng = random.Random(321)
    sources = [_cls_book_source('library_book_master_%d' % i, M[key], M, coll)
               for i,key in enumerate(('book_red','book_blue','book_green','wood_dark','purple'))]
    for row in range(4):
        for bay in range(3):
            for index in range(10):
                yy = -2.35 + bay*1.65 + index*.145
                src = sources[(index+row*2+bay) % len(sources)]
                _cls_book_instance(src, 'library_book_%d_%d_%02d' % (row,bay,index), coll,
                                   root, (-.02+rng.uniform(-.025,.025), yy,
                                          .17+row*.505),
                                   (rng.uniform(.77,.97), rng.uniform(1.02,1.30),
                                    rng.uniform(.81,1.03)), rz=math.pi/2,
                                   lean=rng.uniform(-.035,.035))
    for source in sources:
        bpy.data.objects.remove(source, do_unlink=True)
    return root


def _cls_elixir_cabinet(M, coll):
    root = empty('elixir_cabinet_root', (-3.70,4.20,.18), coll)
    _cls_prop_box('cabinet_back', (0,.25,1.14), (1.20,.075,2.26), M['wood_dark'], coll, root)
    for xx in (-.59,.59):
        _cls_prop_box('cabinet_carved_side', (xx,0,1.17), (.09,.59,2.32),
                      M['wood'], coll, root, .035)
        _cls_prop_box('cabinet_front_pilaster', (xx,-.31,1.15), (.105,.07,2.19),
                      M['wood_light'], coll, root, .018)
    for zz in (.12,.65,1.18,1.71,2.28):
        _cls_prop_box('cabinet_shelf', (0,-.015,zz), (1.22,.63,.075), M['wood'], coll, root)
        _cls_prop_box('cabinet_brass_edge', (0,-.34,zz), (1.18,.014,.023),
                      M['brass'], coll, root, .004)
    _cls_prop_box('cabinet_cornice', (0,0,2.36), (1.34,.72,.12),
                  M['wood_light'], coll, root, .035)
    shared = {}
    for row in range(4):
        for column in range(6):
            color = ('liquid_a','liquid_b','liquid_c')[(row+column)%3]
            _cls_bottle('cabinet_bottle_%d_%d' % (row,column),
                        (-.46+column*.184, -.05, .162+row*.53),
                        1.0+((column+row)%3)*.13, color, M, coll, root, shared)
    # 橱顶中心徽章与两侧小圆饰件。
    _cls_prop_cyl('cabinet_crest', (0,-.365,2.40), .105,.018, M['brass'],
                  coll, root, 32, (math.pi/2,0,0))
    _cls_prop_sphere('cabinet_crest_gem', (0,-.383,2.40), (.043,.018,.043),
                     M['magic_blue'], coll, root)
    return root


def _cls_teachers_desk(M, coll):
    root = empty('teachers_desk_root', (-.60,3.90,.18), coll)
    for i in range(4):
        _cls_prop_box('teacher_desktop_plank', (0,(i-1.5)*.20,.955), (2.0,.194,.09),
                      M['wood_light'], coll, root, .035)
    for xx in (-.79,.79):
        for yy in (-.25,.25):
            _cls_prop_box('teacher_desk_leg', (xx,yy,.455), (.13,.14,.91),
                          M['wood'], coll, root, .023)
            _cls_prop_cyl('teacher_leg_brass_foot', (xx,yy,.10), .078,.10,
                          M['brass'], coll, root, 16)
    _cls_prop_box('teacher_desk_front', (0,-.29,.70), (1.72,.10,.37), M['wood'], coll, root)
    for xx in (-.48,.48):
        _cls_prop_box('teacher_desk_drawer', (xx,-.355,.72), (.77,.045,.22),
                      M['wood_light'], coll, root, .025)
        _cls_prop_cyl('teacher_desk_pull', (xx,-.39,.72), .026,.04, M['brass'],
                      coll, root, 16, (math.pi/2,0,0))
    _cls_prop_box('teacher_desk_stretcher', (0,.18,.23), (1.70,.10,.10), M['wood_dark'], coll, root)
    _cls_open_book('teacher_grimoire', (-.13,-.03,1.005), 1.28, -.055, M, coll, 'book_blue', root)
    _cls_quill('teacher_quill', (-.78,.12,1.005), -.4, M, coll, root)
    _cls_bottle('teacher_ink_elixir', (.76,.08,1.005), 1.22, 'liquid_b', M, coll, root)
    _cls_prop_box('teacher_notes', (.58,-.13,1.01), (.28,.29,.014), M['paper'], coll, root, .008,
                  (0,0,.17))
    return root


def _cls_globe(M, coll):
    root = empty('terrestrial_globe_root', (1.25,4.50,.18), coll)
    _cls_prop_cyl('globe_base', (0,0,.06), .31,.12, M['wood_dark'], coll, root, 32)
    _cls_prop_cyl('globe_base_band', (0,0,.13), .25,.035, M['brass'], coll, root, 32)
    _cls_prop_cyl('globe_pedestal', (0,0,.48), .065,.70, M['wood'], coll, root)
    _cls_prop_sphere('globe_pedestal_knot', (0,0,.67), (.10,.10,.14), M['wood_light'], coll, root)
    globe = empty('globe_sphere_root', (0,0,1.12), coll)
    _cls_prop_parent(globe, root)
    globe.rotation_euler = (.12,.24,0)
    _cls_prop_sphere('globe_blue_world', (0,0,0), (.36,.36,.36), M['blue'], coll, globe, 32,16)
    for j in (-1,0,1):
        h = j*.16
        r = math.sqrt(.362**2-h*h)
        pts = [(r*math.cos(i*math.tau/64),r*math.sin(i*math.tau/64),h) for i in range(64)]
        _cls_prop_tube('globe_latitude', pts,.0035,M['brass'],coll,globe,True)
    for angle in (0,math.pi/3,2*math.pi/3):
        pts = [(math.cos(angle)*.362*math.cos(i*math.tau/64),
                math.sin(angle)*.362*math.cos(i*math.tau/64),
                .362*math.sin(i*math.tau/64)) for i in range(64)]
        _cls_prop_tube('globe_longitude', pts,.0035,M['brass'],coll,globe,True)
    # 抽象陆地沿球面铺展，使用厚度极小的曲面片。
    for n,(lon,lat) in enumerate(((-1.8,.3),(-.6,-.45),(.7,.5),(2.5,-.3))):
        verts = []
        for i in range(15):
            theta = i*math.tau/14
            a = lon + .37*math.cos(theta)*(1+.2*math.sin(theta*3+n))
            b = lat + .32*math.sin(theta)*(1+.2*math.cos(theta*4))
            verts.append((.365*math.cos(b)*math.cos(a), .365*math.cos(b)*math.sin(a), .365*math.sin(b)))
        verts.append((.365*math.cos(lat)*math.cos(lon),.365*math.cos(lat)*math.sin(lon),.365*math.sin(lat)))
        ob=mesh_obj('globe_land_%d'%n,verts,[(15,i,(i+1)%14) for i in range(14)],M['leaf2'],coll)
        _cls_prop_parent(ob,globe)
    pts=[(.45*math.cos(i*math.tau/72),0,.45*math.sin(i*math.tau/72)) for i in range(72)]
    _cls_prop_tube('globe_meridian_cradle',pts,.018,M['brass'],coll,globe,True)
    return root


def _cls_magic_plant(M, coll):
    root=empty('moonfern_root',(-3.3,-4.4,0),coll)
    _cls_prop_cyl('moonfern_pot',(0,0,.21),.32,.42,M['pot'],coll,root,32,radius2=.25)
    _cls_prop_cyl('moonfern_pot_rim',(0,0,.42),.34,.075,M['pot'],coll,root,32)
    _cls_prop_cyl('moonfern_soil',(0,0,.447),.295,.025,M['wood_dark'],coll,root,32)
    for n in range(11):
        angle=n*2.39996
        height=.72+(n%3)*.12
        outward=.32+(n%2)*.12
        end=Vector((math.cos(angle)*outward,math.sin(angle)*outward,height))
        start=Vector((0,0,.44))
        mid=start.lerp(end,.55)+Vector((0,0,.12))
        _cls_prop_tube('moonfern_stem',[start,mid,end],.009,M['leaf'],coll,root)
        # 舟形叶片中央拱起，叶脉与发光尖端提供可读轮廓。
        tangent=Vector((-math.sin(angle),math.cos(angle),0))
        tip=end+Vector((math.cos(angle)*.15,math.sin(angle)*.15,.09))
        base=mid.lerp(end,.25)
        center=base.lerp(tip,.55)+Vector((0,0,.055))
        verts=[tuple(base),tuple(center+tangent*.105),tuple(tip),tuple(center-tangent*.105),tuple(center)]
        ob=mesh_obj('moonfern_leaf_%d'%n,verts,[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],
                    M['leaf2' if n%2 else 'leaf'],coll)
        _cls_prop_parent(ob,root)
        _cls_prop_tube('moonfern_vein',[base,center,tip],.004,M['plant_glow'],coll,root)
        if n%3==0:
            _cls_prop_sphere('moonfern_luminous_seed',tuple(tip),(.028,.028,.043),
                             M['plant_glow'],coll,root,12,6)
    return root


def build_furniture(M, C):
    """六套桌凳；最后一排右桌及其所有小物归入 FG。"""
    roots=[]
    for row,y in enumerate((1.70,-.50,-2.70)):
        for col,x in enumerate((-1.60,1.60)):
            coll=C['fg'] if row==2 and col==1 else C['furniture']
            roots.append(_cls_student_desk(row*2+col,x,y,M,coll))
    roots.append(_cls_bookcase(M,C['furniture']))
    roots.append(_cls_elixir_cabinet(M,C['furniture']))
    roots.append(_cls_teachers_desk(M,C['furniture']))
    roots.append(_cls_globe(M,C['furniture']))
    roots.append(_cls_magic_plant(M,C['furniture']))
    return roots


def _cls_candle(name, pos, height, phase, M, coll, floating=False):
    root=empty(name+'_root',pos,coll)
    _cls_prop_cyl(name+'_saucer',(0,0,.015),.105,.027,M['brass'],coll,root,24)
    _cls_prop_cyl(name+'_saucer_foot',(0,0,-.013),.046,.037,M['metal'],coll,root,16)
    _cls_prop_cyl(name+'_wax',(0,0,height*.5+.032),.052,height,M['paper'],coll,root,20)
    for n in range(4):
        angle=n*1.7+phase
        z=height+.025-(n%3)*.025
        _cls_prop_sphere(name+'_wax_drip',(math.cos(angle)*.047,math.sin(angle)*.047,z),
                         (.015,.015,.045+(n%2)*.022),M['paper'],coll,root,12,6)
    _cls_prop_cyl(name+'_wick',(0,0,height+.055),.006,.036,M['ink'],coll,root,8)
    flame=_cls_prop_sphere(name+'_flame',(0,0,height+.128),(.032,.032,.084),
                            M['flame'],coll,root,16,8)
    register_flame(flame,phase=phase)
    core=_cls_prop_sphere(name+'_flame_heart',(0,0,height+.106),(.015,.015,.042),
                           M['star'],coll,root,12,6)
    register_flame(core,phase=phase+.15)
    if floating:
        register_float(root,amp=.065+height*.08,phase=phase,spin=.08)
    return root


def _cls_orrery(M,coll):
    root=empty('orrery_root',(0,-3.20,3.90),coll)
    # 球形日心、三条倾斜轨道、七颗具有不同尺度的行星。
    _cls_prop_sphere('orrery_sun',(0,0,0),(.15,.15,.15),M['star'],coll,root,24,12)
    _cls_prop_cyl('orrery_axis',(0,0,.09),.017,.65,M['brass'],coll,root,16)
    _cls_prop_sphere('orrery_axis_finial',(0,0,.43),(.042,.042,.075),M['brass'],coll,root)
    radii=(.48,.73,1.02)
    angles=((.18,.16,0),(-.3,.18,.2),(.21,-.2,-.15))
    matrices=[Euler(a,'XYZ').to_matrix() for a in angles]
    for n,radius in enumerate(radii):
        points=[tuple(matrices[n]@Vector((radius*math.cos(i*math.tau/96),
                                         radius*math.sin(i*math.tau/96),0))) for i in range(96)]
        _cls_prop_tube('orrery_orbit_%d'%n,points,.011,M['brass'],coll,root,True)
    mats=('magic_blue','purple','leaf2','book_red','blue','wood_light','magic_lilac')
    for n in range(7):
        orbit=0 if n<2 else 1 if n<4 else 2
        angle=n*2.39996+.35
        pos=matrices[orbit]@Vector((radii[orbit]*math.cos(angle),radii[orbit]*math.sin(angle),0))
        radius=(.045,.056,.066,.052,.091,.072,.047)[n]
        _cls_prop_sphere('orrery_planet_%d'%n,tuple(pos),(radius,)*3,M[mats[n]],coll,root,20,10)
        if n in (4,5):
            points=[tuple(pos+matrices[orbit]@Vector((radius*1.8*math.cos(i*math.tau/40),
                                                    radius*1.8*math.sin(i*math.tau/40),0))) for i in range(40)]
            _cls_prop_tube('orrery_planet_ring_%d'%n,points,.006,M['brass'],coll,root,True)
    # 三条短悬索收束于顶端吊环，不跨过投影保护区域。
    for angle in (0,math.tau/3,math.tau*2/3):
        _cls_prop_tube('orrery_suspension',[(.56*math.cos(angle),.56*math.sin(angle),.13),
                                         (.14*math.cos(angle),.14*math.sin(angle),.57),
                                         (0,0,.67)],.006,M['metal'],coll,root)
    points=[(.066*math.cos(i*math.tau/32),0,.70+.066*math.sin(i*math.tau/32)) for i in range(32)]
    _cls_prop_tube('orrery_hanging_loop',points,.010,M['brass'],coll,root,True)
    register_float(root,amp=.03,phase=.3,spin=math.tau)
    return root


def build_magic_props(M,C):
    coll=C['magic']
    roots=[]
    placements=[(-1.78,-2.1,2.85,.76,-.34,.17),
                (.32,-1.40,2.72,.83,.22,-.13),
                (1.75,-2.52,3.18,.72,-.2,.13),
                (-.78,-3.38,3.16,.78,.44,-.18)]
    for n,(x,y,z,size,rz,rx) in enumerate(placements):
        root=_cls_open_book('floating_grimoire_%d'%n,(x,y,z),size,rz,M,coll,
                             ('book_red','book_blue','book_green','purple')[n])
        root.rotation_euler.x=rx
        root.rotation_euler.y=(-.14,.17,-.1,.12)[n]
        register_float(root,amp=.075+n*.012,phase=n*1.43,spin=.14*(-1 if n%2 else 1))
        roots.append(root)
    candle_positions=[(-1.90,-1.10,3.06),(-1.05,-1.12,3.48),(.02,-.92,3.34),
                      (1.10,-1.13,3.46),(1.90,-1.43,2.85),(-1.61,-2.90,3.53),
                      (-.53,-2.50,2.89),(.72,-2.71,2.82),(1.60,-3.40,3.55),
                      (-1.70,-3.42,2.93)]
    for n,pos in enumerate(candle_positions):
        roots.append(_cls_candle('floating_candle_%02d'%n,pos,.16+(n%3)*.045,
                                  n*.71,M,coll,True))
    roots.append(_cls_orrery(M,coll))
    # 六支固定蜡烛位于讲桌与低书架，顶部火焰仍参加循环动画。
    for n,pos in enumerate(((-1.45,3.58,1.18),(.17,3.58,1.18),
                            (4.04,-1.90,2.265),(4.04,-1.50,2.265),
                            (4.04,-1.10,2.265),(4.04,-.70,2.265))):
        _cls_candle('stationary_candle_%02d'%n,pos,.17+(n%3)*.055,n*.87,
                     M,C['furniture'],False)
    return roots


# ==================== 机位与屏幕留白 ====================
def room_world(p):
    return ROOM_ROOT.matrix_world @ Vector(p)


def aim(ob,target):
    ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()


def camera_object(name,kind,lens=35):
    data=bpy.data.cameras.new(name);data.type=kind;data.lens=lens;data.clip_start=.05;data.clip_end=150
    ob=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(ob)
    return ob


def build_cameras():
    sc=bpy.context.scene;bpy.context.view_layer.update()
    target=room_world((0,0,2))
    az,el=map(math.radians,(CAM_AZIMUTH,CAM_ELEVATION))
    main=camera_object('cls_CAM_main','ORTHO')
    main.location=target+Vector((math.sin(az)*math.cos(el),-math.cos(az)*math.cos(el),math.sin(el)))*30
    aim(main,target);sc.camera=main;main.data.ortho_scale=20
    # 根据房间包围盒自动拟合；内容区域的左界为 17%，给桌面图标预留15%。
    pts=[room_world((x,y,z)) for x in (-4.8,4.8) for y in (-5.8,5.8) for z in (-.22,5.8)]
    bpy.context.view_layer.update()
    rect=project_points(pts)
    factor=max((rect[2]-rect[0])/.79,(rect[3]-rect[1])/.86)
    main.data.ortho_scale*=factor
    bpy.context.view_layer.update();rect=project_points(pts)
    main.data.shift_x+=(rect[0]+rect[2])/2-.575
    main.data.shift_y+=((rect[1]+rect[3])/2-.5)/(RES_X/RES_Y)
    persp=camera_object('CAM_persp','PERSP',35)
    persp.location=room_world((5.8,-10.5,5.5));aim(persp,room_world((-.4,1,1.7)))
    close=camera_object('CAM_closeup','PERSP',85)
    close.location=room_world((3,-2.9,2.8));aim(close,room_world((3,3.9,1.65)))
    close.data.dof.use_dof=True;close.data.dof.aperture_fstop=5.6
    focus=empty('cls_closeup_focus',(3,3.9,1.65),C['markers']);close.data.dof.focus_object=focus
    return main


def project_points(points):
    sc=bpy.context.scene
    ps=[world_to_camera_view(sc,sc.camera,p) for p in points]
    return (min(p.x for p in ps),min(p.y for p in ps),max(p.x for p in ps),max(p.y for p in ps))


def object_rect(ob, deps=None):
    ob=ob.evaluated_get(deps) if deps else ob
    return project_points([ob.matrix_world @ Vector(c) for c in ob.bound_box])


def union_rect(rects):
    return (min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects))


def overlap(a,b,pad=.006):
    return a[0]<b[2]+pad and a[2]>b[0]-pad and a[1]<b[3]+pad and a[3]>b[1]-pad


def protected_rects():
    board=bpy.data.objects['cls_board_ui_panel']
    c1=project_points([room_world((3+dx,3.9+dy,.18+z)) for dx in (-.75,.75) for dy in (-.75,.75) for z in (0,2.4)])
    return object_rect(board),c1


def descendants(root):
    return [o for o in root.children_recursive if o.type in {'MESH','CURVE','FONT'}]


def arrange_magic():
    # 投影上的安全摆放：每个动画组使用静态包围盒+最大浮动扩张。
    bpy.context.view_layer.update();protected=protected_rects()
    for idx,root in enumerate(FLOATS):
        parts=descendants(root)
        def clear():
            if not parts:return True
            r=union_rect([object_rect(o) for o in parts]);amp=root.get('cls_amp',.08)
            pad=.025+amp/bpy.context.scene.camera.data.ortho_scale
            return r[0]>=LEFT_SAFE+.018 and r[2]<.985 and r[1]>.06 and r[3]<.95 and not any(overlap(r,p,pad) for p in protected)
        if clear():continue
        original=root.location.copy()
        found=False
        # 后半部、偏左或中央：沿镜头下方分布，保留完整黑板与 C1 轮廓。
        for y in (-3.9,-4.5,-3.0,-2.0):
            for x in (-1.8,-.4,1.1,2.4):
                root.location=(x,y,original.z)
                bpy.context.view_layer.update()
                if clear():found=True;break
            if found:break
        if not found:
            root.location=original
            log('动态组需要逐帧检查调整：'+root.name)
    bpy.context.view_layer.update()


# ==================== 动画，分层 Action 与旧版 4.x 兼容 ====================
def action_curves(idblock):
    ad=idblock.animation_data
    if not ad or not ad.action:return []
    action=ad.action
    if hasattr(action,'layers') and len(action.layers):
        curves=[]
        for layer in action.layers:
            for strip in layer.strips:
                if not hasattr(strip,'channelbags'):continue
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
        return curves
    return list(action.fcurves) if hasattr(action,'fcurves') else []


def key_loop(idblock,path,index,fn,step=8):
    # 三次 Hermite 手柄，边界导数显式匹配；第193帧等于第1帧的状态。
    for frame in range(1,LOOP_FRAMES+2,step):
        value=fn(frame)
        if index is None:setattr(idblock,path,value)
        else:getattr(idblock,path)[index]=value
        idblock.keyframe_insert(data_path=path,index=-1 if index is None else index,frame=frame)
    for fc in action_curves(idblock):
        if fc.data_path!=path or (index is not None and fc.array_index!=index):continue
        for kp in fc.keyframe_points:
            f=kp.co.x;dy=(fn(f+.001)-fn(f-.001))/.002
            kp.interpolation='BEZIER';kp.handle_left_type='FREE';kp.handle_right_type='FREE'
            kp.handle_left=(f-step/3,fn(f)-dy*step/3);kp.handle_right=(f+step/3,fn(f)+dy*step/3)
        if not any(md.type=='CYCLES' for md in fc.modifiers):fc.modifiers.new('CYCLES')
    if index is None:setattr(idblock,path,fn(1))
    else:getattr(idblock,path)[index]=fn(1)


def build_animation():
    sc=bpy.context.scene;sc.frame_start=1;sc.frame_end=LOOP_FRAMES;sc.render.fps=FPS
    w=2*math.pi/LOOP_FRAMES
    for root in FLOATS:
        z=root.location.z;p=root['cls_phase'];amp=root['cls_amp'];spin=root['cls_spin'];base=root.rotation_euler.z
        key_loop(root,'location',2,lambda f,z=z,p=p,a=amp:z+a*math.sin(w*(f-1)+p))
        if abs(spin)>=6:
            key_loop(root,'rotation_euler',2,lambda f,b=base:b+2*math.pi*(f-1)/LOOP_FRAMES)
        else:
            key_loop(root,'rotation_euler',2,lambda f,b=base,p=p,s=spin:b+s*math.sin(w*(f-1)+p))
    for ob in FLAMES:
        ob.rotation_mode='XYZ';p=ob['cls_phase'];z=ob.scale.z;x=ob.scale.x
        key_loop(ob,'scale',2,lambda f,p=p,z=z:z*(1+.11*math.sin(5*w*(f-1)+p)+.045*math.sin(11*w*(f-1))))
        key_loop(ob,'scale',0,lambda f,p=p,x=x:x*(1+.06*math.sin(7*w*(f-1)+p)))
    sc.frame_set(1)


def build_dust():
    rnd=random.Random(SEED+93)
    proto=sphere('dust_000',(0,0,0),(.011,.011,.011),M['star'],C['fx'],segments=8,rings=4)
    for i in range(DUST_COUNT):
        if i==0:ob=proto
        else:
            ob=bpy.data.objects.new('cls_dust_%03d'%i,proto.data);attach(ob,C['fx'])
        p=rnd.uniform(0,2*math.pi);base=(rnd.uniform(-2.6,2.8),rnd.uniform(-4.8,2),rnd.uniform(.6,3))
        ob.location=base
        # 同一网格的链接实例；内置数学表达式驱动，无需加载 Python handler。
        for axis,amp,k in ((0,.12,1),(1,.07,2),(2,.15,1)):
            fc=ob.driver_add('location',axis)
            fc.driver.expression=f'{base[axis]:.7f}+{amp}*sin(2*pi*{k}*(frame-1)/192+{p:.7f})'
        ob['cls_dust']=True


def validate_clearance():
    sc=bpy.context.scene;hits=[]
    # 网格和曲线的求值包围盒，包含倒角/父子层级/动画。逐帧而非抽样。
    groups=[(r,descendants(r)) for r in FLOATS]
    inside={p.name for root,parts in groups for p in parts}
    groups += [(o,[o]) for o in bpy.context.scene.objects if o.name not in inside and (o.get('cls_flame') or o.get('cls_dust'))]
    for f in range(1,LOOP_FRAMES+1):
        sc.frame_set(f);deps=bpy.context.evaluated_depsgraph_get();protected=protected_rects()
        for root,parts in groups:
            rect=union_rect([object_rect(o,deps) for o in parts])
            for i,p in enumerate(protected):
                if overlap(rect,p,.004):hits.append((f,root.name,'UI' if i==0 else 'C1'))
    sc.frame_set(1)
    sc['cls_clearance_frames']=192;sc['cls_clearance_hits']=len(hits)
    sc['cls_ui_min_x']=protected_rects()[0][0]
    if hits:raise RuntimeError('动态遮挡不合格：'+str(hits[:12]))
    assert sc['cls_ui_min_x']>=LEFT_SAFE, '黑板进入左侧图标区'
    log('PASS：192 帧悬浮物、火苗、光尘对黑板 UI / C1 投影重叠 = 0')


# ==================== 时段、真实灯光与后期 ====================
def build_lighting():
    sc=bpy.context.scene
    world=bpy.data.worlds.new('cls_World');sc.world=world
    if bpy.app.version<(5,0,0):world.use_nodes=True
    nd=world.node_tree.nodes;nd.clear();bg=nd.new('ShaderNodeBackground');bg.name='cls_WorldColor'
    out=nd.new('ShaderNodeOutputWorld');world.node_tree.links.new(bg.outputs[0],out.inputs[0])
    sun=bpy.data.lights.new('cls_Sun','SUN');sun.angle=math.radians(3.5)
    ob=bpy.data.objects.new('cls_Sun',sun);C['lights'].objects.link(ob)
    # 窗口补光使灰泥和地板接收到真实暖光；发光材质不替代光源。
    for i,y in enumerate((-2.8,.3,3.4)):
        ld=bpy.data.lights.new('cls_window_area_%d'%i,'AREA');ld.shape='DISK';ld.size=3
        ob=attach(bpy.data.objects.new(ld.name,ld),C['lights'],(-4.9,y,3.1))
        ob.rotation_euler=(Vector((1.8,y-1.8,.4))-ob.location).to_track_quat('-Z','Y').to_euler()
        ob['cls_powers']={'morning':230,'noon':330,'night':55};ob['cls_window_light']=True;LIGHTS.append(ob)
    for i,(pos,col,powers) in enumerate((
        ((-.6,3.5,2.5),(1,.65,.28),dict(morning=25,noon=12,night=180)),
        ((-3.45,3.8,1.7),(.65,.52,1),dict(morning=8,noon=4,night=65)),
        ((0,-2.3,3.1),(1,.72,.38),dict(morning=25,noon=10,night=230)),
        ((2.2,-3.4,1.7),(1,.67,.3),dict(morning=15,noon=5,night=100)),
        ((-1.7,.8,1.4),(1,.72,.4),dict(morning=10,noon=3,night=90)),
        ((-3.25,-4.3,.8),(.4,.82,.64),dict(morning=3,noon=2,night=35)),
        ((-.4,4.8,2.8),(.55,.48,1),dict(morning=5,noon=3,night=45)))):
        ob=add_point('practical_%d'%i,pos,col,powers,.6)
        if i in (0,2,3,4):
            fc=ob.data.driver_add('energy');drv=fc.driver;v=drv.variables.new();v.name='base'
            v.targets[0].id=ob;v.targets[0].data_path='["cls_base_power"]'
            drv.expression=f'base*(1+0.05*sin(2*pi*5*(frame-1)/192+{i}))'
    # 室内局部淡雾：不会在窗洞外继续延伸。
    mat=_new_material('cls_haze');nt=mat.node_tree
    v=nt.nodes.new('ShaderNodeVolumeScatter');v.name='Haze';v.inputs['Anisotropy'].default_value=.48
    out=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(v.outputs['Volume'],out.inputs['Volume'])
    box('haze',(-.1,0,2.4),(8.6,10.7,4.7),mat,C['fx'],bevel=0)


def setup_render():
    sc=bpy.context.scene
    for engine in ('BLENDER_EEVEE_NEXT','BLENDER_EEVEE'):
        try:sc.render.engine=engine;break
        except TypeError:pass
    sc.render.resolution_x=RES_X;sc.render.resolution_y=RES_Y;sc.render.resolution_percentage=100
    sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGBA';sc.render.image_settings.color_depth='8'
    sc.render.film_transparent=True
    sc.view_settings.view_transform='AgX'
    for look in ('AgX - Punchy','Punchy','AgX - Medium High Contrast','None'):
        try:sc.view_settings.look=look;break
        except (TypeError,ValueError):continue
    sc.view_settings.exposure=.4
    ee=sc.eevee
    for attr,val in dict(taa_render_samples=SAMPLES,use_raytracing=RAYTRACE,ray_tracing_method='SCREEN',
        shadow_ray_count=2,shadow_step_count=8,volumetric_start=.1,volumetric_end=65,
        volumetric_tile_size=VOLUME_TILE,volumetric_samples=VOLUME_SAMPLES,use_volumetric_shadows=True,
        volumetric_shadow_samples=16).items():
        if hasattr(ee,attr):setattr(ee,attr,val)
        else:log('API 无此选项，使用本版本默认：'+attr)
    if hasattr(ee,'ray_tracing_options'):ee.ray_tracing_options.resolution_scale='2'
    sc.render.use_file_extension=True
    log(f'引擎 {sc.render.engine}, Look {sc.view_settings.look}, samples={SAMPLES}')


def setup_layers():
    sc=bpy.context.scene
    base=sc.view_layers[0];base.name='BG'
    for layer in list(sc.view_layers)[1:]:sc.view_layers.remove(layer)
    fg=sc.view_layers.new('FG');ch=sc.view_layers.new('CHAR')
    # BG 是完整场景预览；FG 独立前景彩色素材，CHAR中将FG作为holdout。
    for key,coll in C.items():
        if key=='char':continue
        node=fg.layer_collection.children.get(coll.name)
        if node and key not in ('fg','lights','markers'):node.holdout=True
        node=ch.layer_collection.children.get(coll.name)
        if node and key not in ('char','lights','markers','fg'):node.exclude=True
    ch.layer_collection.children[C['fg'].name].holdout=True
    fg.use=False;ch.use=False
    bpy.context.window.view_layer=base


def setup_compositor():
    sc=bpy.context.scene
    if hasattr(sc,'compositing_node_group'):
        nt=bpy.data.node_groups.new('cls_Compositor','CompositorNodeTree');sc.compositing_node_group=nt
        nt.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
        out=nt.nodes.new('NodeGroupOutput');dest=out.inputs['Image']
    else:
        sc.use_nodes=True;nt=sc.node_tree;nt.nodes.clear();out=nt.nodes.new('CompositorNodeComposite');dest=out.inputs['Image']
    rl=nt.nodes.new('CompositorNodeRLayers');rl.layer='BG';rl.location=(-500,0)
    glare=nt.nodes.new('CompositorNodeGlare');glare.name='cls_Bloom';glare.location=(-250,0)
    if 'Type' in glare.inputs:
        glare.inputs['Type'].default_value='Bloom';glare.inputs['Threshold'].default_value=.9
        glare.inputs['Size'].default_value=.6
    else:
        try:glare.glare_type='BLOOM'
        except TypeError:glare.glare_type='FOG_GLOW'
        glare.threshold=.9;glare.quality='HIGH';glare.size=8
    nt.links.new(rl.outputs['Image'],glare.inputs['Image'])
    # 保留输入alpha；不会让Bloom把透明窗洞变成不透明色块。
    alpha=nt.nodes.new('CompositorNodeSetAlpha');alpha.location=(0,0)
    if 'Type' in alpha.inputs:alpha.inputs['Type'].default_value='Replace Alpha'
    else:alpha.mode='REPLACE_ALPHA'
    nt.links.new(glare.outputs['Image'],alpha.inputs['Image']);nt.links.new(rl.outputs['Alpha'],alpha.inputs['Alpha'])
    nt.links.new(alpha.outputs['Image'],dest);out.location=(220,0)
    sc.render.use_compositing=True


def rebind():
    global ROOM_ROOT,TOON,C
    ROOM_ROOT=bpy.data.objects.get('cls_room_root');TOON=bpy.data.node_groups.get('cls_ToonCore')
    GLOW_MATS.clear();LIGHTS.clear();FLOATS.clear();FLAMES.clear()
    for mat in bpy.data.materials:
        if mat.get('gsd_strengths') is not None:GLOW_MATS.append((mat,dict(mat['gsd_strengths'])))
    for ob in bpy.data.objects:
        if ob.get('cls_powers') is not None:LIGHTS.append(ob)
        if ob.get('cls_float'):FLOATS.append(ob)
        if ob.get('cls_flame'):FLAMES.append(ob)
    C={k:bpy.data.collections.get('cls_'+k) for k in ('architecture','furniture','magic','fx','fg','lights','backdrop','markers')}
    C['char']=bpy.data.collections.get('cls_CHAR')


def set_backdrop(show):
    sc=bpy.context.scene;sc['cls_show_backdrop']=bool(show)
    coll=bpy.data.collections.get('cls_backdrop')
    if coll:
        for ob in list(coll.all_objects):ob.hide_render=not show;ob.hide_set(not show)
    # 后期合成模式只保留真正透明的窗口，去掉沿相机射线覆盖窗洞的室内雾。
    haze=bpy.data.objects.get('cls_haze')
    if haze:haze.hide_render=not show
    log('窗外背景 '+('开启' if show else '关闭（RGBA透明窗口，体积雾同步关闭）'))


def apply_time(t):
    if t not in TIMES:raise ValueError('时段必须为 morning / noon / night')
    sc=bpy.context.scene;cfg=TIMES[t]
    if not LIGHTS:rebind()
    sun=bpy.data.objects['cls_Sun'];sun.rotation_euler=Euler((math.radians(90-cfg['el']),0,math.radians(cfg['az'])),'XYZ')
    sun.data.color=lin(cfg['sun']);sun.data.energy=cfg['power']
    bg=sc.world.node_tree.nodes['cls_WorldColor'];bg.inputs['Color'].default_value=(*lin(cfg['sky']),1)
    bg.inputs['Strength'].default_value=cfg['sky_power']
    if TOON:TOON.nodes['TimeTint'].outputs[0].default_value=(*lin(cfg['tint']),1)
    for mat,strength in GLOW_MATS:
        em=next(n for n in mat.node_tree.nodes if n.type=='EMISSION');em.inputs['Strength'].default_value=strength[t]
    for ob in LIGHTS:
        power=ob['cls_powers'][t];ob['cls_base_power']=power
        if not ob.data.animation_data or not ob.data.animation_data.drivers:ob.data.energy=power
        if ob.get('cls_window_light'):ob.data.color=lin(cfg['sun'])
    skycols={'morning':((.86,.73,.62),(.37,.54,.52),(.56,.65,.62)),
        'noon':((.48,.72,.86),(.28,.50,.46),(.44,.61,.63)),
        'night':((.065,.105,.24),(.10,.20,.26),(.16,.27,.36))}
    for key,col in zip(('backdrop_sky','backdrop_island','backdrop_far'),skycols[t]):
        mat=bpy.data.materials.get('cls_'+key)
        if mat:
            em=next(n for n in mat.node_tree.nodes if n.type=='EMISSION');em.inputs['Color'].default_value=(*lin(col),1)
    haze=bpy.data.materials['cls_haze'].node_tree.nodes['Haze']
    haze.inputs['Density'].default_value=cfg['haze']*HAZE_MULTIPLIER;haze.inputs['Color'].default_value=(*lin(cfg['haze_col']),1)
    nt=sc.compositing_node_group if hasattr(sc,'compositing_node_group') else sc.node_tree
    glare=nt.nodes['cls_Bloom']
    if 'Strength' in glare.inputs:glare.inputs['Strength'].default_value=cfg['bloom']
    else:glare.mix=max(-1,min(1,cfg['bloom']-1))
    sc['cls_time']=t;sc.frame_set(sc.frame_current);bpy.context.view_layer.update()
    log('时段 '+t)


# ==================== 统计、验证和交付 ====================
def validate_board_visibility():
    sc=bpy.context.scene;sc.frame_set(1);deps=bpy.context.evaluated_depsgraph_get()
    ui=bpy.data.objects['cls_board_ui_panel']
    # 以实际UI表面网格作采样，从正交相机平行发射射线。
    corners=[ui.matrix_world @ v.co for v in ui.data.vertices]
    cam=sc.camera;direction=cam.rotation_euler.to_matrix() @ Vector((0,0,-1))
    failures=[]
    # 由四边面顶点双线性取点，避开面边界的浮点误差。
    for i in range(9):
        for j in range(7):
            u=.02+.96*i/8;v=.02+.96*j/6
            p=(corners[0]*(1-u)+corners[1]*u)*(1-v)+(corners[3]*(1-u)+corners[2]*u)*v
            origin=p-direction*40
            hit,loc,norm,face,ob,matrix=sc.ray_cast(deps,origin,direction,distance=40.02)
            # 雾体无表面，会被几何射线命中；验证时显式跳过。
            skips=0
            while hit and ob and ob.name.startswith(('cls_haze','cls_dust')) and skips<8:
                origin=loc+direction*.03
                hit,loc,norm,face,ob,matrix=sc.ray_cast(deps,origin,direction,distance=(p-origin).length+.02);skips+=1
            if not hit or ob.name!=ui.name:failures.append(ob.name if ob else 'no hit')
    sc['cls_ui_static_ray_failures']=len(failures)
    if failures:raise RuntimeError('黑板UI可见性射线检查失败：'+str(failures[:8]))
    log('PASS：黑板UI 63个采样点均无遮挡')


def scene_stats():
    deps=bpy.context.evaluated_depsgraph_get();triangles=0
    for inst in deps.object_instances:
        ob=inst.object
        if ob.type not in {'MESH','CURVE','FONT'}:continue
        mesh=ob.to_mesh()
        if mesh:
            triangles+=sum(max(0,len(p.vertices)-2) for p in mesh.polygons)
            ob.to_mesh_clear()
    bpy.context.scene['cls_evaluated_triangles']=triangles
    if triangles>MAX_TRIANGLES:raise RuntimeError(f'面数超预算：{triangles}')
    log(f'物体 {len(bpy.context.scene.objects)}；评估三角面（包含实例/修改器）{triangles:,}')
    return triangles


def save_scene():
    sc=bpy.context.scene;sc.render.resolution_percentage=100
    # 内嵌完整脚本，以attach模式运行即可重新获得 apply_time，不重建。
    sourcepath=globals().get('__file__')
    if sourcepath and os.path.isfile(sourcepath):
        source=open(sourcepath,encoding='utf-8').read()
        text=bpy.data.texts.get('magic_classroom.py') or bpy.data.texts.new('magic_classroom.py')
        text.clear();text.write('CLASSROOM_ATTACH = True\n'+source)
        text.use_module=False
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    log('保存 '+BLEND_PATH)


def preview():
    sc=bpy.context.scene;old=sc.render.resolution_percentage;current=sc.get('cls_time','morning')
    times={}
    try:
        sc.render.resolution_percentage=PREVIEW_PERCENT
        for t in ('morning','noon','night'):
            apply_time(t);sc.frame_set(1);start=time.perf_counter()
            sc.render.filepath=os.path.join(RENDER_DIR,'classroom_'+t+'.png')
            bpy.ops.render.render(write_still=True,layer='BG')
            times[t]=round(time.perf_counter()-start,2)
            log(f'预览 {t}: {times[t]} 秒，{sc.render.filepath}')
    finally:
        sc.render.resolution_percentage=old;apply_time(current)
    return times


def build():
    global ROOM_ROOT,C,M,START
    START=time.perf_counter();random.seed(SEED)
    with open(LOG_PATH,'w',encoding='utf-8') as f:f.write('共生岛 · 魔法教室构建日志\n')
    log('Blender '+bpy.app.version_string)
    # 本脚本建立独立新文件；不执行原岛屿脚本，不加载人物资源。
    for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
    for coll in list(bpy.data.collections):bpy.data.collections.remove(coll)
    for blocks in (bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.actions,bpy.data.node_groups):
        for block in list(blocks):
            if block.users==0:blocks.remove(block)
    GLOW_MATS.clear();LIGHTS.clear();FLOATS.clear();FLAMES.clear();ROOM_ROOT=None
    C={key:new_collection(key) for key in ('architecture','furniture','magic','fx','fg','lights','backdrop','markers')}
    C['char']=new_collection('CHAR')
    ROOM_ROOT=empty('room_root',(0,0,0),C['markers']);ROOM_ROOT.rotation_euler.z=math.radians(ROOM_ROTATION)
    M=build_materials();setup_render()
    build_architecture(M,C);build_board(M,C);build_backdrop(M,C)
    build_furniture(M,C);build_magic_props(M,C)
    for name,loc in (('CHAR_SPOT_1',(3,3.9,.18)),('CHAR_SPOT_2',(-3.4,.2,0))):
        spot=empty(name,loc,C['markers']);spot.empty_display_type='CIRCLE';spot.empty_display_size=.7
    build_cameras();build_lighting();setup_layers();setup_compositor()
    set_backdrop(SHOW_BACKDROP);apply_time(DEFAULT_TIME)
    arrange_magic();build_animation();build_dust()
    bpy.context.scene['cls_board_ui_ratio']=.60
    validate_clearance();validate_board_visibility();triangles=scene_stats()
    sc=bpy.context.scene
    for area in (bpy.context.screen.areas if bpy.context.screen else []):
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.shading.type='SOLID'
    build_seconds=round(time.perf_counter()-START,2);sc['cls_build_seconds']=build_seconds
    save_scene()
    renders=preview() if RENDER_PREVIEWS else {}
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_gib=rss/(1024**3 if sys.platform=='darwin' else 1024**2)
    sc['cls_peak_rss_gib']=rss_gib
    # 输出统计独立于场景，保存后的默认设置始终为全尺寸、原时段。
    report=dict(blender=bpy.app.version_string,build_seconds=build_seconds,render_seconds=renders,
        peak_process_rss_gib=round(rss_gib,3),triangles=triangles,objects=len(sc.objects),
        resolution=[RES_X,RES_Y],preview_percent=PREVIEW_PERCENT,samples=SAMPLES,
        clearance_frames=192,clearance_hits=0,ui_static_ray_failures=sc['cls_ui_static_ray_failures'])
    with open(os.path.join(RENDER_DIR,'classroom_stats.json'),'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    log('运行统计 '+json.dumps(report,ensure_ascii=False))
    save_scene();log('构建与交付完成')
    return sc


class _ClassroomAPI:
    apply_time=staticmethod(apply_time)
    set_backdrop=staticmethod(set_backdrop)
    preview=staticmethod(preview)
    validate_clearance=staticmethod(validate_clearance)
    rebuild=staticmethod(build)

import builtins
builtins.cls=_ClassroomAPI
bpy.app.driver_namespace['cls']=_ClassroomAPI
if globals().get('CLASSROOM_ATTACH'):
    rebind()
elif __name__=='__main__':
    try:build()
    except Exception:
        log(traceback.format_exc())
        raise
