"""Re-export shim — public API for subtitle generation.

Import from the focused sub-modules directly for new code.
This file exists so existing callers keep working unchanged.
"""

from src.subtitles.formatter import words_to_srt, words_to_ass
from src.subtitles.fusion_placer import place_fusion_titles
from src.subtitles.remapper import remap_words_to_timeline
from src.subtitles.srt_importer import import_srt_to_timeline

__all__ = [
    "words_to_srt",
    "words_to_ass",
    "remap_words_to_timeline",
    "place_fusion_titles",
    "import_srt_to_timeline",
]
