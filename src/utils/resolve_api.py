"""DaVinci Resolve connection — tries four strategies in order.

Works with both DaVinci Resolve free and Studio editions.

Connection strategy (in order):

0. Caller-supplied ``resolve_obj`` (Resolve's Scripts menu can inject one).
1. **HTTP bridge** (``~/.clautter/bridge.json``) — the recommended path on
   the free edition. ``main.py`` starts a local HTTP server inside
   Resolve's process; the ``gui.py`` subprocess connects to it.
2. ``DaVinciResolveScript.scriptapp("Resolve")`` — Studio only when
   External scripting is enabled.
3. ``getattr(builtins, "resolve", None)`` — covers in-Resolve contexts
   (e.g. the Resolve Scripting Console).

Utility helpers (get_fps, ms_to_frames, etc.) live in resolve_utils.py
and are re-exported here for backwards compatibility.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

_SCRIPTING_MODULES = Path(
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
)


def _ensure_scripting_path() -> None:
    if _SCRIPTING_MODULES.exists() and str(_SCRIPTING_MODULES) not in sys.path:
        sys.path.insert(0, str(_SCRIPTING_MODULES))
        log.debug("Added Resolve scripting path: %s", _SCRIPTING_MODULES)


def _try_bridge() -> Optional[Any]:
    """Return a ResolveProxy rooted at the live Resolve, or None if no bridge."""
    try:
        from src.utils.rpc_client import ResolveProxy, read_bridge_file
    except ImportError as e:
        log.debug("rpc_client unavailable: %s", e)
        return None

    http = read_bridge_file()
    if http is None:
        return None
    return ResolveProxy(ref=None, http=http)


def connect(resolve_obj=None) -> tuple[Any, Any, Any, Any, Any]:
    """Connect to a running DaVinci Resolve instance.

    Returns:
        (resolve, project_manager, project, media_pool, timeline)

    Raises:
        RuntimeError if Resolve is not running or no project is open.
    """
    _ensure_scripting_path()

    resolve = resolve_obj
    if resolve is not None:
        log.debug("Connected via injected resolve global")

    if resolve is None:
        resolve = _try_bridge()
        if resolve is not None:
            log.debug("Connected via HTTP bridge")

    if resolve is None:
        try:
            import DaVinciResolveScript as dvr  # type: ignore
            resolve = dvr.scriptapp("Resolve")
            if resolve is not None:
                log.debug("Connected via DaVinciResolveScript")
        except ImportError:
            log.debug("DaVinciResolveScript not importable — trying built-in globals")

    if resolve is None:
        import builtins
        resolve = getattr(builtins, "resolve", None)
        if resolve is not None:
            log.debug("Connected via builtins.resolve")

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


# ---------------------------------------------------------------------------
# Re-exports from resolve_utils for backwards compatibility
# ---------------------------------------------------------------------------

from src.utils.resolve_utils import (  # noqa: E402
    get_fps,
    ms_to_frames,
    frames_to_ms,
    get_clip_file_path,
    get_all_video_clips,
    get_timeline_names,
    ensure_subtitle_track,
    get_bmd,
)

__all__ = [
    "connect",
    "get_fps",
    "ms_to_frames",
    "frames_to_ms",
    "get_clip_file_path",
    "get_all_video_clips",
    "get_timeline_names",
    "ensure_subtitle_track",
    "get_bmd",
]
