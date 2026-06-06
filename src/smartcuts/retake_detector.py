"""Retake detection via transcript similarity.

Identifies segments where the speaker re-recorded the same content.
The LAST attempt in each duplicate group is kept; earlier attempts are
tagged as retakes so the caller can route them to a separate timeline track.

When the retake phrase occupies only part of a segment (common at moderate/slow
pace where silence cutting makes fewer, longer clips), `retake_region` carries
the sub-range (start_ms, end_ms) so cutter.py can split the clip at those
boundaries and move only the retake portion to Track 2.

Types, constants, and text-normalization helpers live in retake_types.py.
"""

from __future__ import annotations
import difflib
from typing import Any, Optional

from src.utils.logger import get_logger
from src.smartcuts.retake_types import (
    SegmentRecord,
    _WordEntry,
    _WIN_WORDS,
    _SIMILARITY_THRESHOLD,
    _PROXIMITY_WINDOW_MS,
    _FULL_RETAKE_COVERAGE,
    _words_in_range,
    _normalize_word,
)

# Re-export SegmentRecord so callers that do
# ``from src.smartcuts.retake_detector import SegmentRecord`` still work.
__all__ = ["SegmentRecord", "find_retakes"]

log = get_logger(__name__)


def find_retakes(
    segments: list[SegmentRecord],
    language: str = "",
    progress_callback: Optional[Any] = None,
) -> int:
    """Tag retake segments in-place.  Returns number of retakes found.

    Algorithm:
    1. Transcribe each unique source file (lazy Whisper import).
    2. Build a flat word timeline (content words only, fillers excluded).
    3. Slide a window of _WIN_WORDS words across the timeline.
       When two windows match, extend the match greedily forward to find the
       full repeated phrase.  Map the phrase's ms range onto segments:
       - Segments fully inside the phrase → is_retake=True, retake_region=None
       - Segments partially overlapping   → is_retake=True, retake_region=(start,end)
       Partial-retake segments are split by cutter.py at the stored sub-range.

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

    segments.sort(key=lambda s: s.start_ms)

    for seg in segments:
        words = words_by_path.get(seg.file_path, [])
        seg.text = _words_in_range(words, seg.start_ms, seg.end_ms)

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

    retake_covered: list[bool] = [False] * len(flat)
    retake_count = 0
    n = len(flat)

    for i in range(n - _WIN_WORDS + 1):
        if all(retake_covered[i : i + _WIN_WORDS]):
            continue

        win_a   = flat[i : i + _WIN_WORDS]
        words_a = [e.word for e in win_a]
        t_end_a = win_a[-1].time_ms

        for j in range(i + _WIN_WORDS, n - _WIN_WORDS + 1):
            if flat[j].time_ms - t_end_a > _PROXIMITY_WINDOW_MS:
                break

            words_b = [flat[j + k].word for k in range(_WIN_WORDS)]
            ratio   = difflib.SequenceMatcher(None, words_a, words_b).ratio()

            if ratio < _SIMILARITY_THRESHOLD:
                continue

            ext     = 0
            max_ext = min(n - i - _WIN_WORDS, n - j - _WIN_WORDS)
            while ext < max_ext:
                na = [flat[i + ext + k + 1].word for k in range(_WIN_WORDS)]
                nb = [flat[j + ext + k + 1].word for k in range(_WIN_WORDS)]
                if difflib.SequenceMatcher(None, na, nb).ratio() >= _SIMILARITY_THRESHOLD:
                    ext += 1
                else:
                    break

            total_len       = _WIN_WORDS + ext
            retake_start_ms = flat[i].time_ms
            retake_end_ms   = flat[j].time_ms

            seen_segs: set[int] = set()
            for k in range(total_len):
                fi = i + k
                retake_covered[fi] = True
                si = flat[fi].seg_idx
                if si in seen_segs:
                    continue
                seen_segs.add(si)
                seg = segments[si]
                if seg.is_retake:
                    continue

                seg_dur  = max(seg.end_ms - seg.start_ms, 1.0)
                overlap  = min(seg.end_ms, retake_end_ms) - max(seg.start_ms, retake_start_ms)
                coverage = max(0.0, overlap) / seg_dur

                seg.is_retake = True
                seg.retake_region = None if coverage >= _FULL_RETAKE_COVERAGE else (
                    max(seg.start_ms, retake_start_ms),
                    min(seg.end_ms,   retake_end_ms),
                )
                retake_count += 1
                log.debug(
                    "Retake: seg %d [%.1fs–%.1fs] '%s...' → superseded at %.1fs "
                    "(sim=%.2f, coverage=%.0f%%, %s)",
                    si, seg.start_ms / 1000, seg.end_ms / 1000, seg.text[:40],
                    flat[j].time_ms / 1000, ratio, coverage * 100,
                    "full" if seg.retake_region is None else "partial",
                )

            break

    log.info("Retake detection complete: %d retake(s) in %d segment(s)", retake_count, len(segments))
    return retake_count
