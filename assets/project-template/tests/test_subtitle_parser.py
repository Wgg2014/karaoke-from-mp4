from pathlib import Path

from scripts.subtitle_parser import Cue, parse_json, parse_lrc, parse_srt, split_long_cues


def test_parse_utf8_srt(tmp_path: Path) -> None:
    path = tmp_path / "中文 歌词.srt"
    path.write_text("1\n00:00:00,100 --> 00:00:02,300\n你好，世界\n", encoding="utf-8")
    cues = parse_srt(path)
    assert cues[0].text == "你好，世界"
    assert cues[0].start == 0.1
    assert cues[0].end == 2.3


def test_long_cue_is_split_without_time_gap() -> None:
    cue = Cue(2.0, 8.0, "而你是我的猎物 不是我嘴里的羔羊")
    result = split_long_cues([cue], 14)
    assert len(result) == 2
    assert "".join(item.text.replace(" ", "") for item in result) == cue.text.replace(" ", "")
    assert result[0].start == 2.0
    assert result[-1].end == 8.0
    assert result[0].end == result[1].start
    assert all(len(item.text) <= 14 for item in result)


def test_phrase_is_not_broken_in_the_middle() -> None:
    result = split_long_cues([Cue(0, 5, "我确定我就是那一只披着羊皮的狼")], 8)
    assert [item.text for item in result] == ["我确定我就是那", "一只披着羊皮的狼"]


def test_very_long_srt_cue_is_split_into_safe_length_segments() -> None:
    cue = Cue(1.0, 11.0, "这是一个非常非常长的歌词字幕需要保留全部文字并且最多只能拆分成两个连续字幕段")
    result = split_long_cues([cue], 8)
    assert len(result) > 2
    assert "".join(item.text for item in result) == cue.text
    assert result[0].start == cue.start
    assert all(left.end == right.start for left, right in zip(result, result[1:]))
    assert result[-1].end == cue.end
    assert all(len(item.text) <= 8 for item in result)


def test_enhanced_lrc_keeps_word_timing(tmp_path: Path) -> None:
    path = tmp_path / "逐字.lrc"
    path.write_text("[00:01.00]<00:01.00>你<00:01.40>好\n[00:02.00]下一句", encoding="utf-8")
    cues = parse_lrc(path)
    assert cues[0].text == "你好"
    assert [(word.text, word.start) for word in cues[0].words] == [("你", 1.0), ("好", 1.4)]
    assert cues[0].words[-1].end == 2.0


def test_json_words_are_supported(tmp_path: Path) -> None:
    path = tmp_path / "timing.json"
    path.write_text(
        '[{"start":0,"end":1,"text":"OK","words":[{"text":"OK","start":0.2,"end":0.8}]}]',
        encoding="utf-8",
    )
    cue = parse_json(path)[0]
    assert cue.words[0].start == 0.2
    assert cue.words[0].end == 0.8
