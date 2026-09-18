from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class WordTiming:
    text: str
    start: float
    end: float


@dataclass(slots=True)
class Cue:
    start: float
    end: float
    text: str
    words: list[WordTiming] = field(default_factory=list)


_SRT_BLOCK = re.compile(
    r"(?:^|\n)\s*\d*\s*\n?"
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})[^\n]*\n"
    r"(?P<text>.*?)(?=\n\s*\n|\Z)",
    re.S,
)
_LRC_STAMP = re.compile(r"\[(\d{1,3}):(\d{2}(?:\.\d+)?)\]")
_ENHANCED_STAMP = re.compile(r"<(\d{1,3}):(\d{2}(?:\.\d+)?)>")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别字幕编码: {path}")


def _stamp(value: str) -> float:
    value = value.replace(",", ".")
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _lrc_stamp(minutes: str, seconds: str) -> float:
    return int(minutes) * 60 + float(seconds)


def parse_srt(path: Path) -> list[Cue]:
    text = _read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for match in _SRT_BLOCK.finditer(text.strip() + "\n"):
        body = " ".join(line.strip() for line in match.group("text").splitlines() if line.strip())
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            cues.append(Cue(_stamp(match.group("start")), _stamp(match.group("end")), body))
    if not cues:
        raise ValueError(f"SRT 中没有可用字幕: {path}")
    return cues


def parse_lrc(path: Path) -> list[Cue]:
    lines: list[tuple[float, str, list[tuple[float, str]]]] = []
    for raw_line in _read_text(path).splitlines():
        stamps = list(_LRC_STAMP.finditer(raw_line))
        if not stamps:
            continue
        content = raw_line[stamps[-1].end():].strip()
        if not content:
            continue
        enhanced = list(_ENHANCED_STAMP.finditer(content))
        word_marks: list[tuple[float, str]] = []
        if enhanced:
            for index, mark in enumerate(enhanced):
                stop = enhanced[index + 1].start() if index + 1 < len(enhanced) else len(content)
                token = content[mark.end():stop]
                word_marks.append((_lrc_stamp(mark.group(1), mark.group(2)), token))
            plain = _ENHANCED_STAMP.sub("", content).strip()
        else:
            plain = content
        for stamp in stamps:
            lines.append((_lrc_stamp(stamp.group(1), stamp.group(2)), plain, word_marks))
    lines.sort(key=lambda item: item[0])
    cues: list[Cue] = []
    for index, (start, text, marks) in enumerate(lines):
        end = lines[index + 1][0] if index + 1 < len(lines) else start + 3.0
        words: list[WordTiming] = []
        if marks:
            for j, (word_start, token) in enumerate(marks):
                word_end = marks[j + 1][0] if j + 1 < len(marks) else end
                words.append(WordTiming(token, word_start, max(word_start, word_end)))
        cues.append(Cue(start, max(start + 0.05, end), text, words))
    if not cues:
        raise ValueError(f"LRC 中没有可用歌词: {path}")
    return cues


def parse_json(path: Path) -> list[Cue]:
    data = json.loads(_read_text(path))
    items = data.get("cues", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("JSON 顶层应为数组，或包含 cues 数组")
    cues: list[Cue] = []
    for item in items:
        words = [
            WordTiming(str(word["text"]), float(word["start"]), float(word["end"]))
            for word in item.get("words", [])
        ]
        cues.append(Cue(float(item["start"]), float(item["end"]), str(item["text"]), words))
    return cues


def parse_subtitle(path: Path) -> list[Cue]:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(path)
    if suffix == ".lrc":
        return parse_lrc(path)
    if suffix == ".json":
        return parse_json(path)
    raise ValueError(f"不支持的字幕格式: {path.suffix}")


_BREAK_CHARS = set("，。！？；：、,.!?;: ")
_SOFT_BREAK_AFTER = set("的了着过吗呢啊吧呀和与及但而却又就才也都")
_PHRASE_STARTS = (
    "一只", "披着", "背负", "不是", "就是", "让我", "而你", "只求",
    "独自", "把你", "为了", "因为", "所以", "但是", "然后",
)


def _split_text(text: str, limit: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return [text]
    target = len(text) / 2
    minimum = max(1, min(4, len(text) // 4))
    candidates = range(minimum, len(text) - minimum + 1)

    def score(pos: int) -> float:
        left = text[pos - 1]
        right = text[pos] if pos < len(text) else ""
        boundary = 8 if left in _BREAK_CHARS else 1.5 if left in _SOFT_BREAK_AFTER else 0
        if right in _BREAK_CHARS:
            boundary += 5
        if any(text.startswith(phrase, pos) for phrase in _PHRASE_STARTS):
            boundary += 7
        return boundary - abs(pos - target)

    cut = max(candidates, key=score)
    return [text[:cut].strip(), text[cut:].strip()]


def split_long_cues(cues: Iterable[Cue], limit: int) -> list[Cue]:
    result: list[Cue] = []
    for cue in cues:
        if cue.words or len(cue.text) <= limit:
            result.append(cue)
            continue
        parts = _split_text(cue.text, limit)
        weights = [max(1, len(re.sub(r"\W", "", part))) for part in parts]
        total = sum(weights)
        cursor = cue.start
        for index, (part, weight) in enumerate(zip(parts, weights)):
            end = cue.end if index == len(parts) - 1 else cursor + (cue.end - cue.start) * weight / total
            result.append(Cue(cursor, end, part))
            cursor = end
    return result
