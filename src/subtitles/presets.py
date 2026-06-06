"""Subtitle style presets and Fusion Title type registry."""

from __future__ import annotations


class _Preset:
    words_per_line: int
    lines_per_block: int
    uppercase: bool
    word_by_word: bool
    highlight_color: str | None

    def __init__(
        self,
        words_per_line: int = 8,
        lines_per_block: int = 2,
        uppercase: bool = False,
        word_by_word: bool = False,
        highlight_color: str | None = None,
    ) -> None:
        self.words_per_line = words_per_line
        self.lines_per_block = lines_per_block
        self.uppercase = uppercase
        self.word_by_word = word_by_word
        self.highlight_color = highlight_color


PRESETS: dict[str, _Preset] = {
    "Standard":           _Preset(words_per_line=8, lines_per_block=2),
    "YouTube":            _Preset(words_per_line=7, lines_per_block=2),
    "TikTok":             _Preset(words_per_line=5, lines_per_block=1, uppercase=True,
                                  word_by_word=True,  highlight_color="#FF0000"),
    "Alex Hormozi Style": _Preset(words_per_line=3, lines_per_block=1, uppercase=True,
                                  word_by_word=True,  highlight_color="#FFFF00"),
}

# Localized "Fusion Title" type strings from DaVinci Resolve's Media Pool.
# Matches AutoSubs' titleStrings list so we recognise templates in any locale.
FUSION_TITLE_TYPES: frozenset[str] = frozenset({
    "Fusion Title", "Generator",
    "Fusion Titles",
    "Título – Fusion", "Título Fusion",
    "Titre Fusion",
    "Титры на стр. Fusion",
    "Fusion Titel",
    "Titolo Fusion",
    "Fusionタイトル",
    "Fusion标题",
    "퓨전 타이틀",
    "Tiêu đề Fusion",
})
