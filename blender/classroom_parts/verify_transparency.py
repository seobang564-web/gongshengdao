import bpy, os
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sc=bpy.context.scene
ns={'__name__':'classroom_attach','CLASSROOM_ATTACH':True,'__file__':os.path.join(os.path.dirname(bpy.data.filepath),'magic_classroom.py')}
exec(bpy.data.texts['magic_classroom.py'].as_string(),ns)
ns['LOG_PATH']=os.path.join(os.path.dirname(bpy.data.filepath),'render','classroom_transparency_log.txt')
ns['set_backdrop'](False)
sc.render.resolution_percentage=50
path=os.path.join(os.path.dirname(bpy.data.filepath),'render','classroom_transparency_check.png')
sc.render.filepath=path
bpy.ops.render.render(write_still=True,layer='BG')
im=bpy.data.images.load(path,check_existing=False)
w,h=im.size;pixels=list(im.pixels)
root=bpy.data.objects['cls_room_root'];clear=0;attempts=0;bad=[]
deps=bpy.context.evaluated_depsgraph_get()
direction=sc.camera.rotation_euler.to_matrix()@Vector((0,0,-1))
# 先几何射线筛选真正穿过窗洞的光线，避免把窗棂/厚墙遮住的位置误当窗口。
for yi in range(18):
    for zi in range(28):
        y=-.55+yi*.10;z=1.3+zi*.10
        point=root.matrix_world@Vector((-4.72,y,z))
        origin=point-direction*40
        hit,loc,norm,face,ob,matrix=sc.ray_cast(deps,origin,direction,distance=40)
        for skip in range(12):
            if not hit or not ob or not ob.hide_render:break
            origin=loc+direction*.02
            hit,loc,norm,face,ob,matrix=sc.ray_cast(deps,origin,direction,distance=(point-origin).length)
        if hit:continue
        # 邻域射线也必须穿孔，剔除只有亚像素缝隙的抗锯齿边缘。
        basis=sc.camera.rotation_euler.to_matrix()
        pixel=sc.camera.data.ortho_scale/w
        interior=True
        for dx,dy in ((-2,-2),(-2,2),(2,-2),(2,2)):
            neighbor=point+basis@Vector((dx*pixel,dy*pixel,0))
            ray=neighbor-direction*40
            hh,ll,nn,ff,oo,mm=sc.ray_cast(deps,ray,direction,distance=40)
            for skip in range(12):
                if not hh or not oo or not oo.hide_render:break
                ray=ll+direction*.02
                hh,ll,nn,ff,oo,mm=sc.ray_cast(deps,ray,direction,distance=(neighbor-ray).length)
            if hh:interior=False;break
        if not interior:continue
        p=world_to_camera_view(sc,sc.camera,point)
        x,yy=int(p.x*w),int(p.y*h)
        if 1<=x<w-1 and 1<=yy<h-1:
            # 抗锯齿边缘允许检查相邻像素，内部必须存在完全透明的像素。
            alpha=min(pixels[((yy+dy)*w+x+dx)*4+3] for dx in (-1,0,1) for dy in (-1,0,1))
            clear+=alpha<.01;attempts+=1
            if alpha>=.01:bad.append((y,z,alpha))
assert attempts>=8, f'未找到足够清晰窗洞采样：{attempts}'
assert clear/attempts>=.95, f'窗洞透明失败：{clear}/{attempts} {bad[:8]}'
assert all(o.hide_render for o in bpy.data.collections['cls_backdrop'].all_objects)
print('TRANSPARENCY_PASS',clear,'/',attempts,'unobstructed samples fully transparent; no blend mutation saved')
