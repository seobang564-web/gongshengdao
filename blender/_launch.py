# 通用后台启动器：读取 island_final/job.json 里的参数，起一个无界面 Blender 进程
import os, subprocess, bpy, json
B = LAUNCH_DIR
P = os.path.dirname(B)
job = json.load(open(os.path.join(B, "island_final", "job.json"), encoding="utf-8"))
args = [bpy.app.binary_path, "-b"] + [a.replace("{B}", B).replace("{P}", P) for a in job["args"]]
env = dict(os.environ, **{k: v.replace("{B}", B).replace("{P}", P) for k, v in job.get("env", {}).items()})
log = os.path.join(B, "island_final", job.get("log", "job_stdout.txt"))
proc = subprocess.Popen(args, stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
print("started", job.get("name"), proc.pid)
