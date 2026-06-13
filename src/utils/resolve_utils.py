"""DaVinci Resolve helper utilities — frame math, clip/timeline queries.

Extracted from resolve_api.py so that module stays focused on connection logic.
resolve_api.py re-exports everything here for backwards compatibility.
"""

from __future__ import annotations
import sys
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


def get_fps(project: Any) -> float:
    """Return the current timeline frame rate as a float."""
    try:
        return float(project.GetSetting("timelineFrameRate"))
    except (TypeError, ValueError):
        log.warning("Could not read timelineFrameRate, defaulting to 25.0")
        return 25.0


def ms_to_frames(ms: float, fps: float) -> int:
    """Convert milliseconds to frame count (floored)."""
    return int((ms / 1000.0) * fps)


def frames_to_ms(frames: int, fps: float) -> float:
    """Convert frame count to milliseconds."""
    return (frames / fps) * 1000.0


def get_clip_file_path(clip: Any) -> Optional[str]:
    """Return the source media file path for a timeline clip, or None."""
    try:
        media_item = clip.GetMediaPoolItem()
        if media_item is None:
            return None
        props = media_item.GetClipProperty()
        if not isinstance(props, dict):
            return None
        for key in ("File Path", "FilePath", "Clip Path", "clipPath"):
            val = props.get(key)
            if val:
                return str(val)
    except Exception as e:
        log.debug("get_clip_file_path error: %s", e)
    return None


def get_all_video_clips(timeline: Any, track_index: int = 1) -> list[Any]:
    """Return all TimelineItems from a video track (1-based index)."""
    try:
        items = timeline.GetItemListInTrack("video", track_index)
        return list(items) if items else []
    except Exception as e:
        log.error("get_all_video_clips error: %s", e)
        return []


def get_timeline_names(project: Any) -> list[str]:
    """Return list of all timeline names in the project."""
    names = []
    try:
        count = project.GetTimelineCount()
        for i in range(1, count + 1):
            tl = project.GetTimelineByIndex(i)
            if tl:
                names.append(tl.GetName())
    except Exception as e:
        log.debug("get_timeline_names error: %s", e)
    return names


def ensure_subtitle_track(timeline: Any) -> bool:
    """Add a subtitle track if none exists. Returns True on success."""
    try:
        count = timeline.GetTrackCount("subtitle")
        if count == 0:
            return timeline.AddTrack("subtitle")
        return True
    except Exception as e:
        log.error("ensure_subtitle_track error: %s", e)
        return False


def find_named_video_track(timeline: Any, name: str) -> int | None:
    """Return 1-based index of first video track whose name matches, or None."""
    try:
        count = timeline.GetTrackCount("video")
        for i in range(1, count + 1):
            try:
                if (timeline.GetTrackName("video", i) or "").strip().lower() == name.strip().lower():
                    return i
            except Exception:
                continue
    except Exception as e:
        log.debug("find_named_video_track(%r) error: %s", name, e)
    return None


def get_or_create_video_track(timeline: Any, name: str) -> int:
    """Return index of named video track, creating it (at the top) if absent.

    Tolerates SetTrackName failures on free edition — track is still usable.
    Returns -1 on hard failure.
    """
    existing = find_named_video_track(timeline, name)
    if existing is not None:
        return existing
    try:
        count = timeline.GetTrackCount("video")
        timeline.AddTrack("video")
        new_index = count + 1
        try:
            timeline.SetTrackName("video", new_index, name)
        except Exception as e:
            log.debug("SetTrackName(%r) non-fatal: %s", name, e)
        log.info("resolve_utils: created video track %d '%s'", new_index, name)
        return new_index
    except Exception as e:
        log.error("get_or_create_video_track(%r) failed: %s", name, e)
        return -1


# Canonical video track order (bottom to top within Resolve's track stack).
# Track 1 = main footage (always exists). Higher index = higher in the stack.
# Desired visual order (top→bottom on screen): Subtitle → B-Roll → Retakes → Main
# In Resolve track numbering that means: Main(1) < Retakes(~2) < B-Roll < Subtitle
_ORDERED_NAMED_TRACKS = ("B-Roll", "Subtitle")


def ensure_video_track_order(timeline: Any) -> dict[str, int]:
    """Ensure named tracks exist in canonical order: B-Roll below Subtitle.

    Creates any missing tracks so that their indices satisfy:
        broll_idx < subtitle_idx

    Returns a mapping ``{track_name: track_index}`` for all managed tracks.
    Silently no-ops if the timeline already has the correct ordering.
    """
    result: dict[str, int] = {}
    try:
        # First pass: find existing named tracks.
        for track_name in _ORDERED_NAMED_TRACKS:
            idx = find_named_video_track(timeline, track_name)
            if idx is not None:
                result[track_name] = idx

        broll_idx = result.get("B-Roll")
        sub_idx = result.get("Subtitle")

        # Both exist and already ordered correctly — nothing to do.
        if broll_idx is not None and sub_idx is not None and broll_idx < sub_idx:
            return result

        # B-Roll missing: create it. New track always lands on top (highest index).
        if broll_idx is None:
            broll_idx = get_or_create_video_track(timeline, "B-Roll")
            result["B-Roll"] = broll_idx

        # Subtitle missing or below B-Roll: create/re-create above B-Roll.
        # Resolve can't reorder tracks — if Subtitle exists below B-Roll we
        # can't fix it without destructive changes; log a warning instead.
        if sub_idx is None:
            sub_idx = get_or_create_video_track(timeline, "Subtitle")
            result["Subtitle"] = sub_idx
        elif sub_idx < broll_idx:
            log.warning(
                "ensure_video_track_order: Subtitle track (%d) is below B-Roll track (%d). "
                "Resolve does not support track reordering — please manually drag Subtitle "
                "above B-Roll in the timeline.",
                sub_idx, broll_idx,
            )

    except Exception as e:
        log.error("ensure_video_track_order failed: %s", e)
    return result


def get_bmd() -> Any:
    """Return the bmd module injected by DaVinci Resolve's scripting environment."""
    bmd = sys.modules.get("bmd")
    if bmd is not None:
        return bmd
    import builtins
    return getattr(builtins, "bmd", None)
