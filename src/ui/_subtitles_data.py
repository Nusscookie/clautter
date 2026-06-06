"""Constants for the Subtitles tab."""

from __future__ import annotations

_LANGUAGES = [
    ("Auto-detect", ""), ("English", "en"), ("German", "de"), ("French", "fr"),
    ("Spanish", "es"), ("Italian", "it"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Dutch", "nl"), ("Swedish", "sv"),
    ("Norwegian", "no"), ("Danish", "da"), ("Mandarin (Simplified)", "zh"),
]
LANG_LABELS: list[str] = [l for l, _ in _LANGUAGES]
LANG_CODES:  dict[str, str] = {l: c for l, c in _LANGUAGES}

STYLE_PRESETS: list[str] = ["YouTube", "Standard", "TikTok", "Alex Hormozi Style"]

FONT_FAMILIES: list[str] = [
    "Open Sans", "Arial", "Calibri", "Georgia", "Impact",
    "Montserrat", "Roboto", "Times New Roman", "Trebuchet MS", "Verdana",
]

WHISPER_MODELS: list[str] = ["Tiny (fast)", "Base", "Small", "Medium", "Large v2", "Large v3"]
WHISPER_MODEL_MAP: dict[str, str] = {
    "Tiny (fast)": "tiny",
    "Base": "base",
    "Small": "small",
    "Medium": "medium",
    "Large v2": "large-v2",
    "Large v3": "large-v3",
}

# (words_per_line, lines_per_block, uppercase, highlight_color)
PRESET_DEFAULTS: dict[str, tuple[int, int, bool, str]] = {
    "Standard":           (8, 2, False, "#FFFF00"),
    "YouTube":            (7, 2, False, "#FFFF00"),
    "TikTok":             (5, 1, True,  "#FF0000"),
    "Alex Hormozi Style": (3, 1, True,  "#FFFF00"),
}
