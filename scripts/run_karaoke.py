#!/usr/bin/env python3
"""Render three-line karaoke outputs from one MP4 and one verified SRT."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-template"


def run(args: list[str], *, cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=os.fspath(cwd) if cwd else None,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )


def require_tools() -> None:
    missing = [name for name in ("python", "ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "缺少 " + ", ".join(missing) + "。请安装 Python 3.12；FFmpeg 可用 "
            "winget install Gyan.FFmpeg 安装，然后重新打开终端。"
        )
    filters = run(["ffmpeg", "-hide_banner", "-filters"], capture=True)
    if " subtitles " not in filters.stdout or " ass " not in filters.stdout:
        raise RuntimeError("当前 FFmpeg 缺少 libass 的 subtitles/ass 滤镜，请安装 Gyan full build。")


def cache_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "karaoke-from-mp4"
    return Path(tempfile.gettempdir()) / "karaoke-from-mp4"


def unique_job_dir(video: Path, requested: str | None) -> Path:
    base = Path(requested).expanduser().resolve() if requested else video.parent / f"{video.stem}_卡拉OK输出"
    if not base.exists() or not any(base.iterdir()):
        return base
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = base.with_name(f"{base.name}_{stamp}")
    counter = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}_{stamp}_{counter}")
        counter += 1
    return candidate


def copy_template(job_dir: Path) -> None:
    if not TEMPLATE_ROOT.is_dir():
        raise RuntimeError(f"Skill 项目模板缺失：{TEMPLATE_ROOT}")
    shutil.copytree(TEMPLATE_ROOT, job_dir, dirs_exist_ok=True)
    (job_dir / "input").mkdir(parents=True, exist_ok=True)
    (job_dir / "output").mkdir(parents=True, exist_ok=True)


def runtime_python() -> Path:
    runtime = cache_root() / "runtime"
    python_path = runtime / "Scripts" / "python.exe"
    marker = runtime / ".ready"
    if python_path.is_file() and marker.is_file():
        return python_path
    runtime.parent.mkdir(parents=True, exist_ok=True)
    proc = run([sys.executable, "-m", "venv", os.fspath(runtime)], capture=True)
    if proc.returncode != 0:
        raise RuntimeError(f"创建 Skill 运行环境失败：{proc.stderr[-2000:]}")
    proc = run([os.fspath(python_path), "-m", "pip", "install", "PyYAML>=6.0.2,<7"], capture=True)
    if proc.returncode != 0:
        raise RuntimeError(f"安装 PyYAML 失败：{proc.stderr[-2000:]}")
    marker.write_text("ready\n", encoding="ascii")
    return python_path


def render_job(
    job_dir: Path,
    video: Path,
    srt: Path,
    preview_only: bool,
    ass_only: bool,
    title: str | None,
    font_size_scale: float | None,
) -> None:
    python_path = runtime_python()
    command = [os.fspath(python_path), os.fspath(job_dir / "main.py"), os.fspath(video), os.fspath(srt)]
    if preview_only:
        command.append("--preview-only")
    if ass_only:
        command.append("--ass-only")
    if title:
        command += ["--title", title]
    if font_size_scale is not None:
        command += ["--font-size-scale", str(font_size_scale)]
    proc = run(command, cwd=job_dir)
    if proc.returncode != 0:
        raise RuntimeError(f"字幕渲染失败，请检查：{job_dir / 'output' / '处理日志.log'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用已核对的 MP4 和 SRT 生成三行卡拉OK字幕与视频")
    parser.add_argument("video", help="输入 MP4")
    parser.add_argument("subtitle", help="已人工核对的 SRT")
    parser.add_argument("--output-dir", help="任务输出目录；非空目录会自动改用带时间戳的新目录")
    parser.add_argument("--title", help="可选固定标题")
    parser.add_argument(
        "--font-size-scale",
        type=float,
        help="字幕字号倍率；默认读取稳定配置（1.0），例如 0.9、1.1、1.2",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview-only", action="store_true")
    mode.add_argument("--ass-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        video = Path(args.video).expanduser().resolve()
        subtitle = Path(args.subtitle).expanduser().resolve()
        if not video.is_file() or video.suffix.lower() != ".mp4":
            raise FileNotFoundError(f"输入视频必须是存在的 MP4：{video}")
        if not subtitle.is_file() or subtitle.suffix.lower() != ".srt":
            raise FileNotFoundError(f"输入字幕必须是存在的 SRT：{subtitle}")
        require_tools()
        if args.font_size_scale is not None and args.font_size_scale <= 0:
            raise ValueError("--font-size-scale 必须大于 0")
        job_dir = unique_job_dir(video, args.output_dir)
        copy_template(job_dir)
        copied_srt = job_dir / "input" / subtitle.name
        shutil.copy2(subtitle, copied_srt)
        if copied_srt.read_bytes() != subtitle.read_bytes():
            raise RuntimeError("SRT 副本校验失败，已停止处理。")
        print(f"输入视频：{video}")
        print(f"输入字幕：{subtitle}")
        print("歌词处理：原样保留，不听写、不翻译、不转换简繁体")
        render_job(
            job_dir,
            video,
            copied_srt,
            args.preview_only,
            args.ass_only,
            args.title,
            args.font_size_scale,
        )
        print(f"任务完成：{job_dir}")
        return 0
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
