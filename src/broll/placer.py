"""Resolve timeline V2 placement for autonomous B-roll mode.

Places a downloaded clip on video track 2 at a given start timecode.
Falls back gracefully when Resolve is unavailable or V2 insertion is
restricted (Resolve free edition).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


class PlacerResult:
    """Outcome of a single place_clip() call."""

    def __init__(
        self,
        clip_path: str,
        segment_start_sec: float,
        placed: bool,
        reason: str = "",
    ) -> None:
        self.clip_path = clip_path
        self.segment_start_sec = segment_start_sec
        self.placed = placed
        self.reason = reason

    def __repr__(self) -> str:
        status = "placed" if self.placed else f"skipped ({self.reason})"
        return f"<PlacerResult {Path(self.clip_path).name} @ {self.segment_start_sec:.1f}s — {status}>"


def _find_or_create_broll_track(timeline: Any) -> int:
    """Return the 1-based video track index for the 'B-Roll' named track.

    Searches existing tracks by name. If not found, creates a new video track,
    names it 'B-Roll', and returns its index. New tracks land above all existing
    ones (highest index), so B-Roll ends up above Retakes but below any
    Subtitle track created afterward.
    """
    try:
        count = timeline.GetTrackCount("video")
        for i in range(1, count + 1):
            try:
                name = timeline.GetTrackName("video", i) or ""
                if name.strip().lower() == "b-roll":
                    log.debug("[placer] found existing B-Roll track at index %d", i)
                    return i
            except Exception:
                continue

        # Not found — create a new track
        timeline.AddTrack("video")
        new_index = count + 1
        try:
            timeline.SetTrackName("video", new_index, "B-Roll")
        except Exception as e:
            log.debug("[placer] SetTrackName failed (non-fatal): %s", e)
        log.info("[placer] created B-Roll track at video index %d", new_index)
        return new_index
    except Exception as e:
        log.warning("[placer] _find_or_create_broll_track failed (%s) — using track 2", e)
        return 2


def _fps_from_timeline(timeline: Any) -> float:
    """Extract FPS from the timeline setting string, e.g. '25' or '23.976'."""
    try:
        raw = timeline.GetSetting("timelineFrameRate") or "25"
        return float(str(raw).split()[0])
    except Exception:
        return 25.0


def _sec_to_frame(sec: float, fps: float) -> int:
    return max(0, int(round(sec * fps)))


def _import_to_pool(app: Any, clip_path: str) -> Any | None:
    """Import a local file to the Resolve media pool; return MediaPoolItem or None."""
    try:
        project = getattr(app, "project", None)
        if project is None:
            log.warning("[placer] no project — cannot import to media pool")
            return None
        mp = project.GetMediaPool()
        if mp is None:
            log.warning("[placer] GetMediaPool() returned None")
            return None
        items = mp.ImportMedia([str(clip_path)])
        if not items:
            log.warning("[placer] ImportMedia returned empty list for %s", clip_path)
            return None
        return items[0]
    except Exception as e:
        log.error("[placer] ImportMedia failed: %s", e)
        return None


def place_clip(
    app: Any,
    clip_path: str,
    segment_start_sec: float,
    clip_duration_sec: float = 0.0,
    track_index: int | None = None,
) -> PlacerResult:
    """Place *clip_path* on the B-Roll track at *segment_start_sec*.

    Strategy:
      1. Import clip into media pool.
      2. Get active timeline; compute frame offset.
      3. Find or create a named 'B-Roll' video track (or use explicit track_index).
      4. Use AppendToTimeline with trackIndex.
      5. If step 4 raises (restricted in free edition), log a warning and return
         placed=False so the caller can show a toast.

    Args:
        app:                 The AIEditorApp (or proxy); needs .project and .timeline.
        clip_path:           Absolute path to a local video file.
        segment_start_sec:   Where on the timeline (in seconds) to insert the clip.
        clip_duration_sec:   Duration to use; 0 = full clip.
        track_index:         Explicit Resolve track index (1-based). None = auto-find
                             or create a named 'B-Roll' track.

    Returns:
        PlacerResult with placed=True on success, placed=False with reason on failure.
    """
    clip_path = str(clip_path)

    # 1. Import to media pool
    mpi = _import_to_pool(app, clip_path)
    if mpi is None:
        return PlacerResult(clip_path, segment_start_sec, False,
                            "MediaPool import failed — clip saved to disk only")

    # 2. Get timeline + FPS
    timeline = getattr(app, "timeline", None)
    if timeline is None:
        return PlacerResult(clip_path, segment_start_sec, False,
                            "No active timeline — clip imported to media pool")

    fps = _fps_from_timeline(timeline)
    start_frame = _sec_to_frame(segment_start_sec, fps)

    # Resolve target track: find/create named 'B-Roll' track if not explicit
    resolved_track = track_index if track_index is not None else _find_or_create_broll_track(timeline)

    # 3. Build clip info dict for AppendToTimeline
    clip_info: dict[str, Any] = {
        "mediaPoolItem": mpi,
        "trackIndex": resolved_track,
        "recordFrame": start_frame,
    }
    if clip_duration_sec > 0.0:
        clip_info["startFrame"] = 0
        clip_info["endFrame"] = _sec_to_frame(clip_duration_sec, fps)

    try:
        project = app.project
        mp = project.GetMediaPool()
        result = mp.AppendToTimeline([clip_info])
        if not result:
            # AppendToTimeline returns [] on failure (e.g., restricted in free)
            log.warning("[placer] AppendToTimeline returned empty — V2 placement may be restricted")
            return PlacerResult(clip_path, segment_start_sec, False,
                                "AppendToTimeline returned empty (free edition restriction?)")
        log.info("[placer] placed %s on track %d at %.1fs (frame %d)",
                 Path(clip_path).name, resolved_track, segment_start_sec, start_frame)
        return PlacerResult(clip_path, segment_start_sec, True)
    except Exception as e:
        log.error("[placer] AppendToTimeline raised: %s", e)
        return PlacerResult(clip_path, segment_start_sec, False, str(e))
