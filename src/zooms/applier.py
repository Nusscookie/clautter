"""Apply zoom cuts to a DaVinci Resolve timeline.

Strategy (same non-destructive new-timeline approach as Smart Cuts):
  1. For each clip, split it into sub-segments at zoom boundaries.
  2. On zoom segments, call SetProperty("ZoomX" / "ZoomY") with the zoom factor.
  3. For fade zooms, also set DynamicZoomEase on the zoom segment.
  4. Create a new timeline containing the reconstructed segments.

Because DaVinci's scripting API has no direct keyframe-per-frame zoom API in V1,
this approach uses static zoom values per segment (hard-cut or dynamic-zoom-ease style).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.resolve_api import get_clip_file_path, ms_to_frames
from src.zooms.analyzer import ZoomPoint

log = get_logger(__name__)

# DaVinci Resolve DynamicZoomEase constants
_ZOOM_EASE_LINEAR = 0
_ZOOM_EASE_IN_AND_OUT = 3


@dataclass
class ZoomResult:
    new_timeline_name: str
    zooms_applied: int
    total_clips_processed: int


def _unique_timeline_name(project: Any, base: str) -> str:
    try:
        existing = {
            project.GetTimelineByIndex(i + 1).GetName()
            for i in range(project.GetTimelineCount())
        }
    except Exception:
        existing = set()
    name = base
    i = 2
    while name in existing:
        name = f"{base}_{i}"
        i += 1
    return name


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

    # Build a frame-indexed set of zoom regions: {start_frame: (end_frame, zoom_factor)}
    zoom_map: dict[int, tuple[int, float]] = {}
    for zp in zoom_points:
        zoom_map[zp.timeline_frame] = (
            zp.timeline_frame + zp.duration_frames,
            zp.zoom_amount,
        )

    clip_infos: list[dict] = []
    zoom_meta: list[dict] = []  # track which segments are zoom segments
    clips_processed = 0
    zooms_applied = 0

    total = len(clips)
    for idx, clip in enumerate(clips):
        if progress_callback:
            progress_callback(idx, total, f"Processing clip {idx + 1}/{total}...")

        media_item = clip.GetMediaPoolItem()
        if media_item is None:
            continue

        clip_tl_start = clip.GetStart()       # timeline frame
        clip_tl_end = clip.GetEnd()           # timeline frame
        src_start = clip.GetSourceStartFrame()
        src_end = clip.GetSourceEndFrame()

        # Find zoom points that fall within this clip
        clip_zooms = [
            (zs, ze, zf)
            for zs, (ze, zf) in zoom_map.items()
            if clip_tl_start <= zs < clip_tl_end
        ]
        clip_zooms.sort(key=lambda x: x[0])

        if not clip_zooms:
            # No zooms for this clip — include as one segment unchanged
            if src_end > src_start:
                clip_infos.append({
                    "mediaPoolItem": media_item,
                    "startFrame": src_start,
                    "endFrame": src_end,
                })
                zoom_meta.append({"is_zoom": False})
            clips_processed += 1
            continue

        # Build segments: [normal, zoom, normal, zoom, ...]
        cursor_tl = clip_tl_start
        cursor_src = src_start

        for zoom_start_tl, zoom_end_tl, zoom_factor in clip_zooms:
            # Normal segment before this zoom
            pre_tl_frames = zoom_start_tl - cursor_tl
            if pre_tl_frames > 0:
                clip_infos.append({
                    "mediaPoolItem": media_item,
                    "startFrame": cursor_src,
                    "endFrame": cursor_src + pre_tl_frames - 1,
                })
                zoom_meta.append({"is_zoom": False})

            # Zoom segment
            zoom_tl_end = min(zoom_end_tl, clip_tl_end)
            zoom_frames = zoom_tl_end - zoom_start_tl
            if zoom_frames > 0:
                zoom_src_start = cursor_src + pre_tl_frames
                clip_infos.append({
                    "mediaPoolItem": media_item,
                    "startFrame": zoom_src_start,
                    "endFrame": zoom_src_start + zoom_frames - 1,
                })
                zoom_meta.append({
                    "is_zoom": True,
                    "zoom_amount": zoom_factor,
                    "fade": fade,
                })
                zooms_applied += 1

            cursor_tl = zoom_tl_end
            cursor_src = src_start + (cursor_tl - clip_tl_start)

        # Trailing normal segment
        tail_frames = clip_tl_end - cursor_tl
        if tail_frames > 0:
            clip_infos.append({
                "mediaPoolItem": media_item,
                "startFrame": cursor_src,
                "endFrame": cursor_src + tail_frames - 1,
            })
            zoom_meta.append({"is_zoom": False})

        clips_processed += 1

    if not clip_infos:
        raise RuntimeError("No clip segments found for zoom timeline.")

    if progress_callback:
        progress_callback(total, total, f"Building timeline '{new_name}'...")

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
        # Apply zoom properties to zoom segments
        if progress_callback:
            progress_callback(total, total, "Applying zoom properties...")

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
