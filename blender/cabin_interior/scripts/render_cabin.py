"""EEVEE 木屋室内三层渲染。

blender -b --factory-startup --python-exit-code 1 -P render_cabin.py -- test
blender -b --factory-startup --python-exit-code 1 -P render_cabin.py -- all

先设置 GSD_CHAR_SRC、GSD_MIXAMO_DIR。全量编码还需要 PATH 上的 FFmpeg，
或以 --ffmpeg 指定含 libx264 / libvpx-vp9 的可执行文件。
"""

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter

import bpy
from mathutils import Vector
import numpy as np


CABIN = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 2560, 1440
FPS, LOOP = 24, 192
LUMA = np.array((0.2126, 0.7152, 0.0722), dtype=np.float32)
TEST_FRAME = {"night": 30, "late": 70, "dawn_closed": 38, "dawn_open": 60, "dawn_open_nohat": 22}


def log(message):
    print(message, flush=True)


def staging(path):
    return path.with_name(f".{path.stem}.{os.getpid()}{path.suffix}")


def write_json(path, data):
    tmp = staging(path)
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def ready(path):
    return path.is_file() and path.stat().st_size > 0


def load_image(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = image.size
        pixels = np.empty(w * h * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        return pixels.reshape(h, w, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(image)


def save_image(path, pixels):
    h, w, channels = pixels.shape
    tmp = staging(path)
    image = bpy.data.images.new("cabin_pixels", w, h, alpha=channels == 4)
    try:
        image.alpha_mode = "STRAIGHT"
        if channels == 3:
            pixels = np.dstack((pixels, np.ones((h, w), dtype=np.float32)))
        image.pixels.foreach_set(np.ascontiguousarray(pixels[::-1]).ravel())
        image.file_format = "JPEG" if path.suffix == ".jpg" else "PNG"
        image.filepath_raw = str(tmp)
        image.save()
        tmp.replace(path)
    finally:
        bpy.data.images.remove(image)


def neighbors(pixels, r):
    h, w = pixels.shape
    padded = np.pad(pixels, r, mode="edge")
    for y in range(2 * r + 1):
        for x in range(2 * r + 1):
            yield padded[y:y + h, x:x + w]


def morphology(pixels, r, op):
    result = pixels.copy()
    for axis, size in enumerate(pixels.shape):
        pad = ((r, r), (0, 0)) if axis == 0 else ((0, 0), (r, r))
        padded = np.pad(result, pad, mode="edge")
        for i in range(2 * r + 1):
            sample = padded[i:i + size, :] if axis == 0 else padded[:, i:i + size]
            op(result, sample, out=result)
    return result


def soften(pixels, r):
    for axis in range(2):
        rows = np.moveaxis(pixels, axis, 0)
        padded = np.pad(rows, ((r + 1, r), (0, 0)), mode="edge")
        totals = padded.cumsum(axis=0)
        pixels = np.moveaxis((totals[2 * r + 1:] - totals[:-(2 * r + 1)]) / (2 * r + 1), 0, axis)
    return pixels


def compose(beauty, background, mask, gain, edges=(True, True, True, True), bloom=False):
    """将同相位背景中已有的颜色扣除，保留前景、抗锯齿和有效的投影。"""
    rgb, bg = beauty[..., :3], background[..., :3]
    la, lb = rgb @ LUMA, bg @ LUMA
    dark = np.clip((lb - la) / np.maximum(lb, 1 / 255), 0, 1)
    dark[(dark < 0.05) | (morphology(mask, 2, np.maximum) > 0.02)] = 0
    dark = morphology(morphology(dark, 2, np.minimum), 2, np.maximum)
    dark = sum(neighbors(dark, 1)) / 9
    h, w = mask.shape
    edge_gain = np.ones_like(dark)
    left, top, right, bottom = edges
    for active, d in (
        (left, np.arange(w)[None, :]), (top, np.arange(h)[:, None]),
        (right, np.arange(w - 1, -1, -1)[None, :]), (bottom, np.arange(h - 1, -1, -1)[:, None]),
    ):
        if active:
            np.minimum(edge_gain, np.minimum(d / 16, 1), out=edge_gain)
    retained = (1 - mask) * (1 - dark * edge_gain)
    if bloom:
        # B6 发光形状之外的柔光由同相位明差恢复，限定在遮罩附近。
        rise = rgb - bg
        bright = np.clip(np.max(rise / np.maximum(1 - bg, 1 / 255), axis=-1), 0, 1)
        nearby = soften(morphology(mask, 56, np.maximum), 48)
        signal = np.clip((255 * np.max(rise, axis=-1) - 1) / 6, 0, 1)
        np.minimum(retained, 1 - bright * nearby * signal * edge_gain, out=retained)
    alpha = 1 - retained
    premul = np.clip(rgb - retained[..., None] * bg, 0, 1)
    color = np.clip(premul / np.maximum(alpha[..., None], 1e-4), 0, 1)
    color[alpha <= 1e-4] = 0
    return np.dstack((color, alpha * gain)).astype(np.float32)


def fade_gain(clip, frame):
    if clip.get("loop"):
        return 1
    enter = min(1, (frame - 1) / clip["fade_in"]) if clip["fade_in"] else 1
    leave = min(1, (clip["frames"] - frame) / clip["fade_out"]) if clip["fade_out"] else 1
    return min(enter, leave)


def set_fade_mode(clip):
    if clip["fade_in"] or clip["fade_out"]:
        clip["fade_mode"] = "player" if clip["loop"] else "baked"


def background_name(variant, camera, omit):
    suffix = "" if camera == "main" else f"_{camera}"
    for prop in omit:
        suffix += f"_no{prop}"
    return f"bg_cabin_{variant}{suffix}.mp4"


def input_files():
    char = Path(os.environ["GSD_CHAR_SRC"])
    motion = Path(os.environ["GSD_MIXAMO_DIR"])
    library = CABIN.parent
    return [
        Path(__file__), CABIN / "cabin_whitebox.py", library / "cloth_sim.py", library / "retarget_mixamo.py",
        char, *(motion / f"{name}.fbx" for name in ("Typing", "Laying Sleeping", "Stand To Sit", "Happy Walk")),
        *(CABIN / "backdrop" / f"island_{tag}_{view}.png"
          for tag in ("night", "morning", "noon") for view in ("front", "west")),
    ]


def cache_key(samples):
    digest = hashlib.sha256()
    digest.update(f"{bpy.app.version_string}:{samples}".encode())
    for path in input_files():
        with path.open("rb") as source:
            digest.update(hashlib.file_digest(source, "sha256").digest())
    return digest.hexdigest()[:16]


def rebuild(build_output):
    script = CABIN / "cabin_whitebox.py"
    state = {"__name__": "__main__", "__file__": str(script)}
    argv = sys.argv
    previous = os.environ.get("GSD_CABIN_BUILD_OUT")
    try:
        sys.argv = [argv[0], "--", "--b1", "--wb-only", "--render-only"]
        os.environ["GSD_CABIN_BUILD_OUT"] = str(build_output)
        exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), state)
    finally:
        sys.argv = argv
        if previous is None:
            os.environ.pop("GSD_CABIN_BUILD_OUT", None)
        else:
            os.environ["GSD_CABIN_BUILD_OUT"] = previous
    return state


def prop_objects(state, camera):
    objs = bpy.context.scene.objects
    fx = state["B6_FX"].get(camera)
    return {
        "chair": {obj for obj in objs if obj.name.startswith("cab_chair")},
        "hat": set(state["HAT_ON_STAND"]),
        "curtain_l2": {obj for obj in objs if obj.name.startswith("cab_win_l2_cur_closed_")},
        "fx": set(fx.all_objects) if fx else set(),
    }


def background_plan(manifest, clip_names=None, main_backgrounds=()):
    backgrounds = {}
    for clip in manifest["clips"]:
        selected = clip_names is None or clip["name"] in clip_names
        for cam in clip["cams"]:
            variant = clip["bg"]
            if not selected and not (cam == "main" and variant in main_backgrounds):
                continue
            backgrounds.setdefault((variant, cam, ()), clip["name"])
            if selected:
                omit = omitted_props(manifest, clip)
                backgrounds.setdefault((variant, cam, omit), clip["name"])
    missing = [variant for variant in main_backgrounds if (variant, "main", ()) not in backgrounds]
    if missing:
        raise ValueError(f"未知主镜头背景：{', '.join(missing)}")
    return backgrounds


def omitted_props(manifest, clip):
    omit = set(clip["props"]) & {"chair", "hat", "curtain_l2"}
    if manifest["backgrounds"][clip["bg"]]["hat"] == "head":
        omit.discard("hat")
    return tuple(sorted(omit))


def configure_eevee(state, samples):
    state["COL"]["HIDDEN"].hide_render = False
    state["setup_eevee"]()
    scene = state["sc"]
    scene.eevee.taa_render_samples = samples
    scene.render.use_compositing = True
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"


def configure_mask(state, foreground):
    scene = state["sc"]
    state["COL"]["HIDDEN"].hide_render = True
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light, sh.color_type = "FLAT", "OBJECT"
    sh.show_object_outline = sh.show_shadows = sh.show_cavity = False
    sh.show_specular_highlight = sh.show_xray = False
    scene.display.render_aa = "8"
    scene.render.film_transparent = True
    scene.render.use_compositing = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform, scene.view_settings.look = "Standard", "None"
    scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
    for obj in scene.objects:
        value = float(obj in foreground)
        obj.color = (value, value, value, 1)


def park_chair(state):
    chair = state["CHAIR_ROOT"]
    chair.animation_data_clear()
    chair.location.x, chair.location.y = state["B1_CHAIR_XY"]


def set_background(state, variant, camera, omit, clip):
    state["play_clip"](clip, camera)
    state["_show_char"](None)
    state["fx_on"](None, False)
    state["hat_mode"](variant["hat"])
    state["curtain_mode"](variant["curtain_l2"])
    park_chair(state)
    objects = prop_objects(state, camera)
    saved = {obj: obj.hide_render for prop in omit for obj in objects[prop]}
    for obj in saved:
        obj.hide_render = True
    return saved


def foreground_objects(state, clip, camera):
    props = prop_objects(state, camera)
    actors = {obj for info in state["CH_INFO"].values() if not info["coll"].hide_render
              for obj in info["coll"].all_objects if not obj.hide_render}
    return actors | {obj for label in clip["props"] for obj in props[label] if not obj.hide_render}


def shadow_point(point, direction, surfaces):
    """沿射线取第一个有物体可接收阴影的平面。"""
    hits = []
    for axis, plane, bounds in surfaces:
        v = direction[axis]
        if abs(v) < 1e-5:
            continue
        t = (plane - point[axis]) / v
        if t <= 0:
            continue
        hit = point + t * direction
        if all(lo <= hit[i] <= hi for i, lo, hi in bounds):
            hits.append((t, hit))
    return min(hits, key=lambda pair: pair[0])[1] if hits else None


def crop_box(state, objects, n):
    scene = state["sc"]
    cam = scene.camera
    geometry = [obj for obj in objects if obj.type in {"MESH", "CURVE"}]
    ix, iy, wh = state["IX"], state["IY"], state["WH"]
    terrain = scene.objects["cab_island"].bound_box
    surfaces = [
        (0, ix, ((1, -iy, iy), (2, 0, wh))),
        (1, iy, ((0, -ix, ix), (2, 0, wh))),
        (2, 0, ((0, -ix, ix), (1, -iy, iy))),
        (2, state["GROUND"], tuple((i, min(v[i] for v in terrain), max(v[i] for v in terrain)) for i in (0, 1))),
    ]
    if cam != state["CAM_MAIN"]:
        surfaces.append((0, -ix, ((1, -iy, iy), (2, 0, wh))))
    lights = [light for light, _ in state["LIGHTS"] if light.data.use_shadow and not light.hide_render]
    sun = state["SUN"]
    if sun.data.energy > 0:
        lights.append(sun)
    dg = bpy.context.evaluated_depsgraph_get()
    projection = cam.calc_matrix_camera(dg, x=WIDTH, y=HEIGHT) @ cam.matrix_world.inverted()
    left = top = math.inf
    right = bottom = -math.inf
    for frame in range(1, n + 1):
        scene.frame_set(frame)
        for obj in geometry:
            evaluated = obj.evaluated_get(dg)
            corners = [evaluated.matrix_world @ Vector(v) for v in evaluated.bound_box]
            points = list(corners)
            if not obj.name.startswith("FX_"):
                for light in lights:
                    for p in corners:
                        if light.data.type == "SUN":
                            direction = light.matrix_world.to_3x3() @ Vector((0, 0, -1))
                        else:
                            ray = p - light.matrix_world.translation
                            if light.data.use_custom_distance and ray.length > light.data.cutoff_distance:
                                continue
                            direction = ray.normalized()
                            if light.data.type in {"SPOT", "AREA"}:
                                axis = light.matrix_world.to_3x3() @ Vector((0, 0, -1))
                                angle = light.data.spot_size if light.data.type == "SPOT" else light.data.spread
                                # 面光源发光面有宽度，中心光线的锥角向外留余量。
                                if direction.dot(axis) < math.cos(angle / 2 + math.radians(15)):
                                    continue
                        hit = shadow_point(p, direction, surfaces)
                        if hit is not None:
                            points.append(hit)
            for p in points:
                x, y, _, w = projection @ p.to_4d()
                if w <= 0:
                    continue
                x, y = (x / w + 1) * WIDTH / 2, (1 - y / w) * HEIGHT / 2
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    if not geometry or not math.isfinite(left):
        raise RuntimeError("人物裁剪框为空")
    x, y = max(0, 2 * math.floor((left - 48) / 2)), max(0, 2 * math.floor((top - 48) / 2))
    r, b = min(WIDTH, 2 * math.ceil((right + 48) / 2)), min(HEIGHT, 2 * math.ceil((bottom + 48) / 2))
    if r <= x or b <= y:
        raise RuntimeError(f"{cam.name} 的人物裁剪框不在画面内")
    return x, y, r - x, b - y


def set_border(scene, box):
    r = scene.render
    r.use_border = box is not None
    r.use_crop_to_border = box is not None
    if box is not None:
        x, y, w, h = box
        # 避免归一化坐标转 float32 后刚好落在边界像素之前。
        r.border_min_x, r.border_max_x = (x + 0.01) / WIDTH, min(1, (x + w + 0.01) / WIDTH)
        r.border_min_y, r.border_max_y = (HEIGHT - y - h + 0.01) / HEIGHT, min(1, (HEIGHT - y + 0.01) / HEIGHT)


def render_frame(scene, frame, path):
    if ready(path):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = staging(path)
    start = perf_counter()
    scene.frame_set(frame)
    scene.render.filepath = str(tmp)
    result = bpy.ops.render.render(write_still=True)
    if "FINISHED" not in result or not ready(tmp):
        raise RuntimeError(f"第 {frame} 帧渲染失败，路径 {path}")
    tmp.replace(path)
    seconds = round(perf_counter() - start, 3)
    log(f"{path.parent.name}/{path.name}, f{frame:04}, {seconds:.3f}s")
    return seconds


def frame_path(folder, frame):
    return folder / f"frame_{frame:04}.png"


def compose_frame(raw, mask, background, layer, preview, box, gain, bloom):
    start = perf_counter()
    x, y, w, h = box
    if ready(layer) and (preview is None or ready(preview)):
        return None
    bg = load_image(background)
    if ready(layer):
        rgba = load_image(layer)
    else:
        beauty, matte = load_image(raw), load_image(mask)
        if beauty.shape[:2] != (h, w) or matte.shape[:2] != (h, w):
            raise ValueError(f"裁剪尺寸预期 {w}×{h}，实际 {beauty.shape}, {matte.shape}，{raw}")
        edges = (x > 0, y > 0, x + w < WIDTH, y + h < HEIGHT)
        rgba = compose(beauty, bg[y:y + h, x:x + w], matte[..., 0] * matte[..., 3], gain, edges, bloom)
        layer.parent.mkdir(parents=True, exist_ok=True)
        save_image(layer, rgba)
    if preview is not None:
        a = rgba[..., 3:4]
        region = bg[y:y + h, x:x + w, :3]
        region[:] = a * rgba[..., :3] + (1 - a) * region
        save_image(preview, bg[..., :3])
    return round(perf_counter() - start, 3)


def encode(ffmpeg, path, tag, inputs, frames, filter_args=()):
    if ready(path):
        return
    temp = staging(path)
    codecs = {
        "webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "19",
                 "-row-mt", "1", "-auto-alt-ref", "0"],
        "mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart"],
    }
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    *inputs, *filter_args, "-an", "-frames:v", str(frames), *codecs[tag], str(temp)], check=True)
    if not ready(temp):
        raise RuntimeError(f"视频未写入 {temp}")
    temp.replace(path)
    log(f"视频 {path.name}")


def image_sequence(folder):
    return ["-framerate", str(FPS), "-i", str(folder / "frame_%04d.png")]


def preview_overlay(x, y):
    # WebM 的毫秒时间戳会舍入 24 fps 的帧间隔。按帧号对齐两路，
    # 由 encode 的 -frames:v 控制长度，避免 overlay shortest 提前结束。
    return (
        f"[0:v]settb=1/{FPS},setpts=N[bg];"
        f"[1:v]settb=1/{FPS},setpts=N[fg];[bg][fg]overlay={x}:{y}"
    )


def publish_videos(encoded, video):
    for source in encoded.iterdir():
        if source.name.startswith(".") or source.suffix not in {".mp4", ".webm"}:
            continue
        path = video / source.name
        tmp = staging(path)
        shutil.copyfile(source, tmp)
        tmp.replace(path)


def run(args):
    key = cache_key(args.samples)
    work = args.output / "frames" / key
    test = args.mode == "test"
    check = args.output / "check" / key
    video = args.output / "video"
    (check if test else video).mkdir(parents=True, exist_ok=True)
    encoded = work / "encoded"
    if not test:
        encoded.mkdir(parents=True, exist_ok=True)
    timings = {"blender": bpy.app.version_string, "samples": args.samples, "backgrounds": [], "clips": []}
    if test and ready(check / "timings.json"):
        timings = json.loads((check / "timings.json").read_text(encoding="utf-8"))
    old_bg = {entry["file"]: entry for entry in timings["backgrounds"]}
    old_clips = {entry["file"]: entry for entry in timings["clips"]}
    timings["backgrounds"], timings["clips"] = [], []

    state = rebuild(work / "build")
    scene = state["sc"]
    render = scene.render
    render.resolution_x, render.resolution_y, render.resolution_percentage = WIDTH, HEIGHT, 100
    render.fps, render.fps_base = FPS, 1
    render.image_settings.media_type = "IMAGE"
    render.image_settings.file_format = "PNG"
    render.image_settings.color_depth = "8"
    render.image_settings.compression = 15
    render.use_file_extension = True
    manifest = json.loads((Path(state["OUT"]) / "clips_cabin.json").read_text(encoding="utf-8"))
    backgrounds = background_plan(manifest, args.clips, args.main_background)
    if args.clips:
        names = set(args.clips)
        unknown = names - {clip["name"] for clip in manifest["clips"]}
        if unknown:
            raise ValueError(f"未知片段：{', '.join(sorted(unknown))}")
        manifest["clips"] = [clip for clip in manifest["clips"] if clip["name"] in names]
    for clip in manifest["clips"]:
        set_fade_mode(clip)
    manifest["time"] = "cabin"
    manifest["background_files"] = defaultdict(dict)
    background_samples = {}
    configure_eevee(state, args.samples)
    for (variant, cam, omit), clip_name in backgrounds.items():
        name = background_name(variant, cam, omit)
        folder = work / Path(name).stem
        restore = set_background(state, manifest["backgrounds"][variant], cam, omit, clip_name)
        set_border(scene, None)
        sample = 60 if cam != "main" else TEST_FRAME[variant]
        try:
            for f in ([sample] if test else range(1, LOOP + 1)):
                seconds = render_frame(scene, f, frame_path(folder, f))
                if test:
                    shot = check / f"{folder.name}.jpg"
                    if not ready(shot):
                        save_image(shot, load_image(frame_path(folder, f))[..., :3])
                    entry = dict(file=name, frame=f, seconds=seconds, screenshot=shot.name)
                    timings["backgrounds"].append(old_bg.get(name, entry) if seconds is None else entry)
                    background_samples[name] = f
                    write_json(check / "timings.json", timings)
        finally:
            for obj, previous in restore.items():
                obj.hide_render = previous
        if not test:
            encode(args.ffmpeg, encoded / name, "mp4", image_sequence(folder), LOOP)
        if not omit:
            manifest["background_files"][variant][cam] = name

    for clip in manifest["clips"]:
        views = {}
        for cam in clip["cams"]:
            n = state["play_clip"](clip["name"], cam)
            if "chair" not in clip["props"]:
                park_chair(state)
            if n != clip["frames"]:
                raise ValueError(f"{clip['name']} 的实际帧数 {n} 不等于清单")
            file = clip["files"][cam]
            stem = Path(file).stem
            bg_file = background_name(clip["bg"], cam, omitted_props(manifest, clip))
            bg = work / Path(bg_file).stem
            folder = work / stem
            objects = foreground_objects(state, clip, cam)
            box_file = folder / "crop.json"
            if ready(box_file):
                box = tuple(json.loads(box_file.read_text(encoding="utf-8")))
            else:
                box = crop_box(state, objects, n)
                folder.mkdir(parents=True, exist_ok=True)
                write_json(box_file, box)
            x, y, w, h = box
            set_border(scene, box)
            frames = [background_samples[bg_file]] if test else range(1, n + 1)
            if frames[-1] > n:
                raise ValueError(f"抽样帧 {frames[-1]} 超过 {clip['name']} 的 {n} 帧")
            raw_seconds = [render_frame(scene, f, frame_path(folder / "beauty", f)) for f in frames]
            configure_mask(state, objects)
            mask_seconds = [render_frame(scene, f, frame_path(folder / "mask", f)) for f in frames]
            configure_eevee(state, args.samples)
            layer = folder / "layer"
            for f in frames:
                preview = check / f"{stem}.jpg" if test else None
                seconds = compose_frame(frame_path(folder / "beauty", f), frame_path(folder / "mask", f),
                                        frame_path(bg, (f - 1) % LOOP + 1), frame_path(layer, f), preview,
                                        box, fade_gain(clip, f), "fx" in clip["props"])
                if test:
                    past = old_clips.get(file, {})
                    timings["clips"].append(dict(
                        file=file, clip=clip["name"], camera=cam, frame=f, frames=n,
                        beauty=raw_seconds[0] if raw_seconds[0] is not None else past.get("beauty"),
                        mask=mask_seconds[0] if mask_seconds[0] is not None else past.get("mask"),
                        compose=seconds if seconds is not None else past.get("compose"),
                        screenshot=preview.name, background=bg_file, crop=box,
                    ))
                    write_json(check / "timings.json", timings)
            views[cam] = dict(file=file, background=bg_file, x=x, y=y, w=w, h=h)
            if not test:
                encode(args.ffmpeg, encoded / file, "webm", image_sequence(layer), n)
                encode(args.ffmpeg, encoded / f"preview_{stem}.mp4", "mp4",
                       ["-stream_loop", "-1", "-i", str(encoded / bg_file),
                        "-c:v", "libvpx-vp9", "-i", str(encoded / file)], n,
                       ["-filter_complex", preview_overlay(x, y)])
        clip.update(views[clip["cams"][0]], views=views)
    if test:
        write_json(check / "clips_cabin.json", manifest)
        log(f"单帧检查 {check}")
    else:
        publish_videos(encoded, video)
        write_json(video / "clips_cabin.json", manifest)
        log(f"视频与清单 {video}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", default="test", choices=("test", "all"))
    parser.add_argument("--output", type=Path, default=Path("D:/gsd_cabin/output"))
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--clips", nargs="+", help="单帧试渲时只检查指定片段")
    parser.add_argument("--main-background", action="append", default=[], help="单帧试渲时额外检查一个主镜头背景变体")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not bpy.app.background or bpy.app.version[:2] != (5, 2):
        parser.error("需要以 Blender 5.2 无界面运行")
    if args.mode == "all" and not args.ffmpeg:
        parser.error("全量编码需要 --ffmpeg 或 PATH 上的 FFmpeg")
    if args.mode == "all" and (args.clips or args.main_background):
        parser.error("--clips 和 --main-background 只用于单帧试渲")
    args.output = args.output.resolve()
    run(args)


if __name__ == "__main__":
    main()
