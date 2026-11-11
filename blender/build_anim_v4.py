# -*- coding: utf-8 -*-
"""
一步搭好：v4 场景 + 导入伊蕾娜 + 8 秒循环动画 → gongshengdao_v4_anim.blend
终端：Blender -b -P ~/Desktop/共生岛/blender/build_anim_v4.py
"""
import bpy
import os

ROOT = os.path.expanduser("~/Desktop/共生岛/blender")
for name in ("gongshengdao_scene_v4.py", "animate_loop.py"):
    p = os.path.join(ROOT, name)
    print("[共生岛] 运行", name)
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), {"__name__": "__main__"})
out = os.path.join(ROOT, "gongshengdao_v4_anim.blend")
bpy.ops.wm.save_as_mainfile(filepath=out)
print("[共生岛] 已保存", out, "（Blender", bpy.app.version_string + "）")
