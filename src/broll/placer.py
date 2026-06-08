"""Resolve timeline placement for autonomous B-roll mode.

Places a downloaded clip on the named 'B-Roll' video track at a given
start timecode. Uses the same API chain as the working subtitles placer:
resolve.GetProjectManager().GetCurrentProject().GetMediaPool().AppendToTimeline().
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
    names it 'B-Roll', and returns its index. Tolerates SetTrackName failures
    (common on free edition) — track is still usable even if not named.
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

        timeline.AddTrack("video")
        new_index = count + 1
        try:
            timeline.SetTrackName("video", new_index, "B-Roll")
            log.info("[placer] created and named B-Roll track at video index %d", new_index)
        except Exception as e:
            log.debug("[placer] SetTrackName failed (non-fatal, track %d still usable): %s", new_index, e)
        return new_index
    except Exception as e:
        log.warning("[placer] _find_or_create_broll_track failed (%s) — using track 2", e)
        return 2


def _fps_from_timeline(timeline: Any) -> float:
    """Extract FPS from timeline settings."""
    try:
        raw = timeline.GetSetting("timelineFrameRate") or "25"
        return float(str(raw).split()[0])
    except Exception:
        return 25.0


def _sec_to_frame(sec: float, fps: float) -> int:
    return max(0, int(round(sec * fps)))


def _apply_fill_frame(timeline_item: Any, mpi: Any, project: Any) -> None:
    """Zoom-crop clip to fill the timeline frame with no black bars (CSS cover math).

    Silently skips if resolution data is unavailable.
    """
    try:
        tl_w = int(project.GetSetting("timelineResolutionWidth") or 1920)
        tl_h = int(project.GetSetting("timelineResolutionHeight") or 1080)
        props = mpi.GetClipProperty() or {}
        res_str = props.get("Resolution", "")
        if not res_str or "x" not in res_str:
            log.debug("[placer] fill_frame: no Resolution property — skipping")
            return
        parts = res_str.lower().split("x")
        clip_w, clip_h = int(parts[0].strip()), int(parts[1].strip())
        if clip_w == 0 or clip_h == 0:
            return
        if abs((tl_w / tl_h) - (clip_w / clip_h)) < 0.01:
            return
        # scale so neither dimension falls short of the frame
        zoom = max(tl_w / clip_w, tl_h / clip_h)
        timeline_item.SetProperty("ZoomX", zoom)
        timeline_item.SetProperty("ZoomY", zoom)
        timeline_item.SetProperty("ZoomGang", True)
        log.debug("[placer] fill_frame: %dx%d → %dx%d zoom=%.4f", clip_w, clip_h, tl_w, tl_h, zoom)
    except Exception as e:
        log.warning("[placer] fill_frame failed (non-fatal): %s", e)


def place_clip(
    app: Any,
    clip_path: str,
    segment_start_sec: float,
    clip_duration_sec: float = 0.0,
    clip_start_sec: float = 0.0,
    track_index: int | None = None,
    fill_frame: bool = False,
) -> PlacerResult:
    """Place *clip_path* on the B-Roll track at *segment_start_sec*.

    Uses resolve.GetProjectManager().GetCurrentProject().GetMediaPool()
    — same chain as the working subtitles placer (fusion_placer.py).

    Args:
        app:                 The AIEditorApp; needs .resolve.
        clip_path:           Absolute path to a local video file.
        segment_start_sec:   Where on the timeline (seconds) to insert.
        clip_duration_sec:   Duration to use from clip; 0 = full clip.
        clip_start_sec:      In-point offset within the clip (seconds).
        track_index:         Explicit 1-based track index. None = auto-find/create.
        fill_frame:          Zoom-crop to eliminate black bars on aspect mismatch.

    Returns:
        PlacerResult with placed=True on success.
    """
    clip_path = str(clip_path)
    clip_name = Path(clip_path).name

    resolve = getattr(app, "resolve", None)
    if resolve is None:
        return PlacerResult(clip_path, segment_start_sec, False,
                            "app.resolve is None — not connected to Resolve")

    # Always get a fresh project + media pool via resolve (same as fusion_placer.py)
    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        if project is None:
            return PlacerResult(clip_path, segment_start_sec, False,
                                "GetCurrentProject() returned None")
        media_pool = project.GetMediaPool()
        if media_pool is None:
            return PlacerResult(clip_path, segment_start_sec, False,
                                "GetMediaPool() returned None")
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            return PlacerResult(clip_path, segment_start_sec, False,
                                "GetCurrentTimeline() returned None — open a timeline in Resolve")
    except Exception as e:
        return PlacerResult(clip_path, segment_start_sec, False,
                            f"Resolve API chain failed: {e}")

    # Import clip to media pool
    try:
        items = media_pool.ImportMedia([clip_path])
        if not items:
            return PlacerResult(clip_path, segment_start_sec, False,
                                f"ImportMedia returned empty for {clip_name}")
        mpi = items[0]
    except Exception as e:
        return PlacerResult(clip_path, segment_start_sec, False,
                            f"ImportMedia failed: {e}")

    fps = _fps_from_timeline(timeline)
    try:
        tl_start = timeline.GetStartFrame()
    except Exception:
        tl_start = 0

    record_frame = tl_start + _sec_to_frame(segment_start_sec, fps)
    resolved_track = track_index if track_index is not None else _find_or_create_broll_track(timeline)

    # Build clip info — same keys as fusion_placer.py (the working reference)
    clip_info: dict[str, Any] = {
        "mediaPoolItem": mpi,
        "mediaType":     1,
        "startFrame":    _sec_to_frame(clip_start_sec, fps) if clip_start_sec > 0.0 else 0,
        "endFrame":      max(1, _sec_to_frame(clip_start_sec + clip_duration_sec, fps))
                         if clip_duration_sec > 0.0 else None,
        "recordFrame":   record_frame,
        "trackIndex":    resolved_track,
    }
    # Remove endFrame key entirely if not set (None confuses the API)
    if clip_info["endFrame"] is None:
        del clip_info["endFrame"]

    log.debug(
        "[placer] AppendToTimeline: %s → track %d, recordFrame %d (%.1fs), "
        "startFrame %d, endFrame %s",
        clip_name, resolved_track, record_frame, segment_start_sec,
        clip_info["startFrame"], clip_info.get("endFrame", "full"),
    )

    try:
        placed = media_pool.AppendToTimeline([clip_info])
        log.debug("[placer] AppendToTimeline raw result: %r", placed)
        if placed:
            log.info("[placer] placed %s on track %d at %.1fs", clip_name, resolved_track, segment_start_sec)
            if fill_frame and isinstance(placed, (list, tuple)) and placed:
                _apply_fill_frame(placed[0], mpi, project)
            return PlacerResult(clip_path, segment_start_sec, True)
        log.warning(
            "[placer] AppendToTimeline returned empty for %s "
            "(track %d, recordFrame %d) — may be a free edition restriction",
            clip_name, resolved_track, record_frame,
        )
        return PlacerResult(clip_path, segment_start_sec, False,
                            "AppendToTimeline returned empty (free edition restriction?)")
    except Exception as e:
        log.error("[placer] AppendToTimeline raised: %s", e)
        return PlacerResult(clip_path, segment_start_sec, False, str(e))
