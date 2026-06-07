"""Smoke tests for retake detection — the big-segment duplicate bug.

Regression: when silence cutting produced few, long segments, a clip containing
two retakes (or a retake plus kept speech) only had its FIRST retake recorded, so
duplicates survived. Detection runs on a flat word timeline, so removal must be
span-accurate and independent of how coarsely the clip was split.

Run directly (no Resolve, no Whisper needed):
    py -3.12 tests/test_retake_detector.py
"""

from __future__ import annotations
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.smartcuts.retake_types import SegmentRecord  # noqa: E402

_FPS = 30.0
_PATH = "fake.mov"


def _words(text: str, base_sec: float, *, step: float = 0.3, dur: float = 0.2) -> list[dict]:
    """Build faster-whisper-style word dicts for `text`, one word every `step` s."""
    out: list[dict] = []
    for k, w in enumerate(text.split()):
        start = base_sec + k * step
        out.append({"word": w, "start_sec": start, "end_sec": start + dur, "type": "word"})
    return out


def _seg(start_ms: float, end_ms: float) -> SegmentRecord:
    return SegmentRecord(
        clip_idx=0, media_item=None, file_path=_PATH,
        start_ms=start_ms, end_ms=end_ms,
        start_frame=round(start_ms * _FPS / 1000), end_frame=round(end_ms * _FPS / 1000),
    )


def _run(segments: list[SegmentRecord], words: list[dict]) -> int:
    """Call find_retakes with Whisper stubbed to return `words` for any path."""
    fake = mock.Mock()
    fake.transcribe.return_value = words
    with mock.patch("src.subtitles.whisper_client.WhisperClient", return_value=fake):
        from src.smartcuts.retake_detector import find_retakes
        return find_retakes(segments, language="de")


# The false-start retake from the bug report.
_PREFIX = "Das finde ich schon mal großartig Leider haben Sie nicht so eine"
_TAKE1  = _PREFIX + " gute Org"
_TAKE2  = _PREFIX + " coole Organisation wie wir"


def test_false_start_in_one_big_segment_is_removed() -> None:
    """Both takes inside ONE long segment: the first take must be flagged for removal."""
    words = _words(_TAKE1, base_sec=0.5) + _words(_TAKE2, base_sec=5.0)
    seg = _seg(0, 11_000)
    _run([seg], words)

    assert seg.is_retake, "first take not detected as retake"
    assert seg.retake_regions, "no retake_regions recorded"
    start, end = seg.retake_regions[0]
    # Region spans take 1 start (~0.5s) up to where take 2 begins (~5.0s).
    assert 400 <= start <= 700, f"region start off: {start}"
    assert 4800 <= end <= 5200, f"region end off: {end}"
    # Take 2 (begins at 5.0s) must be preserved — region must not cover it.
    assert end <= 5200, "retake region bleeds into the kept take"
    print("ok: false start in one big segment removed", seg.retake_regions)


def test_two_retakes_in_one_segment_both_recorded() -> None:
    """A long segment holding TWO separate retakes must record BOTH (the core bug)."""
    intro = "möchte jetzt auch ein Pfandsystem einführen"
    words = (
        _words(intro, base_sec=0.5)
        + _words(intro, base_sec=3.0)          # intro retake
        + _words(_TAKE1, base_sec=6.0)
        + _words(_TAKE2, base_sec=11.0)        # phrase retake
    )
    seg = _seg(0, 18_000)
    _run([seg], words)

    assert seg.is_retake
    assert len(seg.retake_regions) >= 2, (
        f"expected >=2 retakes in one segment, got {seg.retake_regions}"
    )
    print("ok: two retakes in one segment both recorded", seg.retake_regions)


def test_granularity_invariance() -> None:
    """Same audio, fine segmentation: the first take is still flagged for removal."""
    words = _words(_TAKE1, base_sec=0.5) + _words(_TAKE2, base_sec=5.0)
    # Split the same 11s into three segments; take 1 lives in seg 0.
    segs = [_seg(0, 4_700), _seg(4_700, 9_800), _seg(9_800, 11_000)]
    _run(segs, words)

    removed = [r for s in segs for r in s.retake_regions]
    assert removed, "no retakes detected under fine segmentation"
    assert any(s.is_retake for s in segs)
    # Take 1's words (0.5–4.6s) fall in seg 0, which must carry a retake span.
    assert segs[0].is_retake and segs[0].retake_regions, "take 1 not removed when split"
    print("ok: granularity invariance", [s.retake_regions for s in segs])


if __name__ == "__main__":
    test_false_start_in_one_big_segment_is_removed()
    test_two_retakes_in_one_segment_both_recorded()
    test_granularity_invariance()
    print("\nALL PASS")
