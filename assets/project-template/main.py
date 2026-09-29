from __future__ import annotations

import argparse
from array import array
import json
import logging
import os
import shutil
import subprocess
import sys
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path

import yaml

from scripts.ass_generator import generate_ass
from scripts.subtitle_parser import parse_subtitle, split_long_cues


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
LOG_PATH = OUTPUT / "处理日志.log"


def setup_logging() -> logging.Logger:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("karaoke")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def check_environment(logger: logging.Logger) -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not command_exists(name)]
    if missing:
        raise RuntimeError(
            "缺少 FFmpeg/FFprobe。最简单安装方法：打开 PowerShell 执行 "
            "winget install Gyan.FFmpeg，然后重新打开终端。程序不会自动修改系统设置。"
        )
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if " subtitles " not in proc.stdout or " ass " not in proc.stdout:
        raise RuntimeError("当前 FFmpeg 未包含 libass（缺少 subtitles/ass 滤镜）。请安装 Gyan full build。")
    logger.info("环境检查通过：FFmpeg、FFprobe、libass 可用")


def _windows_font_catalog() -> list[tuple[str, Path]]:
    if os.name != "nt":
        return []
    import winreg

    catalog: list[tuple[str, Path]] = []
    registry_paths = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    )
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for hive, key_path in registry_paths:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                index = 0
                while True:
                    try:
                        value_name, value_data, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    index += 1
                    if not isinstance(value_data, str):
                        continue
                    path = Path(os.path.expandvars(value_data))
                    if not path.is_absolute():
                        path = fonts_dir / path
                    label = value_name.rsplit(" (", 1)[0]
                    for face_name in (part.strip() for part in label.split(" & ")):
                        if face_name:
                            catalog.append((face_name, path))
        except FileNotFoundError:
            continue
    return catalog


def resolve_font(config: dict, logger: logging.Logger) -> tuple[str, Path]:
    subtitle = config["subtitle"]
    requested = str(subtitle["font"])
    candidates = [requested, *(str(name) for name in subtitle.get("font_fallbacks", []))]
    catalog = _windows_font_catalog()

    for candidate_index, family in enumerate(candidates):
        for desired_face in (f"{family} Bold", family):
            match = next(
                ((face, path) for face, path in catalog if face.casefold() == desired_face.casefold() and path.is_file()),
                None,
            )
            if not match:
                continue
            face, path = match
            if candidate_index or desired_face.casefold() != f"{requested} Bold".casefold():
                logger.warning(
                    "指定字体不可用或缺少粗体：%s；fallback 字体：%s；字体文件：%s",
                    requested,
                    face,
                    path,
                )
            else:
                logger.info("实际使用字体：%s；字体文件：%s", face, path)
            return family, path

    raise RuntimeError(
        f"指定字体和 fallback 字体均不存在：{', '.join(candidates)}。"
        "为避免静默替换，已停止渲染。"
    )


def _candidate_roots() -> list[Path]:
    roots = [ROOT, ROOT / "input"]
    return [root for root in roots if root.exists()]


def scan_candidates() -> tuple[list[Path], list[Path]]:
    videos: list[Path] = []
    subtitles: list[Path] = []
    for folder in _candidate_roots():
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() == ".mp4":
                if "参考" not in path.stem:
                    videos.append(path)
            elif path.suffix.lower() in {".srt", ".lrc", ".json"}:
                subtitles.append(path)
    return sorted(set(videos)), sorted(set(subtitles))


def choose_inputs(video_arg: str | None, subtitle_arg: str | None) -> tuple[Path, Path]:
    if video_arg and subtitle_arg:
        video, subtitle = Path(video_arg).resolve(), Path(subtitle_arg).resolve()
        if not video.is_file() or not subtitle.is_file():
            raise FileNotFoundError("指定的视频或字幕不存在")
        return video, subtitle
    videos, subtitles = scan_candidates()
    if not subtitles:
        raise RuntimeError("未找到 SRT/LRC/JSON 字幕。请先从剪映导出 SRT；本工具不会对歌曲强行语音识别。")
    if not videos:
        raise RuntimeError("未找到 MP4 视频。请把视频放到项目根目录或 input 目录。")
    if len(videos) > 1:
        names = "\n".join(f"  - {path.name}" for path in videos)
        raise RuntimeError(f"发现多个视频候选，请拖拽指定视频和字幕到 run.bat：\n{names}")
    video = videos[0]
    if subtitle_arg:
        return video, Path(subtitle_arg).resolve()
    ranked = sorted(
        subtitles,
        key=lambda path: SequenceMatcher(None, video.stem.casefold(), path.stem.casefold()).ratio(),
        reverse=True,
    )
    best_score = SequenceMatcher(None, video.stem.casefold(), ranked[0].stem.casefold()).ratio()
    tied = [path for path in ranked if abs(SequenceMatcher(None, video.stem.casefold(), path.stem.casefold()).ratio() - best_score) < 0.02]
    if len(tied) > 1:
        names = "\n".join(f"  - {path.name}" for path in tied)
        raise RuntimeError(f"发现多个接近的字幕候选，请拖拽指定文件到 run.bat：\n{names}")
    return video, ranked[0]


def probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,duration,nb_frames,sample_rate,channels",
            "-of", "json", os.fspath(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(proc.stdout)


def source_video_spec(path: Path) -> dict:
    info = probe(path)
    stream = next((item for item in info["streams"] if item["codec_type"] == "video"), None)
    if not stream:
        raise RuntimeError("输入文件没有视频流")
    fps_text = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    fps = Fraction(fps_text)
    if fps <= 0:
        raise RuntimeError("无法读取原视频帧率")
    duration = float(stream.get("duration") or info["format"]["duration"])
    frames = int(stream.get("nb_frames") or round(duration * float(fps)))
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps_text": fps_text,
        "fps": float(fps),
        "duration": duration,
        "frames": frames,
    }


def _ass_filter_path(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    return relative.replace("'", r"'\''")


def build_filter(config: dict, ass_path: Path) -> tuple[str, bool]:
    width, height = int(config["output"]["width"]), int(config["output"]["height"])
    pre = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    subs = f"subtitles=filename='{_ass_filter_path(ass_path)}':fontsdir='C\\:/Windows/Fonts'"
    cleanup = config.get("source_cleanup", {})
    spectrum = config.get("decorations", {}).get("spectrum_enabled", False)
    if cleanup.get("mask_burned_subtitle", False):
        x, y = int(cleanup["x"]), int(cleanup["y"])
        w, h = int(cleanup["width"]), int(cleanup["height"])
        source_y = int(cleanup.get("clone_source_y", y + h))
        complex_filter = (
            f"[0:v]{pre},split=2[main][patch];"
            f"[patch]crop=w={w}:h={h}:x={x}:y={source_y}[patchc];"
            f"[main][patchc]overlay=x={x}:y={y}[clean];"
            f"[clean]{subs}[subbed]"
        )
        if not spectrum:
            return complex_filter + ";[subbed]null[v]", True
    elif not spectrum:
        return f"{pre},{subs}", False
    else:
        complex_filter = f"[0:v]{pre},{subs}[subbed]"
    y = int(config["decorations"].get("spectrum_y", height - 260))
    complex_filter += (
        ";"
        "[0:a]aformat=channel_layouts=mono,showwaves=s=1080x150:mode=cline:rate=30:scale=lin:"
        "colors=0x8A2BE2,format=rgba,colorkey=black:0.06:0.04,colorchannelmixer=aa=0.88[spec];"
        f"[subbed][spec]overlay=x=0:y={y}:shortest=1[v]"
    )
    return complex_filter, True


def available_encoders() -> str:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stdout


def render(video: Path, ass_path: Path, destination: Path, config: dict, logger: logging.Logger, preview: bool) -> None:
    filter_value, is_complex = build_filter(config, ass_path)
    encoders = available_encoders()
    candidates = []
    if config["output"].get("prefer_hardware", True):
        for encoder in ("h264_nvenc", "h264_qsv", "h264_amf"):
            if encoder in encoders:
                candidates.append(encoder)
    candidates.append("libx264")
    duration_args = ["-t", str(config["output"].get("preview_seconds", 10))] if preview else []
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for encoder in candidates:
        temp_path = destination.with_name(destination.stem + f".{encoder}.partial.mp4")
        args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", os.fspath(video), *duration_args]
        if is_complex:
            args += ["-filter_complex", filter_value, "-map", "[v]", "-map", "0:a?"]
        else:
            args += ["-vf", filter_value, "-map", "0:v:0", "-map", "0:a?"]
        args += ["-c:v", encoder]
        if encoder == "libx264":
            args += ["-preset", "medium" if not preview else "veryfast", "-crf", str(config["output"].get("final_crf", 18) if not preview else 27)]
        elif encoder == "h264_nvenc":
            args += ["-preset", "p5", "-cq", "19" if not preview else "28", "-b:v", "0"]
        elif encoder == "h264_qsv":
            args += ["-global_quality", "20" if not preview else "28"]
        else:
            args += ["-quality", "balanced", "-qp_i", "20" if not preview else "28"]
        if preview:
            args += ["-maxrate", str(config["output"].get("preview_video_bitrate", "1800k")), "-bufsize", "3600k"]
        args += ["-c:a", "aac", "-b:a", str(config["output"].get("audio_bitrate", "192k")), "-movflags", "+faststart", os.fspath(temp_path)]
        logger.info("尝试编码器 %s", encoder)
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0 and temp_path.exists():
            os.replace(temp_path, destination)
            logger.info("已生成 %s（编码器 %s）", destination, encoder)
            return
        last_error = proc.stderr[-4000:]
        logger.warning("编码器 %s 失败，尝试回退：%s", encoder, last_error[-500:])
        if temp_path.exists():
            temp_path.unlink()
    raise RuntimeError(f"所有 H.264 编码器均失败：\n{last_error}")


def render_transparent(
    source_video: Path,
    ass_path: Path,
    destination: Path,
    logger: logging.Logger,
    preview_seconds: float | None = None,
) -> dict:
    spec = source_video_spec(source_video)
    frames = spec["frames"]
    if preview_seconds is not None:
        frames = min(frames, int(round(preview_seconds * spec["fps"])))
    source_duration = max(spec["duration"], frames / spec["fps"] + 1.0)
    transparent_source = (
        f"color=c=black@0.0:s={spec['width']}x{spec['height']}:"
        f"r={spec['fps_text']}:d={source_duration:.6f},format=rgba"
    )
    subtitle_filter = (
        f"subtitles=filename='{_ass_filter_path(ass_path)}':"
        "fontsdir='C\\:/Windows/Fonts':alpha=1,format=yuva444p10le"
    )
    temp_path = destination.with_name(destination.stem + ".prores_ks.partial.mov")
    args = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "lavfi", "-i", transparent_source,
        "-vf", subtitle_filter,
        "-frames:v", str(frames), "-an",
        "-c:v", "prores_ks", "-profile:v", "4",
        "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
        "-vendor", "apl0", "-movflags", "+faststart",
        os.fspath(temp_path),
    ]
    logger.info(
        "生成透明字幕 MOV：%sx%s，%s fps，%s 帧，ProRes 4444",
        spec["width"], spec["height"], spec["fps_text"], frames,
    )
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not temp_path.exists():
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"ProRes 4444 透明字幕渲染失败：\n{proc.stderr[-4000:]}")
    os.replace(temp_path, destination)
    logger.info("已生成透明字幕：%s", destination)
    return {**spec, "frames": frames, "duration": frames / spec["fps"]}


def validate_alpha_mov(path: Path, expected: dict, logger: logging.Logger) -> None:
    info = probe(path)
    video_streams = [stream for stream in info["streams"] if stream["codec_type"] == "video"]
    audio_streams = [stream for stream in info["streams"] if stream["codec_type"] == "audio"]
    if len(video_streams) != 1:
        raise RuntimeError("透明 MOV 必须且只能包含一个视频流")
    stream = video_streams[0]
    if stream.get("codec_name") != "prores" or "4444" not in str(stream.get("profile", "")):
        raise RuntimeError(f"透明 MOV 不是 ProRes 4444：{stream.get('codec_name')} / {stream.get('profile')}")
    if stream.get("pix_fmt") not in {"yuva444p10le", "yuva444p12le"}:
        raise RuntimeError(f"透明 MOV 未使用 Alpha 像素格式：{stream.get('pix_fmt')}")
    if audio_streams:
        raise RuntimeError("透明字幕 MOV 不应包含音频")
    if int(stream["width"]) != expected["width"] or int(stream["height"]) != expected["height"]:
        raise RuntimeError("透明字幕 MOV 分辨率与原视频不一致")
    if Fraction(stream.get("avg_frame_rate") or stream["r_frame_rate"]) != Fraction(expected["fps_text"]):
        raise RuntimeError("透明字幕 MOV 帧率与原视频不一致")
    actual_frames = int(stream.get("nb_frames") or round(float(stream["duration"]) * expected["fps"]))
    if actual_frames != expected["frames"]:
        raise RuntimeError(f"透明字幕 MOV 帧数不一致：{actual_frames} != {expected['frames']}")
    expected_duration = expected["frames"] / expected["fps"]
    actual_duration = float(stream.get("duration") or info["format"]["duration"])
    if abs(actual_duration - expected_duration) > 1 / expected["fps"] + 0.001:
        raise RuntimeError("透明字幕 MOV 时长与原视频视频流不一致")

    sample_time = min(1.5, max(0.0, expected_duration / 2))
    alpha_proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{sample_time:.3f}",
            "-i", os.fspath(path), "-vf", "alphaextract,format=gray16le",
            "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        capture_output=True,
    )
    if alpha_proc.returncode != 0:
        error_text = alpha_proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Alpha 平面读取失败：\n{error_text[-2000:]}")
    alpha_values = array("H")
    alpha_values.frombytes(alpha_proc.stdout)
    if not alpha_values:
        raise RuntimeError("Alpha 平面为空")
    alpha_min, alpha_max = min(alpha_values), max(alpha_values)
    # ProRes 4444 stores 12-bit alpha. When FFmpeg expands it to gray16le,
    # fully opaque samples can be reported as 65520 (4095 << 4) instead of
    # 65535. Both values represent a complete 12-bit alpha range.
    if alpha_min != 0 or alpha_max < 65520:
        raise RuntimeError(f"Alpha 通道无效：最小值 {alpha_min}，最大值 {alpha_max}")
    logger.info(
        "Alpha 验证通过：pix_fmt=%s，Alpha 范围=%d..%d，%s 帧，无音频",
        stream["pix_fmt"], alpha_min, alpha_max, actual_frames,
    )


def validate_media(path: Path, expected_max_duration: float | None = None) -> None:
    info = probe(path)
    video_stream = next((stream for stream in info["streams"] if stream["codec_type"] == "video"), None)
    audio_stream = next((stream for stream in info["streams"] if stream["codec_type"] == "audio"), None)
    if not video_stream or video_stream.get("codec_name") != "h264":
        raise RuntimeError("输出视频不是 H.264")
    if not audio_stream or audio_stream.get("codec_name") != "aac":
        raise RuntimeError("输出音频不是 AAC")
    if expected_max_duration and float(info["format"]["duration"]) > expected_max_duration + 0.25:
        raise RuntimeError("预览时长超出预期")


def main() -> int:
    parser = argparse.ArgumentParser(description="三行滚动卡拉OK字幕生成器")
    parser.add_argument("video", nargs="?", help="MP4 视频路径")
    parser.add_argument("subtitle", nargs="?", help="SRT/LRC/JSON 字幕路径")
    parser.add_argument("--config", default=os.fspath(ROOT / "config.yaml"))
    parser.add_argument("--title", help="可选固定标题")
    parser.add_argument(
        "--font-size-scale",
        type=float,
        help="字幕字号倍率；默认读取 config.yaml 中的 1.0",
    )
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--ass-only", action="store_true")
    args = parser.parse_args()
    logger = setup_logging()
    internal_ass_path = OUTPUT / ".内部渲染_完整样式.ass"
    transparent_ass_path = OUTPUT / ".内部渲染_透明字幕.ass"
    try:
        check_environment(logger)
        video, subtitle = choose_inputs(args.video, args.subtitle)
        logger.info("输入视频：%s", video)
        logger.info("输入字幕：%s", subtitle)
        config = load_config(Path(args.config))
        subtitle_config = config["subtitle"]
        if "font_size" in subtitle_config:
            raise RuntimeError("检测到旧版 font_size 配置；稳定版只允许使用 base_font_size")
        required_style_keys = (
            "stable_style_version",
            "base_play_res_x",
            "base_play_res_y",
            "base_font_size",
            "font_size_scale",
        )
        missing_style_keys = [key for key in required_style_keys if key not in subtitle_config]
        if missing_style_keys:
            raise RuntimeError("稳定字幕配置缺少字段：" + ", ".join(missing_style_keys))
        if args.font_size_scale is not None and args.font_size_scale <= 0:
            raise ValueError("--font-size-scale 必须大于 0")
        if args.title:
            title = args.title.strip("《》")
            config["decorations"]["title"] = f"《{title}》"
            config["decorations"]["title_enabled"] = True

        resolved_font, font_path = resolve_font(config, logger)
        output_width = int(config["output"]["width"])
        output_height = int(config["output"]["height"])
        cues = parse_subtitle(subtitle)
        cues = split_long_cues(cues, int(subtitle_config["max_chars_per_line"]))
        ass_path = OUTPUT / "三行卡拉OK字幕.ass"
        metrics = generate_ass(
            cues,
            config,
            ass_path,
            include_decorations=False,
            play_res=(output_width, output_height),
            font_size_scale=args.font_size_scale,
            font_name=resolved_font,
        )
        logger.info(
            "稳定字幕配置：version=%s；最终视频分辨率=%dx%d；PlayResX=%d；PlayResY=%d；"
            "base_font_size=%d；font_size_scale=%g；最终 Fontsize=%d",
            subtitle_config["stable_style_version"],
            output_width,
            output_height,
            metrics["play_res_x"],
            metrics["play_res_y"],
            metrics["base_font_size"],
            metrics["font_size_scale"],
            metrics["font_size"],
        )
        logger.info("字幕字体：%s；字体文件路径：%s", resolved_font, font_path)
        logger.info("每个滚动字幕段最多 %d 个字符；水平中心 x=%d", subtitle_config["max_chars_per_line"], metrics["center_x"])
        logger.info("已生成 ASS：%s（%d 个歌词段）", ass_path, len(cues))
        if args.ass_only:
            return 0
        generate_ass(
            cues,
            config,
            internal_ass_path,
            include_decorations=True,
            play_res=(output_width, output_height),
            font_size_scale=args.font_size_scale,
            font_name=resolved_font,
        )
        source_spec = source_video_spec(video)
        transparent_metrics = generate_ass(
            cues,
            config,
            transparent_ass_path,
            include_decorations=False,
            play_res=(source_spec["width"], source_spec["height"]),
            font_size_scale=args.font_size_scale,
            font_name=resolved_font,
        )
        logger.info(
            "透明轨字幕画布：PlayResX=%d；PlayResY=%d；最终 Fontsize=%d；描边=%g",
            transparent_metrics["play_res_x"],
            transparent_metrics["play_res_y"],
            transparent_metrics["font_size"],
            transparent_metrics["outline"],
        )
        preview_path = OUTPUT / "歌词预览_10秒.mp4"
        render(video, internal_ass_path, preview_path, config, logger, preview=True)
        validate_media(preview_path, float(config["output"].get("preview_seconds", 10)))
        logger.info("预览技术检查通过：H.264 + AAC，时长和媒体流正常")
        transparent_preview_path = OUTPUT / "透明卡拉OK字幕_10秒预览.mov"
        transparent_preview_spec = render_transparent(
            video,
            transparent_ass_path,
            transparent_preview_path,
            logger,
            preview_seconds=float(config["output"].get("preview_seconds", 10)),
        )
        validate_alpha_mov(transparent_preview_path, transparent_preview_spec, logger)
        logger.info("10 秒透明字幕预览验证成功，允许继续完整渲染")
        if not args.preview_only:
            final_path = OUTPUT / "最终视频_已烧录字幕.mp4"
            render(video, internal_ass_path, final_path, config, logger, preview=False)
            validate_media(final_path)
            logger.info("烧录版最终视频技术检查通过")
            transparent_path = OUTPUT / "透明卡拉OK字幕.mov"
            transparent_spec = render_transparent(video, transparent_ass_path, transparent_path, logger)
            validate_alpha_mov(transparent_path, transparent_spec, logger)
            logger.info("完整透明字幕 MOV 技术检查通过")
        return 0
    except Exception as exc:
        logger.exception("处理失败：%s", exc)
        print(f"\n错误：{exc}", file=sys.stderr)
        return 1
    finally:
        for temporary_ass in (internal_ass_path, transparent_ass_path):
            if temporary_ass.exists():
                temporary_ass.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
