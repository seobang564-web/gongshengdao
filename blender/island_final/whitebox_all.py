import bpy, subprocess, os
H = os.path.dirname(os.path.abspath(__file__))
for t in ("night", "morning", "noon"):
    subprocess.run([bpy.app.binary_path, "-b", os.path.join(H, f"island_{t}.blend"), "-P", os.path.join(H, "whitebox.py"), "--", "all"],
                   stdout=open(os.path.join(H, f"wb_{t}.txt"), "w"), stderr=subprocess.STDOUT)
open(os.path.join(H, "wb_done.txt"), "w").write("done")
