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

# Cap fill-frame zoom. CSS-cover math (zoom = cover/fit) is mathematically correct
# for a clean aspect mismatch, but B-roll footage is often a wide picture with black
# bars BAKED INTO the pixels inside a nominal 16:9 file — so the file resolution
# reports 16:9 while the visible content is wider. Covering on the file aspect then
# over-crops massively (e.g. 16:9 file → 9:16 timeline computes 3.16x, but the real
# picture only needs ~1.4x). We can't measure the baked-in bars from metadata, so we
# clamp the zoom: cover what we can up to the cap, and accept residual bars beyond it
# rather than crop the subject to oblivion.
_MAX_FILL_ZOOM = 1.5


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


def _video_track1_end_sec(timeline: Any, fps: float) -> float | None:
    """Return the end time (seconds) of the last item on video track 1, or None.

    Used to cap B-roll duration so clips don't overhang the main video clip.
    """
    try:
        tl_start = timeline.GetStartFrame()
        items = timeline.GetItemListInTrack("video", 1) or []
        if not items:
            return None
        end_frame = max(item.GetEnd() for item in items)
        return (end_frame - tl_start) / fps
    except Exception as e:
        log.debug("[placer] _video_track1_end_sec failed (non-fatal): %s", e)
        return None


def _apply_fill_frame(timeline_item: Any, mpi: Any, project: Any) -> None:
    """Zoom-crop clip to fill the timeline frame with no black bars (CSS cover math).

    Resolve places clips with ZoomX/ZoomY=1.0 meaning "fit" (letterboxed/pillarboxed).
    To cover, we need zoom = cover_scale / fit_scale, where:
      fit_scale   = min(tl_w/clip_w, tl_h/clip_h)  (how Resolve fits the clip)
      cover_scale = max(tl_w/clip_w, tl_h/clip_h)  (what fills the frame)
    This relative zoom works for any orientation pair (portrait←landscape, etc.).
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
        scale_x = tl_w / clip_w
        scale_y = tl_h / clip_h
        fit_scale = min(scale_x, scale_y)
        cover_scale = max(scale_x, scale_y)
        zoom = cover_scale / fit_scale
        if zoom > _MAX_FILL_ZOOM:
            log.debug("[placer] fill_frame: capping zoom %.3f → %.3f", zoom, _MAX_FILL_ZOOM)
            zoom = _MAX_FILL_ZOOM
        timeline_item.SetProperty("ZoomX", zoom)
        timeline_item.SetProperty("ZoomY", zoom)
        timeline_item.SetProperty("ZoomGang", True)
        # SetProperty("ZoomX") silently no-ops on Resolve free — verify it took,
        # and fall back to a wired Fusion Transform (the proven-rendering path) if
        # not, so the bars are actually removed on the free edition.
        if not _zoom_took(timeline_item, zoom):
            from src.zooms.applier import apply_fusion_static_zoom
            apply_fusion_static_zoom(timeline_item, zoom)
            log.info("[placer] fill_frame: ZoomX no-op (free edition?) — used Fusion static zoom")
        log.debug("[placer] fill_frame: %dx%d → %dx%d zoom=%.4f", clip_w, clip_h, tl_w, tl_h, zoom)
    except Exception as e:
        log.warning("[placer] fill_frame failed (non-fatal): %s", e)


def _zoom_took(timeline_item: Any, expected: float) -> bool:
    """True if SetProperty("ZoomX") actually applied (read it back).

    Mirrors src/zooms/applier._zoom_took: the static zoom property can silently
    no-op on Resolve free. Returns True conservatively if the value can't be read.
    """
    try:
        got = timeline_item.GetProperty("ZoomX")
        if got is None:
            return True
        return abs(float(got) - float(expected)) < 0.01
    except Exception:
        return True


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
