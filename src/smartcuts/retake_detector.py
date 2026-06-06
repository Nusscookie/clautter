"""Retake detection via transcript similarity.

Identifies segments where the speaker re-recorded the same content.
The LAST attempt in each duplicate group is kept; earlier attempts are
tagged as retakes so the caller can route them to a separate timeline track.
"""

from __future__ import annotations
import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

_SIMILARITY_THRESHOLD = 0.70   # SequenceMatcher ratio (word-level) to call two segments retakes
_PROXIMITY_WINDOW_MS  = 120_000  # only compare segments within 2 minutes of each other
_MIN_WORDS            = 4        # skip segments shorter than this (after filler stripping)

_FILLERS = frozenset({
    "um", "uh", "like", "so", "okay", "ok", "well", "right",
    "actually", "basically", "you", "know", "now", "alright", "hmm",
})


@dataclass
class SegmentRecord:
    """One non-silent segment, enriched with source metadata and transcript text."""

    clip_idx:    int
    media_item:  Any
    file_path:   str
    start_ms:    float   # absolute position in source file
    end_ms:      float
    start_frame: int
    end_frame:   int
    text:        str  = field(default="", compare=False)
    is_retake:   bool = field(default=False, compare=False)


def _words_in_range(words: list[dict], start_ms: float, end_ms: float) -> str:
    """Return space-joined text of words whose timestamps fall inside [start_ms, end_ms]."""
    return " ".join(
        w["word"]
        for w in words
        if w["start_sec"] * 1000.0 >= start_ms and w["end_sec"] * 1000.0 <= end_ms
    )


def _normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove fillers. Returns word list for comparison."""
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return [w for w in words if w not in _FILLERS]


def find_retakes(
    segments: list[SegmentRecord],
    language: str = "",
    progress_callback: Optional[Any] = None,
) -> int:
    """Tag retake segments in-place.  Returns number of retakes found.

    Algorithm:
    1. Transcribe each unique source file (lazy Whisper import).
    2. Map word timestamps → segment text.
    3. Compare adjacent segments within PROXIMITY_WINDOW_MS; if text similarity
       exceeds SIMILARITY_THRESHOLD, mark the EARLIER one as a retake.

    Args:
        segments:          All SegmentRecord objects in source-timeline order.
        language:          BCP-47 code for Whisper (empty = auto-detect).
        progress_callback: Optional callable(message: str) for status updates.

    Returns:
        Number of segments tagged is_retake=True.
    """
    if not segments:
        return 0

    from src.subtitles.whisper_client import WhisperClient

    # Transcribe each unique file once
    unique_paths = list(dict.fromkeys(s.file_path for s in segments if s.file_path))
    words_by_path: dict[str, list[dict]] = {}
    client = WhisperClient(model_name="base")

    for i, path in enumerate(unique_paths):
        if progress_callback:
            progress_callback(f"Transcribing file {i + 1}/{len(unique_paths)} for retake detection...")
        try:
            words_by_path[path] = client.transcribe(path, language=language)
            log.info("Retake detector: transcribed %s (%d words)", path, len(words_by_path[path]))
        except Exception as e:
            log.error("Retake detector: transcription failed for %s: %s", path, e)
            words_by_path[path] = []

    # Fill text for each segment
    for seg in segments:
        words = words_by_path.get(seg.file_path, [])
        seg.text = _words_in_range(words, seg.start_ms, seg.end_ms)

    # Sort by source position (should already be, but ensure stability)
    segments.sort(key=lambda s: s.start_ms)

    retake_count = 0

    for i, seg_a in enumerate(segments):
        if seg_a.is_retake:
            continue  # already marked — skip as anchor
        nw_a = _normalize(seg_a.text)
        if len(nw_a) < _MIN_WORDS:
            continue

        for seg_b in segments[i + 1:]:
            if seg_b.start_ms - seg_a.end_ms > _PROXIMITY_WINDOW_MS:
                break  # segments sorted; no point checking further
            nw_b = _normalize(seg_b.text)
            if len(nw_b) < _MIN_WORDS:
                continue

            # Word-level comparison on filler-stripped lists
            ratio = difflib.SequenceMatcher(None, nw_a, nw_b).ratio()

            if ratio >= _SIMILARITY_THRESHOLD:
                seg_a.is_retake = True
                retake_count += 1
                log.debug(
                    "Retake: [%.1fs–%.1fs] '%s...' → replaced by [%.1fs–%.1fs] (sim=%.2f)",
                    seg_a.start_ms / 1000, seg_a.end_ms / 1000,
                    seg_a.text[:40],
                    seg_b.start_ms / 1000, seg_b.end_ms / 1000,
                    ratio,
                )
                break  # seg_a is a retake — no need to keep comparing it

    log.info("Retake detection complete: %d retake(s) in %d segment(s)", retake_count, len(segments))
    return retake_count
