"""SRT and ASS subtitle formatting — timestamp helpers, block builder, file generators."""

from __future__ import annotations
from typing import Any

from src.subtitles.presets import PRESETS
from src.utils.logger import get_logger

log = get_logger(__name__)


# ── Timestamp helpers ──────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h = ms // 3_600_000;  ms %= 3_600_000
    m = ms // 60_000;     ms %= 60_000
    s = ms // 1_000;      ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_timestamp(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h  = cs // 360000; cs %= 360000
    m  = cs // 6000;   cs %= 6000
    s  = cs // 100;    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _to_ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


# ── Block builder ──────────────────────────────────────────────────────────────

def build_blocks(
    word_entries: list[dict],
    words_per_line: int,
    lines_per_block: int,
    uppercase: bool,
    word_by_word: bool = False,
) -> list[dict]:
    """Build timed subtitle blocks from a flat word list.

    Returns list of {start: float, end: float, text: str} dicts.
    """
    if not word_entries:
        return []
    blocks: list[dict] = []
    if word_by_word:
        for wd in word_entries:
            text = wd["word"].upper() if uppercase else wd["word"]
            blocks.append({"start": wd["start_sec"], "end": wd["end_sec"], "text": text})
    else:
        max_words = words_per_line * lines_per_block
        for i in range(0, len(word_entries), max_words):
            chunk = word_entries[i : i + max_words]
            text_words = [(wd["word"].upper() if uppercase else wd["word"]) for wd in chunk]
            line_chunks = [
                " ".join(text_words[j : j + words_per_line])
                for j in range(0, len(text_words), words_per_line)
            ]
            blocks.append({
                "start": chunk[0]["start_sec"],
                "end":   chunk[-1]["end_sec"],
                "text":  "\n".join(line_chunks),
            })
    return blocks


# ── Public generators ──────────────────────────────────────────────────────────

def words_to_srt(
    words: list[dict],
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
) -> str:
    """Convert word-timing entries to an SRT subtitle file string."""
    preset = PRESETS.get(preset_name, PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("words_to_srt: no word entries to format")
        return ""

    blocks = build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)
    lines: list[str] = []
    for idx, block in enumerate(blocks, 1):
        start = _format_timestamp(block["start"])
        end   = _format_timestamp(block["end"])
        lines.extend([str(idx), f"{start} --> {end}", block["text"], ""])

    log.debug("Generated %d SRT subtitle entries (%s style)", len(blocks), preset_name)
    return "\n".join(lines)


def words_to_ass(
    words: list[dict],
    style: dict,
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
) -> str:
    """Convert word-timing entries to an ASS subtitle file string with visual styling."""
    preset = PRESETS.get(preset_name, PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("words_to_ass: no word entries to format")
        return ""

    blocks = build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)

    bold_flag      = -1 if style.get("bold",      False) else 0
    italic_flag    = -1 if style.get("italic",    False) else 0
    underline_flag = -1 if style.get("underline", False) else 0
    primary_col    = _to_ass_color(style.get("primary_color",  "#FFFFFF"))
    outline_col    = _to_ass_color(style.get("outline_color",  "#000000"))
    font_name      = style.get("font_family",    "Arial")
    font_size      = int(style.get("font_size",    36))
    outline_w      = int(style.get("outline_width", 3))
    shadow_depth   = int(style.get("shadow",        1))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "Timer: 100.0000\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_col},{primary_col},{outline_col},"
        f"&H80000000,{bold_flag},{italic_flag},{underline_flag},0,100,100,0,0,1,"
        f"{outline_w},{shadow_depth},2,10,10,30,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for block in blocks:
        start = _format_ass_timestamp(block["start"])
        end   = _format_ass_timestamp(block["end"])
        text  = block["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    log.debug("Generated %d ASS entries (font=%s, size=%d)", len(blocks), font_name, font_size)
    return header + "\n".join(events) + "\n"
