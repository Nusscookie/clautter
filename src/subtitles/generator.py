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


def words_to_srt(
    words: list[dict],
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
) -> str:
    """Convert word-timing entries to an SRT subtitle file string.

    Args:
        words:         List of {word, start_sec, end_sec, type} dicts.
        preset_name:   One of the _PRESETS keys (sets defaults).
        words_per_line: Override preset's words-per-line (1–12).
        lines_per_block: Override preset's lines-per-block (1–3).
        uppercase:     Override preset's uppercase flag.

    Returns:
        SRT file content as a string.
    """
    preset = _PRESETS.get(preset_name, _PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

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
            text = w["word"].upper() if effective_upper else w["word"]
            start = _format_timestamp(w["start_sec"])
            end = _format_timestamp(w["end_sec"])
            lines.extend([str(block_index), f"{start} --> {end}", text, ""])
            block_index += 1
    else:
        # Group words into blocks
        max_words = effective_wpl * effective_lpb
        for i in range(0, len(word_entries), max_words):
            block_words = word_entries[i : i + max_words]
            start_sec = block_words[0]["start_sec"]
            end_sec = block_words[-1]["end_sec"]

            text_words = [
                (w["word"].upper() if effective_upper else w["word"])
                for w in block_words
            ]

            # Split into lines
            chunks: list[str] = []
            for j in range(0, len(text_words), effective_wpl):
                chunks.append(" ".join(text_words[j : j + effective_wpl]))
            text = "\n".join(chunks)

            start = _format_timestamp(start_sec)
            end = _format_timestamp(end_sec)
            lines.extend([str(block_index), f"{start} --> {end}", text, ""])
            block_index += 1

    log.debug("Generated %d SRT subtitle entries (%s style)", block_index - 1, preset_name)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Timeline timestamp remapping
# ──────────────────────────────────────────────────────────────────────

def remap_words_to_timeline(
    words: list[dict],
    clips: list[Any],
    fps: float,
    tl_start_frame: int = 0,
) -> list[dict]:
    """Remap word timestamps from source-file time to cut-timeline time.

    ElevenLabs timestamps are relative to the source video file start.
    After smart cuts, each timeline clip covers a sub-range of the source.
    This function converts timestamps so subtitles align with the cut timeline.

    Words that fall entirely in a removed (silence) region are dropped.
    On an uncut timeline, clips cover the full source → identity mapping.
    """
    result: list[dict] = []
    for word in words:
        if word.get("type", "word") != "word":
            continue
        t_start = word["start_sec"]
        t_end = word["end_sec"]
        for clip in clips:
            src_start = clip.GetSourceStartFrame() / fps
            src_end = clip.GetSourceEndFrame() / fps
            if src_start <= t_start < src_end:
                clip_tl_sec = (clip.GetStart() - tl_start_frame) / fps
                new_start = clip_tl_sec + (t_start - src_start)
                new_end = clip_tl_sec + (min(t_end, src_end) - src_start)
                result.append({**word, "start_sec": new_start, "end_sec": new_end})
                break
        # word in a cut region → drop
    log.debug("remap_words_to_timeline: %d/%d words kept", len(result), len(words))
    return result


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

        # Get the timeline's real start frame. DaVinci timelines start at 01:00:00:00
        # (~frame 90000), not frame 0. recordFrame: 0 is before the timeline exists
        # and gets silently ignored. Use GetStartFrame() — same method AutoSubs uses.
        tl_start = 0
        try:
            if timeline:
                tl_start = timeline.GetStartFrame()
        except Exception as _e:
            log.debug("GetStartFrame failed, falling back to first clip: %s", _e)
            try:
                _v = timeline.GetItemListInTrack("video", 1)
                if _v:
                    tl_start = _v[0].GetStart()
            except Exception:
                pass
        log.info("Placing SRT at timeline frame %d", tl_start)

        # Place SRT clip on the timeline.
        # trackType/trackIndex are undocumented keys — Resolve detects SRT media
        # type automatically and places on the subtitle track. Omitting them avoids
        # potential conflicts with recordFrame handling.
        if srt_item:
            appended = media_pool.AppendToTimeline([{
                "mediaPoolItem": srt_item,
                "recordFrame": tl_start,
            }])
            if not appended:
                log.warning(
                    "AppendToTimeline returned empty — drag '%s' from Media Pool to subtitle track",
                    srt_path,
                )
            else:
                try:
                    _placed = timeline.GetItemListInTrack("subtitle", 1)
                    if _placed:
                        actual = _placed[0].GetStart()
                        log.info("Subtitle clip landed at frame %d (wanted %d)", actual, tl_start)
                        if actual != tl_start:
                            log.warning(
                                "recordFrame ignored by Resolve for subtitle clips — "
                                "drag subtitle clip to frame %d manually", tl_start
                            )
                except Exception as _e:
                    log.debug("Post-placement check failed: %s", _e)

        log.info("SRT imported to media pool: %s", srt_path)
        return True

    except Exception as e:
        log.error("import_srt_to_timeline failed: %s", e)
        log.info("Manual import: drag '%s' from Media Pool to the subtitle track.", srt_path)
        return False
