"""Get/cache a black Solid Color MediaPoolItem in the DaVinci Resolve Media Pool.

Used to insert black gaps of exact frame duration onto a video track.
Pattern mirrors src/subtitles/fusion_template.py — try Resolve's stock
generator via InsertFusionTitleIntoTimeline, then scan the Media Pool
for an existing match, then give up.

The result is cached for the lifetime of the process; callers should not
mutate or delete the returned item.
"""

from __future__ import annotations
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

_CACHED: Optional[Any] = None  # process-wide cache


def _walk(folder: Any):
    """Yield every MediaPoolItem in the folder tree, best-effort."""
    try:
        for clip in (folder.GetClipList() or []):
            yield clip
    except Exception:
        pass
    try:
        for sub in (folder.GetSubFolderList() or []):
            yield from _walk(sub)
    except Exception:
        pass


def _is_black_solid(item: Any) -> bool:
    """Match Solid Color / black generator by name or type."""
    try:
        props = item.GetClipProperty() or {}
    except Exception:
        return False
    name = (props.get("Clip Name") or "").lower()
    typ = (props.get("Type") or "").lower()
    if "solid" in name and "color" in name:
        return True
    if "generator" in typ and "color" in name:
        return True
    return False


def _scan(media_pool: Any) -> Any | None:
    for clip in _walk(media_pool.GetRootFolder()):
        if _is_black_solid(clip):
            return clip
    return None


def _bootstrap(media_pool: Any, timeline: Any) -> Any | None:
    """Insert Resolve's stock Solid Color into a throwaway clip, then read its MediaPoolItem."""
    try:
        bootstrap_clip = timeline.InsertFusionTitleIntoTimeline("Solid Color")
    except Exception as e:
        log.debug("Solid Color bootstrap: InsertFusionTitleIntoTimeline raised: %s", e)
        return None
    if not bootstrap_clip:
        log.warning("Solid Color bootstrap: InsertFusionTitleIntoTimeline returned None")
        return None

    try:
        item = bootstrap_clip.GetMediaPoolItem()
    finally:
        try:
            timeline.DeleteClips([bootstrap_clip])
        except Exception:
            pass

    if not item:
        log.info("Solid Color bootstrap: GetMediaPoolItem returned None (Free edition)")
        return None
    return item


def get_black_media_item(resolve: Any) -> Any | None:
    """Return a cached black Solid Color MediaPoolItem, or None on failure.

    Side effect: may insert a Solid Color clip into the current timeline and
    immediately delete it (Resolve creates the underlying template as a side
    effect; the resulting MediaPoolItem persists in the Media Pool).
    """
    global _CACHED
    if _CACHED is not None:
        return _CACHED

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
    except Exception as e:
        log.warning("get_black_media_item: no project: %s", e)
        return None
    if project is None:
        return None

    try:
        media_pool = project.GetMediaPool()
        timeline = project.GetCurrentTimeline()
    except Exception as e:
        log.warning("get_black_media_item: project access failed: %s", e)
        return None
    if media_pool is None or timeline is None:
        return None

    item = _scan(media_pool)
    if item is None:
        item = _bootstrap(media_pool, timeline)
    if item is not None:
        name = (item.GetClipProperty() or {}).get("Clip Name", "?")
        log.info("Black Solid Color MediaPoolItem ready: %s", name)
        _CACHED = item
    else:
        log.warning(
            "get_black_media_item: no black Solid Color available — "
            "Track 1 retake gaps will be omitted. Add a Solid Color generator "
            "to the Media Pool for aligned gaps."
        )
    return _CACHED
