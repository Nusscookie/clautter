"""Apply zoom cuts to a DaVinci Resolve timeline.

Strategy (same non-destructive new-timeline approach as Smart Cuts):
  1. For each clip, split it into sub-segments at zoom boundaries.
  2. On zoom segments, call SetProperty("ZoomX" / "ZoomY") with the zoom factor.
  3. For fade zooms, also set DynamicZoomEase on the zoom segment.
  4. Create a new timeline containing the reconstructed segments.

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

_ZOOM_EASE_LINEAR = 0
_ZOOM_EASE_IN_AND_OUT = 3


@dataclass
class ZoomResult:
    new_timeline_name: str
    zooms_applied: int
    total_clips_processed: int


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
        fade:              If True, use DynamicZoomEase (smooth transition).
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

    if target_timeline is not None:
        new_name = target_timeline.GetName()
        log.info("Appending zooms to existing timeline '%s' | %d zoom points", new_name, len(zoom_points))
    else:
        new_name = _unique_timeline_name(project, f"{timeline.GetName()}_zooms")
        log.info("Creating zoom timeline '%s' | %d zoom points", new_name, len(zoom_points))

    zoom_map: dict[int, tuple[int, float]] = {
        zp.timeline_frame: (zp.timeline_frame + zp.duration_frames, zp.zoom_amount)
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
                _count = dest_timeline.GetTrackCount(_ttype)
                for _i in range(1, _count + 1):
                    _items = dest_timeline.GetItemListInTrack(_ttype, _i)
                    if _items:
                        dest_timeline.DeleteClips(_items)
            except Exception as _e:
                log.warning("Could not clear %s tracks: %s", _ttype, _e)
    else:
        dest_timeline = media_pool.CreateEmptyTimeline(new_name)
        if dest_timeline is None:
            raise RuntimeError(f"Failed to create timeline '{new_name}'.")
        project.SetCurrentTimeline(dest_timeline)

    appended = media_pool.AppendToTimeline(clip_infos)

    if appended and isinstance(appended, (list, tuple)):
        if progress_callback:
            progress_callback(len(clips), len(clips), "Applying zoom properties...")

        for i, (item, meta) in enumerate(zip(appended, zoom_meta)):
            if not meta.get("is_zoom"):
                continue
            try:
                z = meta.get("zoom_amount", zoom_amount)
                item.SetProperty("ZoomX", z)
                item.SetProperty("ZoomY", z)
                item.SetProperty("ZoomGang", True)
                if meta.get("fade"):
                    item.SetProperty("DynamicZoomEase", _ZOOM_EASE_IN_AND_OUT)
                log.debug("Zoom applied to segment %d: %.2f", i, z)
            except Exception as e:
                log.warning("SetProperty failed on segment %d: %s", i, e)
    else:
        log.warning("AppendToTimeline returned unexpected result — zoom properties not applied")

    log.info(
        "Created zoom timeline '%s': %d zoom(s), %d clip(s) processed",
        new_name, zooms_applied, clips_processed,
    )

    return ZoomResult(
        new_timeline_name=new_name,
        zooms_applied=zooms_applied,
        total_clips_processed=clips_processed,
    )
