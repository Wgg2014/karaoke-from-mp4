from __future__ import annotations

import math
import re
from pathlib import Path

from .subtitle_parser import Cue, WordTiming


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    centiseconds = int(round(seconds * 100))
    h, remainder = divmod(centiseconds, 360000)
    m, remainder = divmod(remainder, 6000)
    s, cs = divmod(remainder, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color: str, opacity: float = 1.0) -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"颜色必须是 #RRGGBB: {hex_color}")
    r, g, b = value[0:2], value[2:4], value[4:6]
    alpha = round((1.0 - max(0.0, min(1.0, opacity))) * 255)
    return f"&H{alpha:02X}{b}{g}{r}"


def _override_color(hex_color: str) -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"颜色必须是 #RRGGBB: {hex_color}")
    r, g, b = value[0:2], value[2:4], value[4:6]
    return f"&H{b}{g}{r}&"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


_TOKEN = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[\u3400-\u9fff]|\s+|.", re.S)
_PUNCT = set("，。！？；：、,.!?;:…—-（）()《》\"“”'‘’ ")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _weights(tokens: list[str], mode: str) -> list[float]:
    values: list[float] = []
    for token in tokens:
        if token.isspace() or all(ch in _PUNCT for ch in token):
            values.append(0.05)
        elif re.fullmatch(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", token):
            values.append(1.0 if mode == "equal" else max(1.0, len(token) * 0.38))
        else:
            values.append(1.0)
    return values


def _allocate_cs(total_cs: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    raw = [total_cs * weight / sum(weights) for weight in weights]
    base = [int(math.floor(value)) for value in raw]
    for index in sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)[: total_cs - sum(base)]:
        base[index] += 1
    return base


def karaoke_text(cue: Cue, mode: str) -> str:
    if cue.words:
        segments: list[str] = []
        cursor = cue.start
        for word in cue.words:
            gap = max(0, int(round((word.start - cursor) * 100)))
            if gap:
                segments.append(rf"{{\k{gap}}}​")
            duration = max(0, int(round((word.end - word.start) * 100)))
            segments.append(rf"{{\kf{duration}}}{_escape(word.text)}")
            cursor = max(cursor, word.end)
        return "".join(segments)
    tokens = tokenize(cue.text)
    durations = _allocate_cs(max(1, int(round((cue.end - cue.start) * 100))), _weights(tokens, mode))
    return "".join(rf"{{\kf{duration}}}{_escape(token)}" for token, duration in zip(tokens, durations))


def _dialogue(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}"


def generate_ass(cues: list[Cue], config: dict, destination: Path, include_decorations: bool = True) -> None:
    sub = config["subtitle"]
    output = config["output"]
    decor = config.get("decorations", {})
    width, height = int(output["width"]), int(output["height"])
    font = sub["font"]
    font_size = int(sub["font_size"])
    outline = float(sub["outline"])
    shadow = float(sub["shadow"])
    current = _ass_color(sub["current_color"])
    white = _ass_color(sub["normal_color"])
    previous = _ass_color(sub["normal_color"], float(sub["previous_opacity"]))
    following = _ass_color(sub["normal_color"], float(sub["next_opacity"]))
    x = int(sub["center_x"])
    y_prev, y_cur, y_next = (int(sub[key]) for key in ("previous_y", "current_y", "next_y"))
    spacing = int(sub["line_spacing"])
    transition_ms = int(round(float(sub["transition_seconds"]) * 1000))
    scroll = bool(sub.get("enable_three_line_scroll", True))
    mode = sub.get("timing_mode", "weighted")
    title_font = decor.get("title_font", "KaiTi")
    title_size = int(decor.get("title_size", 70))
    note_size = int(decor.get("subtitle_size", 34))

    header = f"""[Script Info]
Title: Three-line karaoke subtitles
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Previous,{font},{font_size},{previous},{previous},&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1
Style: CurrentBase,{font},{font_size},{white},{white},&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1
Style: CurrentHighlight,{font},{font_size},{current},{white},&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,0,0,0,1
Style: Next,{font},{font_size},{following},{following},&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1
Style: Title,{title_font},{title_size},{_ass_color(decor.get('title_normal_color', '#111111'))},{_ass_color(decor.get('title_normal_color', '#111111'))},&H00FFFFFF,&H78000000,-1,0,0,0,100,100,1,0,1,3,2,8,0,0,0,1
Style: Note,{title_font},{note_size},{white},{white},&H00000000,&H78000000,-1,-1,0,0,100,100,1,0,1,3,1,8,0,0,0,1
Style: Particle,Arial,22,&H003CFFF0,&H003CFFF0,&H006E24B8,&H00000000,-1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    total_end = max((cue.end for cue in cues), default=1.0) + float(decor.get("tail_seconds", 0))
    if include_decorations and decor.get("title_enabled", False) and decor.get("title"):
        title = str(decor["title"])
        accent = str(decor.get("title_accent_text", ""))
        prefix = title[:-len(accent)] if accent and title.endswith(accent) else title
        suffix = accent if accent and title.endswith(accent) else ""
        bracket = prefix[:1] if prefix.startswith("《") else ""
        prefix_body = prefix[1:] if bracket else prefix
        title_markup = (
            rf"{{\1c{_override_color(decor.get('title_bracket_color', '#6F2798'))}}}{_escape(bracket)}"
            rf"{{\1c{_override_color(decor.get('title_normal_color', '#111111'))}}}{_escape(prefix_body)}"
            rf"{{\1c{_override_color(decor.get('title_accent_color', '#E6292F'))}}}{_escape(suffix)}"
        )
        title_y = int(decor.get("title_y", 485))
        events.append(_dialogue(0, 0, total_end, "Title", rf"{{\pos({width // 2},{title_y})}}{title_markup}"))
        if decor.get("subtitle"):
            note_y = int(decor.get("subtitle_y", 610))
            events.append(_dialogue(0, 0, total_end, "Note", rf"{{\pos({width // 2},{note_y})}}{_escape(str(decor['subtitle']))}"))
    if include_decorations and decor.get("particles_enabled", False):
        cycle = 0.0
        particle_index = 0
        while cycle < total_end:
            for index in range(8):
                start = cycle + index * 0.43
                if start >= total_end:
                    break
                end = min(total_end, start + 1.35 + (index % 3) * 0.18)
                px = 35 + ((particle_index * 137) % (width - 70))
                py = 1770 - ((particle_index * 47) % 150)
                drift = 22 + (particle_index % 4) * 11
                color = "&H003CFFF0&" if particle_index % 2 else "&H00E735A8&"
                size = 14 + (particle_index % 4) * 4
                events.append(_dialogue(0, start, end, "Particle", rf"{{\move({px},{py},{px + 8},{py - drift})\fad(250,500)\1c{color}\fs{size}}}•"))
                particle_index += 1
            cycle += 3.6

    for index, cue in enumerate(cues):
        start = cue.start
        end = max(cue.end, cues[index + 1].start) if index + 1 < len(cues) else cue.end
        if end <= start:
            continue
        if index > 0:
            previous_text = _escape(cues[index - 1].text)
            motion = rf"\move({x},{y_cur},{x},{y_prev},0,{transition_ms})" if scroll else rf"\pos({x},{y_prev})"
            exit_end = min(end, start + transition_ms / 1000)
            events.append(_dialogue(1, start, exit_end, "Previous", rf"{{{motion}\fad(0,{transition_ms})}}{previous_text}"))
        current_motion = rf"\move({x},{y_next},{x},{y_cur},0,{transition_ms})" if scroll and index > 0 else rf"\pos({x},{y_cur})"
        events.append(_dialogue(2, start, end, "CurrentBase", rf"{{{current_motion}}}{_escape(cue.text)}"))
        events.append(_dialogue(4, start, end, "CurrentHighlight", rf"{{{current_motion}}}{karaoke_text(cue, mode)}"))
        if index + 1 < len(cues):
            next_text = _escape(cues[index + 1].text)
            next2_y = y_next + spacing
            motion = rf"\move({x},{next2_y},{x},{y_next},0,{transition_ms})" if scroll and index > 0 else rf"\pos({x},{y_next})"
            events.append(_dialogue(2, start, end, "Next", rf"{{{motion}}}{next_text}"))
        if index + 2 < len(cues):
            next2_text = _escape(cues[index + 2].text)
            next2_y = y_next + spacing
            enter_y = next2_y + spacing
            motion = rf"\move({x},{enter_y},{x},{next2_y},0,{transition_ms})" if scroll and index > 0 else rf"\pos({x},{next2_y})"
            events.append(_dialogue(1, start, end, "Next", rf"{{{motion}}}{next2_text}"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
