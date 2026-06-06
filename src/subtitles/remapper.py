"""Remap word timestamps from source-file time to cut-timeline time."""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


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
    log.debug("remap_words_to_timeline: %d/%d words kept", len(result), len(words))
    return result
