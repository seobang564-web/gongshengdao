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
