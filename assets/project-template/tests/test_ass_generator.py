from pathlib import Path

import yaml

from scripts.ass_generator import karaoke_text, generate_ass, resolve_ass_style
from scripts.subtitle_parser import Cue, WordTiming


ROOT = Path(__file__).resolve().parents[1]


def test_karaoke_is_progressive_and_exact_duration() -> None:
    cue = Cue(0.0, 3.0, "我 love 你！")
    text = karaoke_text(cue, "weighted")
    assert "\\kf" in text
    durations = [int(part.split("}")[0]) for part in text.split("{\\kf")[1:]]
    assert sum(durations) == 300


def test_ass_has_three_rows_and_motion(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    target = tmp_path / "测试.ass"
    generate_ass([Cue(0, 2, "第一句"), Cue(2, 4, "第二句"), Cue(4, 6, "第三句")], config, target)
    content = target.read_text(encoding="utf-8-sig")
    assert "Style: Previous" in content
    assert "Style: CurrentBase" in content
    assert "Style: CurrentHighlight" in content
    assert "Style: Next" in content
    assert "\\move(" in content
    assert "\\kf" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "Style: CurrentBase,Microsoft YaHei UI,84," in content


def test_stable_style_scales_once_for_4k_vertical_video() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    metrics = resolve_ass_style(config, 2160, 3840)
    assert metrics["base_font_size"] == 84
    assert metrics["font_size_scale"] == 1.0
    assert metrics["font_size"] == 168
    assert metrics["outline"] == 18
    assert metrics["center_x"] == 1080
    assert metrics["current_y"] == 2140


def test_font_size_override_is_relative_to_stable_default() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert resolve_ass_style(config, 1080, 1920, font_size_scale=0.9)["font_size"] == 76
    assert resolve_ass_style(config, 1080, 1920, font_size_scale=1.1)["font_size"] == 92
    assert resolve_ass_style(config, 1080, 1920, font_size_scale=1.2)["font_size"] == 101


def test_real_word_timing_preserves_leading_pause() -> None:
    cue = Cue(0.0, 2.0, "你好", [WordTiming("你", 0.3, 0.8), WordTiming("好", 1.0, 1.8)])
    text = karaoke_text(cue, "weighted")
    assert "{\\k30}\u200b" in text
    assert "{\\kf50}你" in text
    assert "{\\k20}\u200b" in text


def test_lyrics_only_ass_excludes_decorations(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    target = tmp_path / "lyrics-only.ass"
    generate_ass([Cue(0, 2, "第一句"), Cue(2, 4, "第二句"), Cue(4, 6, "第三句")], config, target, include_decorations=False)
    content = target.read_text(encoding="utf-8-sig")
    assert "经典歌曲" not in content
    assert "《披着羊皮的狼》" not in content
    assert "Style: CurrentHighlight" in content
    assert "{\\kf" in content
