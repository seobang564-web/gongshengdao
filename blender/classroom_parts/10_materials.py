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
