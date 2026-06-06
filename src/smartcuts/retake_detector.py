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

_WIN_WORDS            = 4        # sliding window size (content words); 4 is robust to compound-word transcription variance in Whisper base
_SIMILARITY_THRESHOLD = 0.70     # SequenceMatcher ratio to call two windows retakes
_PROXIMITY_WINDOW_MS  = 120_000  # only compare windows within 2 minutes of each other

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


@dataclass
class _WordEntry:
    """One content word (filler-stripped) with its timestamp and owning segment index."""
    word:    str    # normalized: lowercase, no punctuation, not a filler
    time_ms: float
    seg_idx: int


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


def _normalize_word(raw: str) -> str | None:
    """Normalize a single word. Returns None if it's a filler or empty after stripping."""
    cleaned = re.sub(r"[^\w]", "", raw.lower())
    if not cleaned or cleaned in _FILLERS:
        return None
    return cleaned


def find_retakes(
    segments: list[SegmentRecord],
    language: str = "",
    progress_callback: Optional[Any] = None,
) -> int:
    """Tag retake segments in-place.  Returns number of retakes found.

    Algorithm:
    1. Transcribe each unique source file (lazy Whisper import).
    2. Map word timestamps → segment text (for logging) and flat word timeline.
    3. Slide a window of _WIN_WORDS content words across the timeline.
       For each window, compare to all later windows within PROXIMITY_WINDOW_MS.
       When similarity >= SIMILARITY_THRESHOLD, mark the earlier window's segments
       as retakes. Clip boundaries are irrelevant — the window spans them naturally,
       so both multi-clip retakes (Problem 2) and retakes embedded mid-clip (Problem 1)
       are detected.

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

    # Sort segments by source position
    segments.sort(key=lambda s: s.start_ms)

    # Fill .text on each segment (used for logging only)
    for seg in segments:
        words = words_by_path.get(seg.file_path, [])
        seg.text = _words_in_range(words, seg.start_ms, seg.end_ms)

    # Build flat word timeline — content words only (fillers excluded)
    flat: list[_WordEntry] = []
    for seg_idx, seg in enumerate(segments):
        raw_words = words_by_path.get(seg.file_path, [])
        for w in raw_words:
            t_start = w["start_sec"] * 1000.0
            t_end   = w["end_sec"]   * 1000.0
            if t_start < seg.start_ms or t_end > seg.end_ms:
                continue
            norm = _normalize_word(w["word"])
            if norm is None:
                continue
            flat.append(_WordEntry(word=norm, time_ms=t_start, seg_idx=seg_idx))

    log.info("Retake detector: %d content words across %d segments", len(flat), len(segments))

    if len(flat) < _WIN_WORDS * 2:
        log.info("Retake detection: not enough words for window comparison")
        return 0

    # Sliding-window comparison
    # retake_covered[i] = True when flat[i] is already part of a marked retake window
    retake_covered: list[bool] = [False] * len(flat)
    retake_count = 0

    for i in range(len(flat) - _WIN_WORDS + 1):
        # Skip if this window is already fully inside a marked retake
        if all(retake_covered[i : i + _WIN_WORDS]):
            continue

        win_a = flat[i : i + _WIN_WORDS]
        words_a = [e.word for e in win_a]
        t_end_a = win_a[-1].time_ms

        for j in range(i + _WIN_WORDS, len(flat) - _WIN_WORDS + 1):
            # Proximity guard: stop when window_b starts too far away
            if flat[j].time_ms - t_end_a > _PROXIMITY_WINDOW_MS:
                break

            win_b = flat[j : j + _WIN_WORDS]
            words_b = [e.word for e in win_b]

            ratio = difflib.SequenceMatcher(None, words_a, words_b).ratio()
            if ratio >= _SIMILARITY_THRESHOLD:
                # Mark all segments touched by window_a as retakes
                for k, entry in enumerate(win_a):
                    seg = segments[entry.seg_idx]
                    if not seg.is_retake:
                        seg.is_retake = True
                        retake_count += 1
                        log.debug(
                            "Retake: seg %d [%.1fs–%.1fs] '%s...' → superseded at %.1fs (sim=%.2f)",
                            entry.seg_idx,
                            seg.start_ms / 1000, seg.end_ms / 1000,
                            seg.text[:40],
                            flat[j].time_ms / 1000,
                            ratio,
                        )
                    retake_covered[i + k] = True
                break  # window_a matched — move to next i

    log.info("Retake detection complete: %d retake(s) in %d segment(s)", retake_count, len(segments))
    return retake_count
