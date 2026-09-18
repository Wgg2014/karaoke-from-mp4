---
name: karaoke-from-mp4
description: Generate three-line scrolling karaoke subtitles and finished videos from one local MP4 plus one user-verified SRT. Use when lyrics and timestamps are already supplied and the task is to create ASS karaoke highlighting, a burned H.264/AAC video, or a ProRes 4444 transparent overlay. Do not use this skill to transcribe, translate, normalize, or guess lyrics.
---

# Karaoke From MP4 + SRT

Require exactly two inputs: the source MP4 and a user-verified SRT. Treat both inputs as read-only. Preserve the SRT wording exactly; do not run speech recognition, translate text, convert simplified/traditional Chinese, or replace interjections.

## Run

1. Resolve the MP4 and SRT to absolute paths. When either input is ambiguous or multiple candidates exist, list the filenames and ask the user to choose. Never guess the pairing.
2. Check that `python`, `ffmpeg`, and `ffprobe` are available and that FFmpeg contains the `subtitles`/`ass` libass filters. Do not change system settings. If FFmpeg is missing, tell the user to run `winget install Gyan.FFmpeg` and stop.
3. Execute:

   ```powershell
   python "<skill-dir>\scripts\run_karaoke.py" "<absolute-video.mp4>" "<absolute-lyrics.srt>"
   ```

   Options:

   - `--output-dir <dir>` selects the job directory.
   - `--title "歌名"` adds a fixed title; it is disabled by default.
   - `--preview-only` creates the ASS and both 10-second previews without full-length outputs.
   - `--ass-only` creates only the ASS after validating the SRT.

4. Inspect the generated 10-second preview and processing log. Report any visible overlap, missing glyphs, or source video that already contains burned subtitles. Do not rewrite lyrics to make the preview look better.

## Output contract

The runner creates a new job directory beside the MP4 unless `--output-dir` is supplied. It never overwrites a non-empty job directory; a timestamped sibling is used instead.

- `input/<srt-name>`: a byte-for-byte copy of the supplied SRT.
- `output/三行卡拉OK字幕.ass`: intermediate karaoke ASS.
- `output/歌词预览_10秒.mp4`: H.264/AAC review preview.
- `output/透明卡拉OK字幕_10秒预览.mov`: ProRes 4444 alpha preview.
- `output/最终视频_已烧录字幕.mp4`: publishable H.264/AAC video.
- `output/透明卡拉OK字幕.mov`: full-length alpha overlay without audio.
- `output/处理日志.log`: render and validation log.

The transparent MOV must match the source resolution, frame rate, duration, and frame count. Validate its Alpha plane before rendering the full overlay. Preserve source audio timing and never modify either input file.

## Default design

Use three lines in the lower-middle safe zone, weighted `\kf` timing between each SRT cue's start and end, Microsoft YaHei UI bold text, a heavy black outline, `#FF4057` progressive highlighting, and a 0.20-second upward transition. When one SRT cue exceeds `max_chars_per_line`, split it at the best punctuation, space, or semantic boundary into at most two consecutive timed cues; preserve every character and divide the original time proportionally. Keep spectrum, particles, title, and source-subtitle masking disabled unless explicitly requested.

For Jianying/CapCut, put the original MP4 on the main track and the transparent MOV on the track above it, align both at 00:00, do not retime the subtitle track separately, and export them together.
