"""Subtitle generation: word timings → SRT file + DaVinci subtitle track import."""

from __future__ import annotations
import os
import tempfile
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Style Presets
# ──────────────────────────────────────────────────────────────────────

class _Preset:
    """Configuration for a subtitle style."""
    words_per_line: int
    lines_per_block: int
    uppercase: bool
    word_by_word: bool  # one entry per word (Hormozi style)

    def __init__(
        self,
        words_per_line: int = 8,
        lines_per_block: int = 2,
        uppercase: bool = False,
        word_by_word: bool = False,
    ) -> None:
        self.words_per_line = words_per_line
        self.lines_per_block = lines_per_block
        self.uppercase = uppercase
        self.word_by_word = word_by_word


_PRESETS: dict[str, _Preset] = {
    "Standard":           _Preset(words_per_line=8,  lines_per_block=2),
    "YouTube":            _Preset(words_per_line=7,  lines_per_block=2),
    "TikTok":             _Preset(words_per_line=5,  lines_per_block=1, uppercase=True),
    "Alex Hormozi Style": _Preset(words_per_line=3,  lines_per_block=1, uppercase=True,
                                  word_by_word=True),
}


# ──────────────────────────────────────────────────────────────────────
# SRT formatting helpers
# ──────────────────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    ms = int(round(seconds * 1000))
    h = ms // 3_600_000;  ms %= 3_600_000
    m = ms // 60_000;     ms %= 60_000
    s = ms // 1_000;      ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_to_srt(words: list[dict], preset_name: str = "YouTube") -> str:
    """Convert word-timing entries to an SRT subtitle file string.

    Args:
        words:       List of {word, start_sec, end_sec, type} dicts.
        preset_name: One of the _PRESETS keys.

    Returns:
        SRT file content as a string.
    """
    preset = _PRESETS.get(preset_name, _PRESETS["YouTube"])

    # Keep only actual words (skip spacing / audio_event entries)
    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]

    if not word_entries:
        log.warning("words_to_srt: no word entries to format")
        return ""

    lines: list[str] = []
    block_index = 1

    if preset.word_by_word:
        # One subtitle entry per word (Hormozi style)
        for w in word_entries:
            text = w["word"].upper() if preset.uppercase else w["word"]
            start = _format_timestamp(w["start_sec"])
            end = _format_timestamp(w["end_sec"])
            lines.extend([str(block_index), f"{start} --> {end}", text, ""])
            block_index += 1
    else:
        # Group words into blocks
        max_words = preset.words_per_line * preset.lines_per_block
        for i in range(0, len(word_entries), max_words):
            block_words = word_entries[i : i + max_words]
            start_sec = block_words[0]["start_sec"]
            end_sec = block_words[-1]["end_sec"]

            text_words = [
                (w["word"].upper() if preset.uppercase else w["word"])
                for w in block_words
            ]

            # Split into lines
            chunks: list[str] = []
            for j in range(0, len(text_words), preset.words_per_line):
                chunks.append(" ".join(text_words[j : j + preset.words_per_line]))
            text = "\n".join(chunks)

            start = _format_timestamp(start_sec)
            end = _format_timestamp(end_sec)
            lines.extend([str(block_index), f"{start} --> {end}", text, ""])
            block_index += 1

    log.debug("Generated %d SRT subtitle entries (%s style)", block_index - 1, preset_name)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# DaVinci Resolve import
# ──────────────────────────────────────────────────────────────────────

def import_srt_to_timeline(resolve: Any, srt_path: str, timeline: Any) -> bool:
    """Import an SRT file and attach it to the timeline as a subtitle track.

    DaVinci Resolve does not have a direct scripting API for SRT import as of v20.
    Best available approach:
      1. Import SRT as a Media Pool item.
      2. Add a subtitle track if none exists.
      3. Append the SRT item to the subtitle track.

    Falls back gracefully and logs the SRT path so the user can import manually.

    Returns True if the operation was attempted without errors.
    """
    if not os.path.exists(srt_path):
        log.error("SRT file not found: %s", srt_path)
        return False

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = project.GetMediaPool()

        # Import SRT into media pool
        imported = media_pool.ImportMedia([srt_path])
        srt_item = imported[0] if imported else None
        if not srt_item:
            log.warning("ImportMedia returned empty list for SRT: %s", srt_path)

        # Ensure a subtitle track exists and clear any old subtitle clips
        if timeline:
            if timeline.GetTrackCount("subtitle") == 0:
                timeline.AddTrack("subtitle")
                log.info("Added subtitle track to timeline")
            else:
                for _i in range(1, timeline.GetTrackCount("subtitle") + 1):
                    _items = timeline.GetItemListInTrack("subtitle", _i)
                    if _items:
                        try:
                            timeline.DeleteClips(_items)
                            log.debug("Cleared %d subtitle clip(s) from track %d", len(_items), _i)
                        except Exception as _e:
                            log.warning("Could not clear subtitle track %d: %s", _i, _e)

        # Resolve timelines start at 01:00:00:00, not frame 0 — use first video clip's
        # actual start frame so recordFrame lands at the timeline's real beginning.
        tl_start_frame = 0
        try:
            if timeline:
                _v = timeline.GetItemListInTrack("video", 1)
                if _v:
                    tl_start_frame = _v[0].GetStart()
        except Exception as _e:
            log.debug("Could not determine timeline start frame: %s", _e)

        # Place SRT clip on the timeline
        if srt_item:
            appended = media_pool.AppendToTimeline([{
                "mediaPoolItem": srt_item,
                "trackType": "subtitle",
                "trackIndex": 1,
                "recordFrame": tl_start_frame,
            }])
            if not appended:
                log.warning(
                    "AppendToTimeline returned empty — drag '%s' from Media Pool to subtitle track",
                    srt_path,
                )

        log.info("SRT imported to media pool: %s", srt_path)
        return True

    except Exception as e:
        log.error("import_srt_to_timeline failed: %s", e)
        log.info("Manual import: drag '%s' from Media Pool to the subtitle track.", srt_path)
        return False
