"""Clip segmentation for zoom timeline construction.

Extracted from applier.py. Handles splitting clips at zoom boundaries and
building the clip_infos / zoom_meta lists that AppendToTimeline consumes.
"""

from __future__ import annotations
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.zooms.analyzer import ZoomPoint

log = get_logger(__name__)


def _segment_clips(
    clips: list[Any],
    fps: float,
    zoom_map: dict[int, tuple[int, float, float, float]],
    progress_callback: Optional[Callable[[int, int, str], None]],
    fade: bool = True,
) -> tuple[list[dict], list[dict], int, int]:
    """Split clips at zoom boundaries and collect metadata.

    Returns:
        (clip_infos, zoom_meta, clips_processed, zooms_applied)
        clip_infos: dicts ready for AppendToTimeline.
        zoom_meta:  parallel list with is_zoom / zoom_amount / fade flags.
    """
    clip_infos: list[dict] = []
    zoom_meta: list[dict] = []
    clips_processed = 0
    zooms_applied = 0
    total = len(clips)

    for idx, clip in enumerate(clips):
        if progress_callback:
            progress_callback(idx, total, f"Processing clip {idx + 1}/{total}...")

        media_item = clip.GetMediaPoolItem()
        if media_item is None:
            continue

        clip_tl_start = clip.GetStart()
        clip_tl_end = clip.GetEnd()
        src_start = clip.GetSourceStartFrame()
        src_end = clip.GetSourceEndFrame()

        clip_zooms = [
            (zs, ze, zf, pan, tilt)
            for zs, (ze, zf, pan, tilt) in zoom_map.items()
            if clip_tl_start <= zs < clip_tl_end
        ]
        clip_zooms.sort(key=lambda x: x[0])

        if not clip_zooms:
            if src_end > src_start:
                clip_infos.append({
                    "mediaPoolItem": media_item,
                    "startFrame": src_start,
                    "endFrame": src_end,
                })
                zoom_meta.append({"is_zoom": False})
            clips_processed += 1
            continue

        cursor_tl = clip_tl_start
        cursor_src = src_start

        for zoom_start_tl, zoom_end_tl, zoom_factor, pan, tilt in clip_zooms:
            pre_tl_frames = zoom_start_tl - cursor_tl
            if pre_tl_frames > 0:
                clip_infos.append({
                    "mediaPoolItem": media_item,
                    "startFrame": cursor_src,
                    "endFrame": cursor_src + pre_tl_frames - 1,
                })
                zoom_meta.append({"is_zoom": False})

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
                    "pan": pan,
                    "tilt": tilt,
                    "seg_len": zoom_frames,  # segment length in frames — drives Fusion keyframe ramp
                })
                zooms_applied += 1

            cursor_tl = zoom_tl_end
            cursor_src = src_start + (cursor_tl - clip_tl_start)

        tail_frames = clip_tl_end - cursor_tl
        if tail_frames > 0:
            clip_infos.append({
                "mediaPoolItem": media_item,
                "startFrame": cursor_src,
                "endFrame": cursor_src + tail_frames - 1,
            })
            zoom_meta.append({"is_zoom": False})

        clips_processed += 1

    return clip_infos, zoom_meta, clips_processed, zooms_applied
