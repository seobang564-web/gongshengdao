# -*- coding: utf-8 -*-
"""
一步搭好：v3 场景 + 导入人物 + 8 秒循环动画，保存为 gongshengdao_v45.blend
（用 Blender 4.5 在终端后台运行，存出来的文件云渲染平台能打开）
"""
import bpy, os
ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
for name in ("gongshengdao_scene_v3.py", "animate_loop.py"):
    p = os.path.join(ROOT, name)
    print("[共生岛] 运行", name)
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), {"__name__": "__main__"})
out = os.path.join(ROOT, "gongshengdao_v45.blend")
bpy.ops.wm.save_as_mainfile(filepath=out)
print("[共生岛] 已保存", out, "（Blender", bpy.app.version_string + "）")
