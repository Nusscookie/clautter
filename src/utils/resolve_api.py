"""DaVinci Resolve API helpers — connection, timeline utilities, frame math.

Works with both DaVinci Resolve free and Studio editions.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

# Standard Windows path for the DaVinci scripting module
_SCRIPTING_MODULES = Path(
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
)


def _ensure_scripting_path() -> None:
    if _SCRIPTING_MODULES.exists() and str(_SCRIPTING_MODULES) not in sys.path:
        sys.path.insert(0, str(_SCRIPTING_MODULES))
        log.debug("Added Resolve scripting path: %s", _SCRIPTING_MODULES)


def connect() -> tuple[Any, Any, Any, Any, Any]:
    """Connect to a running DaVinci Resolve instance.

    Returns:
        (resolve, project_manager, project, media_pool, timeline)

    Raises:
        RuntimeError if Resolve is not running or no project is open.
    """
    _ensure_scripting_path()

    resolve = None

    # Strategy 1: DaVinciResolveScript module (external / standalone scripts)
    try:
        import DaVinciResolveScript as dvr  # type: ignore
        resolve = dvr.scriptapp("Resolve")
        log.debug("Connected via DaVinciResolveScript")
    except ImportError:
        log.debug("DaVinciResolveScript not importable — trying built-in globals")

    # Strategy 2: Globals injected by Resolve when running from Scripts menu
    if resolve is None:
        import builtins
        resolve = getattr(builtins, "resolve", None)

    if resolve is None:
        raise RuntimeError(
            "Cannot connect to DaVinci Resolve.\n"
            "Make sure DaVinci Resolve is running and try again."
        )

    pm = resolve.GetProjectManager()
    if pm is None:
        raise RuntimeError("Failed to get ProjectManager from Resolve.")

    project = pm.GetCurrentProject()
    if project is None:
        raise RuntimeError(
            "No project open in DaVinci Resolve.\n"
            "Please open a project first."
        )

    media_pool = project.GetMediaPool()
    timeline = project.GetCurrentTimeline()

    log.info(
        "Connected to Resolve — project: %s | timeline: %s",
        project.GetName(),
        timeline.GetName() if timeline else "None",
    )
    return resolve, pm, project, media_pool, timeline


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


def get_bmd() -> Any:
    """Return the bmd module injected by DaVinci Resolve's scripting environment."""
    # bmd is registered in sys.modules as a side effect of loading fusionscript
    bmd = sys.modules.get("bmd")
    if bmd is not None:
        return bmd
    # Fallback: check builtins (some Resolve versions inject it there)
    import builtins
    return getattr(builtins, "bmd", None)
