# -*- coding: utf-8 -*-
"""
共生岛 · 省内存 / 提速工具（16GB 内存的 M1/M2 笔记本用）

在【刚启动、还没打开任何文件】的 Blender 里，Scripting → Python 控制台粘贴：
    exec(open("/Users/macbook/Desktop/共生岛/blender/speed.py", encoding="utf-8").read()); gsd_q.open_v3()
它会：不加载界面设置地打开 v3 场景（视口保持“实体”模式，不会一打开就开始算光影）→ 切到草稿质量。
然后：
    gsd_q.preview()   用草稿质量出早/中/晚三张小预览（1/3 尺寸）
    gsd_q.minimal()   更省：连草、花、树叶粒子和体积雾都关掉，只看大构图
    gsd_q.final()     成品质量（最后导出素材时用，会很慢、很吃内存）
渲染中想中止：按 Esc。
"""
import bpy
import builtins

ROOT = "/Users/macbook/Desktop/共生岛/blender"
V3_BLEND = ROOT + "/gongshengdao_scene_v3.blend"
V3_SCRIPT = ROOT + "/gongshengdao_scene_v3.py"


def _set(obj, attr, val):
    try:
        setattr(obj, attr, val)
    except Exception:
        pass


def _particles(scale, render=True):
    for ps in bpy.data.particles:
        base = ps.get("full_count")
        if base is None:
            ps["full_count"] = ps.count
            base = ps.count
        ps.count = max(1, int(base * scale))
        _set(ps, "display_percentage", 5)
    for ob in bpy.data.objects:
        for md in ob.modifiers:
            if md.type == "PARTICLE_SYSTEM":
                md.show_render = render
                md.show_viewport = render


def _atmosphere(on):
    ob = bpy.data.objects.get("atmosphere")
    if ob is not None:
        ob.hide_render = not on
        ob.hide_viewport = not on


def _viewport_solid():
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                sp = area.spaces.active
                if sp.shading.type in ("MATERIAL", "RENDERED"):
                    sp.shading.type = "SOLID"


def _attach():
    """让 gsd.apply_time / gsd.preview 等命令能用（不重建场景）"""
    ns = {"__name__": "__main__", "GSD_ATTACH": True}
    exec(compile(open(V3_SCRIPT, encoding="utf-8").read(), V3_SCRIPT, "exec"), ns)


def draft():
    sc = bpy.context.scene
    ee = sc.eevee
    for attr, val in (("taa_render_samples", 12), ("taa_samples", 4), ("use_raytracing", False),
                      ("shadow_ray_count", 1), ("shadow_step_count", 4), ("shadow_resolution_scale", 0.5),
                      ("shadow_pool_size", "256"), ("gi_irradiance_pool_size", "16"),
                      ("volumetric_tile_size", "16"), ("volumetric_samples", 16), ("use_volumetric_shadows", False),
                      ("fast_gi_method", "AMBIENT_OCCLUSION_ONLY")):
        _set(ee, attr, val)
    sc.render.resolution_percentage = 33
    _particles(0.3)
    _atmosphere(True)
    _viewport_solid()
    print("[共生岛] 草稿质量：采样 12、关光追、阴影/雾降精度、草花树叶 30%、分辨率 33%")


def minimal():
    draft()
    _particles(0.3, render=False)
    _atmosphere(False)
    print("[共生岛] 最省模式：关掉草、花、树叶粒子和体积雾")


def final():
    sc = bpy.context.scene
    ee = sc.eevee
    for attr, val in (("taa_render_samples", 64), ("taa_samples", 16), ("use_raytracing", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 10), ("shadow_resolution_scale", 1.0),
                      ("shadow_pool_size", "512"), ("volumetric_tile_size", "8"), ("volumetric_samples", 64),
                      ("use_volumetric_shadows", True), ("fast_gi_method", "GLOBAL_ILLUMINATION")):
        _set(ee, attr, val)
    sc.render.resolution_percentage = 100
    _particles(1.0)
    _atmosphere(True)
    print("[共生岛] 成品质量（很慢、很吃内存，建议一次只渲一张）")


def open_v3():
    bpy.ops.wm.open_mainfile(filepath=V3_BLEND, load_ui=False)
    _attach()
    draft()


def preview():
    if not hasattr(builtins, "gsd"):
        _attach()
    builtins.gsd.preview(scale=bpy.context.scene.render.resolution_percentage)


class _Q:
    open_v3 = staticmethod(open_v3)
    draft = staticmethod(draft)
    minimal = staticmethod(minimal)
    final = staticmethod(final)
    preview = staticmethod(preview)


builtins.gsd_q = _Q
print("[共生岛] gsd_q 已就绪：open_v3() / draft() / minimal() / preview() / final()")
