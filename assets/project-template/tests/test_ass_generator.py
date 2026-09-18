from pathlib import Path

import yaml

from scripts.ass_generator import karaoke_text, generate_ass
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
