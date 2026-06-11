"""Zoom point detection driven by edit structure (cut points).

A zoom should land at a cut — the start of a new take produced by Smart Cuts —
not on arbitrary audio peaks or every frame a face appears in. This module turns
the current timeline's clip boundaries into ZoomPoint objects: one zoom per take
longer than a threshold, spaced to honour a max-per-minute budget.

Face detection no longer triggers zooms; it only re-centers them on the speaker
(see face_analyzer.face_offset_at). B-roll placements are merged in by the worker.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_ZOOM_DURATION_MS = 2500  # Default zoom region length (ms)


@dataclass
class ZoomPoint:
    """A detected moment where a zoom cut is recommended."""

    timeline_frame: int      # Frame number on the main timeline
    duration_frames: int     # How long the zoom region lasts
    zoom_amount: float       # e.g. 1.15 = 115%
    energy_dbfs: float = 0.0 # Unused legacy field (kept for repr stability)
    pan: float = 0.0         # Normalized horizontal subject offset [-0.5,0.5]; applier scales to Pan px
    tilt: float = 0.0        # Normalized vertical subject offset [-0.5,0.5]; applier scales to Tilt px

    def __repr__(self) -> str:
        return (
            f"<ZoomPoint frame={self.timeline_frame} "
            f"dur={self.duration_frames}fr zoom={self.zoom_amount:.2f} "
            f"pan={self.pan:.2f} tilt={self.tilt:.2f}>"
        )


def enforce_spacing(
    points: list[ZoomPoint], fps: float, max_per_minute: int
) -> list[ZoomPoint]:
    """Drop points that fall closer than the max-per-minute budget allows.

    Walks points in timeline order and keeps one only if it is at least
    ``60s / max_per_minute`` after the last accepted point. Shared by the cut
    detector and the worker's B-roll merge so both honour the same cadence.
    """
    if max_per_minute <= 0:
        return list(points)

    min_spacing_frames = (60.0 / max_per_minute) * fps
    kept: list[ZoomPoint] = []
    last_frame = float("-inf")
    for zp in sorted(points, key=lambda p: p.timeline_frame):
        if zp.timeline_frame - last_frame < min_spacing_frames:
            continue
        kept.append(zp)
        last_frame = zp.timeline_frame
    return kept


def detect_zoom_points_from_cuts(
    clips: list[Any],
    fps: float = 25.0,
    min_take_sec: float = 2.0,
    max_per_minute: int = 4,
    zoom_amount: float = 1.15,
    zoom_duration_ms: float = _ZOOM_DURATION_MS,
) -> list[ZoomPoint]:
    """Emit one zoom at the start of each take longer than ``min_take_sec``.

    The current timeline's clip boundaries are the cut points (Smart Cuts builds
    a timeline of one clip per take). Each qualifying clip yields a single
    ZoomPoint anchored at its start frame, emphasising the new take. Short clips
    (rapid-fire cuts) are skipped; the survivors are then thinned to honour
    ``max_per_minute``.

    Args:
        clips:            TimelineItems from video track 1 (cut order = timeline order).
        fps:              Timeline frame rate.
        min_take_sec:     Skip clips shorter than this (only zoom on longer takes).
        max_per_minute:   Maximum zoom points per minute across the timeline.
        zoom_amount:      Zoom scale factor (1.15 = 115%).
        zoom_duration_ms: Target duration of each zoom region in ms; clamped to the
                          clip length so a zoom never overruns its take.

    Returns:
        List of ZoomPoint objects sorted by timeline_frame (pan/tilt left at 0).
    """
    min_take_frames = min_take_sec * fps
    zoom_dur_frames = max(1, int((zoom_duration_ms / 1000.0) * fps))

    points: list[ZoomPoint] = []
    for clip in clips:
        try:
            start = int(clip.GetStart())
            end = int(clip.GetEnd())
        except Exception as e:
            log.debug("Skipping clip with unreadable bounds: %s", e)
            continue

        length_frames = end - start
        if length_frames < min_take_frames:
            continue

        points.append(ZoomPoint(
            timeline_frame=start,
            duration_frames=min(zoom_dur_frames, length_frames),
            zoom_amount=zoom_amount,
        ))

    points = enforce_spacing(points, fps, max_per_minute)
    log.info(
        "Cut-driven zoom detection: %d point(s) from %d clip(s) "
        "(min_take=%.1fs, max=%d/min)",
        len(points), len(clips), min_take_sec, max_per_minute,
    )
    return points
