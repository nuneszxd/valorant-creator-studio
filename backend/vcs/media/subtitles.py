"""Subtitle cues and ASS generation (burned in with FFmpeg's `ass` filter).

A cue is {"start": s, "end": s, "text": str, "words": [{"start","end","text"}]} with times relative
to the start of the clip. Word timings drive the "highlight the word being spoken" style; when the
creator edits the text, words are re-spread evenly over the cue (an approximation, by design).
"""

from __future__ import annotations

import re
from typing import Any

from ..models import SubtitleStyle

_NON_WORD = re.compile(r"\W+")
_BAD_ASS = re.compile(r"[{}\\\r\n]")


def cues_from_segments(segments: list[dict[str, Any]], clip_start: float, clip_end: float) -> list[dict[str, Any]]:
    """Build cues (times relative to the clip) from stored transcript segments."""
    cues: list[dict[str, Any]] = []
    for seg in segments:
        if seg["end_s"] <= clip_start or seg["start_s"] >= clip_end:
            continue
        words: list[dict[str, Any]] = []
        for w in seg.get("words") or []:
            if w["end"] <= clip_start or w["start"] >= clip_end:
                continue
            words.append({
                "start": round(max(w["start"], clip_start) - clip_start, 3),
                "end": round(min(w["end"], clip_end) - clip_start, 3),
                "text": w["text"],
            })
        if words:
            start, end = words[0]["start"], words[-1]["end"]
            text = " ".join(w["text"] for w in words)
        else:
            start = max(seg["start_s"], clip_start) - clip_start
            end = min(seg["end_s"], clip_end) - clip_start
            text = seg["text"].strip()
        if end - start < 0.05 or not text:
            continue
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": text, "words": words})
    return cues


def _norm(token: str) -> str:
    return _NON_WORD.sub("", token.lower())


def words_for_cue(cue: dict[str, Any]) -> list[dict[str, Any]]:
    tokens = cue["text"].split()
    if not tokens:
        return []
    words = cue.get("words") or []
    if len(words) == len(tokens) and all(_norm(w["text"]) == _norm(t) for w, t in zip(words, tokens)):
        return [{"start": w["start"], "end": w["end"], "text": t} for w, t in zip(words, tokens)]
    duration = cue["end"] - cue["start"]
    if duration <= 0:
        return []
    step = duration / len(tokens)
    return [
        {"start": cue["start"] + i * step, "end": cue["start"] + (i + 1) * step, "text": tok}
        for i, tok in enumerate(tokens)
    ]


def chunk_words(words: list[dict[str, Any]], max_words: int, max_chars: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    chars = 0
    for word in words:
        extra = len(word["text"]) + (1 if current else 0)
        if current and (len(current) >= max_words or chars + extra > max_chars):
            chunks.append(current)
            current, chars, extra = [], 0, len(word["text"])
        current.append(word)
        chars += extra
    if current:
        chunks.append(current)
    return chunks


def ass_color(hex_color: str, alpha: str = "00") -> str:
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alpha}{b}{g}{r}".upper()


def inline_color(hex_color: str) -> str:
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{b}{g}{r}&".upper()


def ass_time(seconds: float) -> str:
    total_cs = int(round(max(0.0, seconds) * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _display(text: str, style: SubtitleStyle) -> str:
    cleaned = _BAD_ASS.sub(" ", text).strip()
    return cleaned.upper() if style.uppercase else cleaned


def build_ass(cues: list[dict[str, Any]], style: SubtitleStyle, width: int, height: int) -> str:
    fontsize = max(12, round(style.size_pct / 100 * height))
    outline = round(style.outline_px * height / 1920, 1)
    margin_v = round(style.position_pct / 100 * height)
    margin_lr = round(0.055 * width)
    bold = -1 if style.bold else 0
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{style.font},{fontsize},{ass_color(style.text_color)},{ass_color(style.text_color)},"
        f"{ass_color(style.outline_color)},{ass_color('#000000', '64')},{bold},0,0,0,100,100,0,0,1,"
        f"{outline},0,2,{margin_lr},{margin_lr},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    highlight = inline_color(style.highlight_color)
    for cue in cues:
        words = words_for_cue(cue)
        if not words:
            continue
        for chunk in chunk_words(words, style.max_words_per_line, style.max_chars_per_line):
            if style.highlight_words:
                for i, current in enumerate(chunk):
                    start = current["start"]
                    end = chunk[i + 1]["start"] if i + 1 < len(chunk) else current["end"]
                    end = max(end, start + 0.08)
                    parts = []
                    for j, word in enumerate(chunk):
                        text = _display(word["text"], style)
                        parts.append("{\\c" + highlight + "}" + text + "{\\r}" if j == i else text)
                    lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{' '.join(parts)}")
            else:
                text = " ".join(_display(w["text"], style) for w in chunk)
                end = max(chunk[-1]["end"], chunk[0]["start"] + 0.08)
                lines.append(f"Dialogue: 0,{ass_time(chunk[0]['start'])},{ass_time(end)},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"
