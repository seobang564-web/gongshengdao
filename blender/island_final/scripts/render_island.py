# -*- coding: utf-8 -*-
"""
共生岛 · 岛屿最终版渲染（Windows / Mac 通用）
用法：blender -b island_night.blend -P scripts/render_island.py -- <步骤> [选项]
  步骤：bg      背景循环（不含人物，全画面，第 1–192 帧）
        clips   人物片段（只渲人物附近的裁剪区域，含真实场景、光照、影子）
        masks   人物遮罩（Workbench，几秒钟）
        all     依次 bg → clips → masks
        test    每个步骤只渲第 1 帧，报告耗时并估算总时间
  选项：--clips A1_idle,B2_wave   只渲指定片段
        --pct 50                 分辨率百分比（只用于快速试渲）
        --samples 16             采样数（只用于快速试渲）
        --frames 1-5             只渲这些帧（只用于快速试渲）
中途关掉后重新运行会跳过已经渲好的帧。输出在 .blend 同目录的 output\\ 里。
"""
import bpy, os, sys, json, time

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
STEP = argv[0] if argv else "all"


def opt(name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else default
    return default


sc = bpy.context.scene
reg = json.loads(bpy.data.texts["clips_island.json"].as_string())
T = reg["time"]
BASE = bpy.path.abspath("//")
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, f"render_log_{T}.txt")
PCT = int(opt("--pct", "100"))
SAMPLES = opt("--samples")
FR = opt("--frames")
SEL = set(opt("--clips").split(",")) if opt("--clips") else None
TEST = STEP == "test"


def log(m):
    m = time.strftime("%H:%M:%S ") + m
    print(m, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


json.dump(reg, open(os.path.join(OUT, f"clips_{T}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"time": T, "pct": PCT}, open(os.path.join(OUT, f"meta_{T}.json"), "w"))
sc.render.resolution_percentage = PCT
if SAMPLES:
    sc.eevee.taa_render_samples = int(SAMPLES)
RX, RY = reg["resolution"]
rig = bpy.data.objects["rig"]
ROOT = bpy.data.objects["CHAR_root"]
CHAR = bpy.data.collections["CHAR_人物"]
ENGINE = sc.render.engine


def frames_of(n):
    if TEST:
        return [1]
    if FR:
        a, b = FR.split("-") if "-" in FR else (FR, FR)
        return [f for f in range(int(a), int(b) + 1) if f <= n]
    return list(range(1, n + 1))


def assign(ob, name):
    act = bpy.data.actions[name]
    ob.animation_data_create()
    ob.animation_data.action = act
    try:
        if act.slots:
            ob.animation_data.action_slot = act.slots[0]
    except AttributeError:
        pass


def render_seq(frames, fmt, label):
    done = 0
    t0 = time.time()
    times = []
    for f in frames:
        fp = fmt % f
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            continue
        sc.frame_set(f)
        sc.render.filepath = fp
        t1 = time.time()
        bpy.ops.render.render(write_still=True)
        done += 1
        times.append(time.time() - t1)
        log(f"{label} 第 {f}/{frames[-1]} 帧 {time.time() - t1:.1f} 秒")
    return done, (min(times) if times else 0.0)


def set_border(crop):
    x, y, w, h = crop
    r = sc.render
    r.use_border = True
    r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = x / RX, (x + w) / RX
    r.border_min_y, r.border_max_y = 1 - (y + h) / RY, 1 - y / RY


def clips():
    return [c for c in reg["clips"] if SEL is None or c["name"] in SEL]


EST = {}


def do_bg():
    CHAR.hide_render = True
    sc.render.use_border = False
    d = os.path.join(OUT, f"bg_{T}")
    os.makedirs(d, exist_ok=True)
    fr = [1, 2] if TEST else frames_of(reg["loop_frames"])
    n, per = render_seq(fr, os.path.join(d, "frame_%04d.png"), f"[{T}] 背景")
    EST["bg"] = (per, reg["loop_frames"])
    CHAR.hide_render = False


def do_clips():
    CHAR.hide_render = False
    sc.render.engine = ENGINE
    for c in clips():
        assign(rig, c["rig_action"]); assign(ROOT, c["root_action"])
        sc.frame_start, sc.frame_end = 1, c["frames"]
        set_border(c["crop"])
        d = os.path.join(OUT, "raw", f"{c['name']}_{T}")
        os.makedirs(d, exist_ok=True)
        n, per = render_seq(frames_of(c["frames"]), os.path.join(d, "A_%04d.png"), f"[{T}] {c['name']}")
        EST[c["name"]] = (per, c["frames"])
    sc.render.use_border = False


def do_masks():
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"; sh.color_type = "OBJECT"
    for a in ("show_object_outline", "show_cavity", "show_shadows", "show_specular_highlight", "show_xray"):
        try:
            setattr(sh, a, False)
        except Exception:
            pass
    try:
        sc.display.render_aa = "8"
    except Exception:
        pass
    sc.render.film_transparent = True
    sc.render.use_compositing = False
    sc.render.use_freestyle = False
    sc.render.image_settings.color_mode = "RGBA"
    vs = sc.view_settings
    vs.view_transform = "Standard"; vs.look = "None"; vs.exposure = 0; vs.gamma = 1
    char_objs = set(CHAR.all_objects)
    skip = ("atmos", "fog", "haze", "mist", "smoke", "glint", "beam", "firefl", "petal", "sky", "star", "moon", "cloud", "sea", "ripple", "foam", "far")
    for o in bpy.data.objects:
        o.color = (1, 1, 1, 1) if o in char_objs else (0, 0, 0, 1)
        if o not in char_objs and o.type == "MESH":
            nm = o.name.lower()
            if any(k in nm for k in skip) or max(o.dimensions) > 30:
                o.hide_render = True
    for c in clips():
        assign(rig, c["rig_action"]); assign(ROOT, c["root_action"])
        set_border(c["crop"])
        d = os.path.join(OUT, "raw", f"{c['name']}_{T}")
        os.makedirs(d, exist_ok=True)
        render_seq(frames_of(c["frames"]), os.path.join(d, "M_%04d.png"), f"[{T}] {c['name']} 遮罩")


t0 = time.time()
log(f"===== {T} 开始：{STEP}，分辨率 {PCT}%，片段 {', '.join(c['name'] for c in clips())}")
if STEP in ("bg", "all", "test"):
    do_bg()
if STEP in ("clips", "all", "test"):
    do_clips()
if STEP in ("masks", "all", "test"):
    do_masks()
if TEST:
    tot = 0
    lines = []
    for k, (per, n) in EST.items():
        tot += per * n
        lines.append(f"  {k}: 每帧 {per:.1f} 秒 × {n} 帧 ≈ {per * n / 60:.1f} 分钟")
    log(f"[{T}] 试渲完成。估算（不含遮罩，遮罩很快）：\n" + "\n".join(lines) + f"\n  合计约 {tot / 3600:.1f} 小时")
log(f"===== {T} 结束：{STEP}，用时 {(time.time() - t0) / 60:.1f} 分钟")
