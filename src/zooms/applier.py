"""Apply zoom cuts to a DaVinci Resolve timeline.

Strategy (same non-destructive new-timeline approach as Smart Cuts):
  1. For each clip, split it into sub-segments at zoom boundaries.
  2. On zoom segments, set static ZoomX/ZoomY via SetProperty, offset toward the
     detected face with Pan/Tilt, and enable DynamicZoomEase when fade=True so
     Resolve eases the zoom transition.
  3. Create a new timeline containing the reconstructed segments.

Why SetProperty and not Fusion keyframes: a probe of the Resolve scripting API
(see scripts/zoom_probe.py) confirmed TimelineItem exposes only Get/SetProperty
— no per-clip keyframe API — and that a scripted Fusion Transform tool is not
wired into the comp's render graph, so `SetInput("Size", …)` is a silent no-op.
ZoomX/ZoomY/Pan/Tilt/DynamicZoomEase all read back correctly and do move the
picture; that is the path used here.

Clip segmentation logic lives in applier_props.py.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.timeline_utils import _unique_timeline_name
from src.zooms.applier_props import _segment_clips
from src.zooms.analyzer import ZoomPoint

log = get_logger(__name__)

_DYNAMIC_ZOOM_EASE_IN_OUT = 3  # Resolve DynamicZoomEase value for ease in & out


@dataclass
class ZoomResult:
    new_timeline_name: str
    zooms_applied: int
    total_clips_processed: int


def _apply_segment_zoom(
    item: Any,
    zoom_amount: float,
    pan: float,
    tilt: float,
    fade: bool,
    frame_w: int,
    frame_h: int,
) -> None:
    """Set static zoom + face-centered Pan/Tilt on a timeline item.

    pan/tilt are normalized subject offsets in [-0.5, 0.5]; they are scaled to
    project pixels here. fade enables Resolve's DynamicZoomEase so the zoom
    transition is eased rather than a hard cut.
    """
    item.SetProperty("ZoomX", zoom_amount)
    item.SetProperty("ZoomY", zoom_amount)
    item.SetProperty("ZoomGang", True)

    if pan:
        item.SetProperty("Pan", round(pan * frame_w, 2))
    if tilt:
        item.SetProperty("Tilt", round(tilt * frame_h, 2))

    if fade:
        item.SetProperty("DynamicZoomEase", _DYNAMIC_ZOOM_EASE_IN_OUT)


def apply_zooms(
    resolve: Any,
    timeline: Any,
    clips: list[Any],
    zoom_points: list[ZoomPoint],
    fade: bool = True,
    zoom_amount: float = 1.15,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    target_timeline: Optional[Any] = None,
) -> ZoomResult:
    """Create a timeline with zoom effects applied at the detected points.

    Non-destructive when creating a new timeline; appends to target_timeline if provided.

    Args:
        resolve:           DaVinci Resolve object.
        timeline:          Source timeline.
        clips:             TimelineItems from video track 1.
        zoom_points:       Detected zoom moments.
        fade:              If True, animate via Fusion keyframes (smooth ease in/out).
                           If False, static SetProperty zoom (hard cut).
        zoom_amount:       Scale factor for zoom segments (e.g. 1.15 = 115%).
        progress_callback: Optional progress fn(current, total, message).
        target_timeline:   If set, append clips here instead of creating a new timeline.

    Returns:
        ZoomResult with stats.
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()

    try:
        fps = float(project.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        fps = 25.0

    try:
        frame_w = int(project.GetSetting("timelineResolutionWidth") or 1920)
        frame_h = int(project.GetSetting("timelineResolutionHeight") or 1080)
    except Exception:
        frame_w, frame_h = 1920, 1080

    if target_timeline is not None:
        new_name = target_timeline.GetName()
        log.info("Appending zooms to existing timeline '%s' | %d zoom points", new_name, len(zoom_points))
    else:
        new_name = _unique_timeline_name(project, f"{timeline.GetName()}_zooms")
        log.info("Creating zoom timeline '%s' | %d zoom points", new_name, len(zoom_points))

    zoom_map: dict[int, tuple[int, float, float, float]] = {
        zp.timeline_frame: (
            zp.timeline_frame + zp.duration_frames, zp.zoom_amount, zp.pan, zp.tilt
        )
        for zp in zoom_points
    }

    clip_infos, zoom_meta, clips_processed, zooms_applied = _segment_clips(
        clips, fps, zoom_map, progress_callback, fade=fade,
    )

    if not clip_infos:
        raise RuntimeError("No clip segments found for zoom timeline.")

    if progress_callback:
        progress_callback(len(clips), len(clips), f"Building timeline '{new_name}'...")

    if target_timeline is not None:
        dest_timeline = target_timeline
        project.SetCurrentTimeline(dest_timeline)
        for _ttype in ("video", "audio"):
            try:
                _items = dest_timeline.GetItemListInTrack(_ttype, 1)
                if _items:
                    dest_timeline.DeleteClips(_items)
            except Exception as _e:
                log.warning("Could not clear %s track 1: %s", _ttype, _e)
    else:
        dest_timeline = media_pool.CreateEmptyTimeline(new_name)
        if dest_timeline is None:
            raise RuntimeError(f"Failed to create timeline '{new_name}'.")
        project.SetCurrentTimeline(dest_timeline)

    appended = media_pool.AppendToTimeline(clip_infos)

    if not appended or not isinstance(appended, (list, tuple)):
        raise RuntimeError(
            "AppendToTimeline returned no items — zoom timeline not built. "
            f"(got {type(appended).__name__})"
        )

    if progress_callback:
        progress_callback(len(clips), len(clips), "Applying zoom properties...")

    applied_ok = 0
    for i, (item, meta) in enumerate(zip(appended, zoom_meta)):
        if not meta.get("is_zoom"):
            continue
        try:
            _apply_segment_zoom(
                item,
                meta.get("zoom_amount", zoom_amount),
                meta.get("pan", 0.0),
                meta.get("tilt", 0.0),
                meta.get("fade", fade),
                frame_w,
                frame_h,
            )
            applied_ok += 1
            log.debug("Zoom applied to segment %d: %.2f", i, meta.get("zoom_amount", zoom_amount))
        except Exception as e:
            log.warning("Zoom property failed on segment %d: %s", i, e)

    if applied_ok == 0 and zooms_applied > 0:
        raise RuntimeError(
            "No zoom properties could be applied to any segment — "
            "the timeline was built but every SetProperty call failed."
        )

    log.info(
        "Created zoom timeline '%s': %d/%d zoom(s) applied, %d clip(s) processed",
        new_name, applied_ok, zooms_applied, clips_processed,
    )

    return ZoomResult(
        new_timeline_name=new_name,
        zooms_applied=applied_ok,
        total_clips_processed=clips_processed,
    )
