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
