"""Resolve timeline placer for rendered motion graphics.

Imports an MP4 into the Resolve media pool and places it on the named
'Motion Graphics' video track at the correct frame position.

Track ordering strategy:
  - Searches existing tracks for "Motion Graphics" by name — reuses if found.
  - If not found, adds a new video track and names it "Motion Graphics".
  - Resolve's AddTrack appends above all existing tracks, which puts it above
    B-Roll. Subtitles should be added after motion graphics in the subtitle
    workflow, keeping the stacking order: main → B-Roll → Motion Graphics → Subtitle.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger
from src.graphics.llm_director import GraphicPlacement

log = get_logger(__name__)


def _find_or_create_motion_graphics_track(timeline: Any) -> int:
    """Return 1-based video track index for 'Motion Graphics' track."""
    try:
        count = timeline.GetTrackCount("video")
        for i in range(1, count + 1):
            try:
                name = timeline.GetTrackName("video", i) or ""
                if name.strip().lower() == "motion graphics":
                    log.debug("[gfx_placer] found existing Motion Graphics track at index %d", i)
                    return i
            except Exception:
                continue

        timeline.AddTrack("video")
        new_index = count + 1
        try:
            timeline.SetTrackName("video", new_index, "Motion Graphics")
            log.info("[gfx_placer] created Motion Graphics track at video index %d", new_index)
        except Exception as e:
            log.debug("[gfx_placer] SetTrackName failed (non-fatal): %s", e)
        return new_index
    except Exception as e:
        log.warning("[gfx_placer] _find_or_create_motion_graphics_track failed (%s) — using track 3", e)
        return 3


def _fps_from_timeline(timeline: Any) -> float:
    try:
        fps_str = str(timeline.GetSetting("timelineFrameRate") or "")
        return float(fps_str) if fps_str else 30.0
    except Exception:
        return 30.0


def place(
    mp4_path: Path,
    placement: GraphicPlacement,
    resolve: Any,
    timeline: Any,
) -> bool:
    """Import mp4_path into media pool and place on Motion Graphics track.

    Args:
        mp4_path:   Path to rendered output.mp4.
        placement:  GraphicPlacement with start_sec / duration_sec.
        resolve:    Live resolve object (or ResolveProxy).
        timeline:   Current timeline object.

    Returns:
        True on success.
    """
    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = project.GetMediaPool()

        items = media_pool.ImportMedia([str(mp4_path)])
        if not items:
            log.warning("[gfx_placer] ImportMedia returned nothing for %s", mp4_path)
            return False
        media_item = items[0]

        track_idx = _find_or_create_motion_graphics_track(timeline)
        fps = _fps_from_timeline(timeline)

        try:
            tl_start = timeline.GetStartFrame()
        except Exception:
            tl_start = 0

        record_frame = tl_start + int(placement.start_sec * fps)
        end_frame = max(1, int(placement.duration_sec * fps))

        clip_info: dict[str, Any] = {
            "mediaPoolItem": media_item,
            "mediaType":     1,
            "startFrame":    0,
            "endFrame":      end_frame,
            "recordFrame":   record_frame,
            "trackIndex":    track_idx,
        }
        result = media_pool.AppendToTimeline([clip_info])
        if result:
            log.info(
                "[gfx_placer] placed %s on track %d at %.1fs (recordFrame %d)",
                mp4_path.name, track_idx, placement.start_sec, record_frame,
            )
            return True
        log.warning(
            "[gfx_placer] AppendToTimeline returned empty for %s "
            "(track %d, recordFrame %d) — may be free edition restriction",
            mp4_path.name, track_idx, record_frame,
        )
        return False

    except Exception as e:
        log.warning("[gfx_placer] place() failed for %s: %s", mp4_path, e)
        return False
