"""Resolve timeline placement for autonomous B-roll mode.

Places a downloaded clip on the named 'B-Roll' video track at a given
start timecode. Uses the same API chain as the working subtitles placer:
resolve.GetProjectManager().GetCurrentProject().GetMediaPool().AppendToTimeline().
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from src.broll.placer_zoom import _apply_fill_frame, _video_track1_end_sec
from src.constants import TRACKS
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
                if name.strip().lower() == TRACKS.BROLL.lower():
                    log.debug("[placer] found existing B-Roll track at index %d", i)
                    return i
            except Exception:
                continue

        timeline.AddTrack("video")
        new_index = count + 1
        try:
            timeline.SetTrackName("video", new_index, TRACKS.BROLL)
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


def _source_fps(mpi: Any, fallback: float) -> float:
    """Native frame rate of a media-pool item, or *fallback* if unavailable.

    Source in/out frames passed to AppendToTimeline are counted in the clip's
    own fps. Reading "FPS" off the clip property keeps the placed duration correct
    when the B-roll fps differs from the timeline fps.
    """
    try:
        props = mpi.GetClipProperty() or {}
        raw = props.get("FPS") or props.get("Frame Rate") or ""
        val = float(str(raw).split()[0])
        if val > 0:
            return val
    except Exception as e:
        log.debug("[placer] _source_fps failed (non-fatal): %s", e)
    return fallback


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
    # startFrame/endFrame in clip_info are SOURCE frames — they must use the clip's
    # native fps, not the timeline fps. If they differ (e.g. 30fps B-roll on a 25fps
    # timeline) and we convert seconds→frames with the timeline fps, AppendToTimeline
    # lays down the wrong number of source frames and the clip overhangs the cap.
    src_fps = _source_fps(mpi, fps)
    try:
        tl_start = timeline.GetStartFrame()
    except Exception:
        tl_start = 0

    # Cap duration so clip doesn't extend past the end of the main video clip (V1).
    # Subtract one frame worth of time to absorb float→frame rounding overshoots.
    video_end = _video_track1_end_sec(timeline, fps)
    if video_end is not None:
        one_frame = 1.0 / fps
        max_allowed = video_end - segment_start_sec - one_frame
        if max_allowed <= 0:
            return PlacerResult(clip_path, segment_start_sec, False,
                                f"segment_start ({segment_start_sec:.1f}s) past video track 1 end ({video_end:.1f}s)")
        if clip_duration_sec <= 0.0 or clip_duration_sec > max_allowed:
            log.debug(
                "[placer] capping clip duration %.1fs → %.1fs (video track 1 ends at %.1fs)",
                clip_duration_sec, max_allowed, video_end,
            )
            clip_duration_sec = max_allowed

    record_frame = tl_start + _sec_to_frame(segment_start_sec, fps)
    resolved_track = track_index if track_index is not None else _find_or_create_broll_track(timeline)

    # Build clip info — same keys as fusion_placer.py (the working reference)
    clip_info: dict[str, Any] = {
        "mediaPoolItem": mpi,
        "mediaType":     1,
        "startFrame":    _sec_to_frame(clip_start_sec, src_fps) if clip_start_sec > 0.0 else 0,
        "endFrame":      max(1, _sec_to_frame(clip_start_sec + clip_duration_sec, src_fps))
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
