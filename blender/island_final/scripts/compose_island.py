# -*- coding: utf-8 -*-
"""
共生岛 · 合成：人物裁剪渲染 + 遮罩 + 背景 → 透明人物层（PNG 序列 + WebM 透明视频）+ 预览 MP4 + 背景 MP4
用法：blender -b -P scripts/compose_island.py -- night [--clips A1_idle,B2_wave] [--no-video]
原理：同一帧里，「有人物的画面」÷「没人物的背景」= 人物投下的阴影比例；遮罩给出人物本身的像素。
     这样人物层可以叠在背景循环的任意相位上，水面、篝火、草的动画都不会错位。
"""
import bpy, os, sys, json, time
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
T = argv[0] if argv else "night"
SEL = set(argv[argv.index("--clips") + 1].split(",")) if "--clips" in argv else None
VIDEO = "--no-video" not in argv
PARTIAL = "--partial" in argv      # 测试用：帧不全也编码
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output")
reg = json.load(open(os.path.join(OUT, f"clips_{T}.json"), encoding="utf-8"))
meta = json.load(open(os.path.join(OUT, f"meta_{T}.json")))
PCT = meta["pct"] / 100.0
LOOPN = reg["loop_frames"]
FPS = reg.get("fps", 24)
LOG = os.path.join(OUT, f"compose_log_{T}.txt")


def log(m):
    m = time.strftime("%H:%M:%S ") + m
    print(m, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def load(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1].copy()          # 左上原点


def save(path, arr):
    h, w, _ = arr.shape
    img = bpy.data.images.new("o", w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


BG_CACHE = {}


def bg_frame(f):
    k = (f - 1) % LOOPN + 1
    if k not in BG_CACHE:
        if len(BG_CACHE) > 8:
            BG_CACHE.clear()
        BG_CACHE[k] = load(os.path.join(OUT, f"bg_{T}", "frame_%04d.png" % k))
    return BG_CACHE[k]


def _shift_stack(a, r):
    p = np.pad(a, r, mode="edge")
    h, w = a.shape
    return [p[r + dy:r + dy + h, r + dx:r + dx + w] for dy in range(-r, r + 1) for dx in range(-r, r + 1)]


def erode(a, r=1):
    return np.minimum.reduce(_shift_stack(a, r))


def dilate(a, r=1):
    return np.maximum.reduce(_shift_stack(a, r))


def box(a, r=1):
    return sum(_shift_stack(a, r)) / float((2 * r + 1) ** 2)


LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)


def compose_clip(c):
    name = c["name"]
    raw = os.path.join(OUT, "raw", f"{name}_{T}")
    dst = os.path.join(OUT, "layer", f"{name}_{T}")
    os.makedirs(dst, exist_ok=True)
    x, y, w, h = [int(round(v * PCT)) for v in c["crop"]]
    n = c["frames"]
    fade = c.get("fade_out", 0)
    made = 0
    for f in range(1, n + 1):
        fo = os.path.join(dst, "frame_%04d.png" % f)
        fa, fm = os.path.join(raw, "A_%04d.png" % f), os.path.join(raw, "M_%04d.png" % f)
        if os.path.exists(fo) or not (os.path.exists(fa) and os.path.exists(fm)):
            continue
        A = load(fa); M = load(fm)
        hh, ww = min(A.shape[0], M.shape[0]), min(A.shape[1], M.shape[1])
        Bf = bg_frame(f)
        B = Bf[y:y + hh, x:x + ww]
        hh, ww = min(hh, B.shape[0]), min(ww, B.shape[1])
        A, M, B = A[:hh, :ww], M[:hh, :ww], B[:hh, :ww]
        m = np.clip(M[..., 0] * M[..., 3], 0, 1)
        la, lb = A[..., :3] @ LUM, B[..., :3] @ LUM
        s = np.clip(la / np.maximum(lb, 1.0 / 255), 0, 1)
        d = 1 - s                                        # 变暗量
        d = np.where(d < 0.05, 0.0, d)                  # 去掉渲染噪点
        md = dilate(m, 2)
        d = np.where(md > 0.02, 0.0, d)                  # 人物本身（含描边）不算阴影
        d = dilate(erode(d, 2), 2)                       # 开运算：去掉物体边缘的细线（抗锯齿差异），保留成片的阴影
        d = box(d, 1)
        s = 1 - d
        # 裁剪边缘 16 像素内渐隐（避免边框处的细微差异）
        ry = np.minimum(np.arange(hh), np.arange(hh)[::-1]); rx = np.minimum(np.arange(ww), np.arange(ww)[::-1])
        ramp = np.clip(np.minimum(ry[:, None], rx[None, :]) / 16.0, 0, 1)
        s = 1 - (1 - s) * ramp
        k = (1 - m) * s
        a = 1 - k
        prem = np.clip(A[..., :3] - k[..., None] * B[..., :3], 0, None)
        if fade and f > n - fade:
            g = (n - f) / fade
            a = a * g; prem = prem * g
        rgb = np.where(a[..., None] > 1e-4, prem / np.maximum(a[..., None], 1e-4), 0)
        out = np.dstack([np.clip(rgb, 0, 1), np.clip(a, 0, 1)]).astype(np.float32)
        save(fo, out)
        made += 1
    log(f"[{T}] {name}: 合成 {made} 帧 → layer/{name}_{T}/")
    f1 = os.path.join(dst, "frame_0001.png")
    if os.path.exists(f1):                      # 以实际尺寸为准（Blender 裁剪可能差 1 像素）
        im = bpy.data.images.load(f1, check_existing=False)
        w, h = im.size[0], im.size[1]
        bpy.data.images.remove(im)
    return dst, (x, y, w, h)


# ---------------------------------------------------------------- 视频（用 Blender 自带的 FFmpeg）
def vse_scene(name, w, h, nframes):
    s = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage = w, h, 100
    s.render.fps = FPS
    s.frame_start, s.frame_end = 1, nframes
    s.view_settings.view_transform = "Standard"
    if not s.sequence_editor:
        s.sequence_editor_create()
    return s


def strips(s):
    ed = s.sequence_editor
    return ed.strips if hasattr(ed, "strips") else ed.sequences


def add_images(s, folder, files, channel, start):
    st = strips(s).new_image(name=os.path.basename(folder) + str(channel), filepath=os.path.join(folder, files[0]), channel=channel, frame_start=start)
    for fn in files[1:]:
        st.elements.append(fn)
    return st


def set_video(s, path, kind):
    r = s.render
    try:
        r.image_settings.media_type = "VIDEO"
    except Exception:
        pass
    r.image_settings.file_format = "FFMPEG"
    ff = r.ffmpeg
    if kind == "webm":
        ff.format = "WEBM"; ff.codec = "WEBM"
        r.image_settings.color_mode = "RGBA"
    else:
        ff.format = "MPEG4"; ff.codec = "H264"
        r.image_settings.color_mode = "RGB"
    try:
        ff.constant_rate_factor = "HIGH"
    except Exception:
        pass
    ff.audio_codec = "NONE"
    r.filepath = path


VID = os.path.join(OUT, "video")
os.makedirs(VID, exist_ok=True)


def encode_layer(c, folder, box):
    x, y, w, h = box
    files = sorted(f for f in os.listdir(folder) if f.startswith("frame_"))
    if len(files) < c["frames"] and not (PARTIAL and files):
        log(f"[{T}] {c['name']}: 只有 {len(files)}/{c['frames']} 帧，跳过视频")
        return
    s = vse_scene("enc_" + c["name"], w + w % 2, h + h % 2, len(files))
    for st in list(strips(s)):
        strips(s).remove(st)
    add_images(s, folder, files, 1, 1)
    s.render.film_transparent = True
    set_video(s, os.path.join(VID, f"{c['name']}_{T}.webm"), "webm")
    with bpy.context.temp_override(scene=s):
        bpy.ops.render.render(animation=True, scene=s.name)
    log(f"[{T}] {c['name']}: video/{c['name']}_{T}.webm")


def encode_bg():
    folder = os.path.join(OUT, f"bg_{T}")
    files = sorted(f for f in os.listdir(folder) if f.startswith("frame_"))
    if len(files) < LOOPN and not (PARTIAL and files):
        log(f"[{T}] 背景只有 {len(files)}/{LOOPN} 帧，跳过背景视频")
        return
    W_, H_ = int(reg["resolution"][0] * PCT), int(reg["resolution"][1] * PCT)
    s = vse_scene("enc_bg", W_, H_, LOOPN)
    for st in list(strips(s)):
        strips(s).remove(st)
    add_images(s, folder, files, 1, 1)
    set_video(s, os.path.join(VID, f"bg_{T}.mp4"), "mp4")
    with bpy.context.temp_override(scene=s):
        bpy.ops.render.render(animation=True, scene=s.name)
    log(f"[{T}] 背景视频 video/bg_{T}.mp4")


def encode_preview(c, folder, box):
    """把人物层叠到背景上看效果（背景从第 37 帧开始，故意和片段错开相位，检验能否任意叠加）"""
    x, y, w, h = box
    files = sorted(f for f in os.listdir(folder) if f.startswith("frame_"))
    bgf = os.path.join(OUT, f"bg_{T}")
    bfiles = sorted(f for f in os.listdir(bgf) if f.startswith("frame_"))
    if (len(files) < c["frames"] or len(bfiles) < LOOPN) and not (PARTIAL and files and bfiles):
        return
    n = len(files)
    W_, H_ = int(reg["resolution"][0] * PCT), int(reg["resolution"][1] * PCT)
    s = vse_scene("prev_" + c["name"], W_, H_, n)
    for st in list(strips(s)):
        strips(s).remove(st)
    off = 36
    seq = [bfiles[(off + i) % len(bfiles)] for i in range(n)]
    add_images(s, bgf, seq, 1, 1)
    lay = add_images(s, folder, files, 2, 1)
    lay.blend_type = "ALPHA_OVER"
    try:
        lay.transform.offset_x = x + w / 2 - W_ / 2
        lay.transform.offset_y = (H_ / 2) - (y + h / 2)
    except Exception:
        pass
    s.render.resolution_percentage = 50
    set_video(s, os.path.join(VID, f"preview_{c['name']}_{T}.mp4"), "mp4")
    with bpy.context.temp_override(scene=s):
        bpy.ops.render.render(animation=True, scene=s.name)


t0 = time.time()
index = []
for c in reg["clips"]:
    if SEL and c["name"] not in SEL:
        continue
    folder, box = compose_clip(c)
    entry = {"name": c["name"], "time": T, "file": f"{c['name']}_{T}.webm", "frames": c["frames"], "loop": c["loop"],
             "from": c["from"], "to": c["to"], "pose_from": c["pose_from"], "pose_to": c["pose_to"],
             "x": int(c["crop"][0]), "y": int(c["crop"][1]), "w": int(round(box[2] / PCT)), "h": int(round(box[3] / PCT)), "fade_out": c.get("fade_out", 0)}
    index.append(entry)
    if VIDEO:
        try:
            encode_layer(c, folder, box)
            encode_preview(c, folder, box)
        except Exception as e:
            import traceback
            log(f"[{T}] {c['name']} 视频编码出错：{e}\n{traceback.format_exc()}")
if VIDEO and (not SEL or PARTIAL):
    try:
        encode_bg()
    except Exception as e:
        log(f"[{T}] 背景视频编码出错：{e}")
json.dump({"time": T, "background": f"bg_{T}.mp4", "loop_frames": LOOPN, "fps": FPS, "resolution": reg["resolution"],
           "positions": reg.get("positions"), "clips": index}, open(os.path.join(VID, f"clips_{T}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
log(f"[{T}] 合成完成，用时 {(time.time() - t0) / 60:.1f} 分钟")
