"""Import an SRT file into DaVinci Resolve as a subtitle track."""

from __future__ import annotations
import os
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def import_srt_to_timeline(resolve: Any, srt_path: str, timeline: Any, style: dict | None = None) -> bool:
    """Import an SRT file and attach it to the timeline as a subtitle track.

    DaVinci Resolve does not have a direct scripting API for SRT import as of v20.
    Best available approach:
      1. Import SRT as a Media Pool item.
      2. Add a subtitle track if none exists.
      3. Append the SRT item to the subtitle track.

    Falls back gracefully and logs the SRT path so the user can import manually.
    Returns True if the operation was attempted without errors.
    """
    if not os.path.exists(srt_path):
        log.error("SRT file not found: %s", srt_path)
        return False

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = project.GetMediaPool()

        imported = media_pool.ImportMedia([srt_path])
        srt_item = imported[0] if imported else None
        if not srt_item:
            ext = os.path.splitext(srt_path)[1].lower()
            log.warning(
                "ImportMedia returned empty for %s file: %s — "
                "Resolve may not support this format via the Python API.",
                ext, srt_path,
            )
            return False

        if timeline:
            if timeline.GetTrackCount("subtitle") == 0:
                timeline.AddTrack("subtitle")
                log.info("Added subtitle track to timeline")
            else:
                for _i in range(1, timeline.GetTrackCount("subtitle") + 1):
                    _items = timeline.GetItemListInTrack("subtitle", _i)
                    if _items:
                        try:
                            timeline.DeleteClips(_items)
                            log.debug("Cleared %d subtitle clip(s) from track %d", len(_items), _i)
                        except Exception as _e:
                            log.warning("Could not clear subtitle track %d: %s", _i, _e)

        tl_start = 0
        try:
            if timeline:
                tl_start = timeline.GetStartFrame()
        except Exception as _e:
            log.debug("GetStartFrame failed, falling back to first clip: %s", _e)
            try:
                _v = timeline.GetItemListInTrack("video", 1)
                if _v:
                    tl_start = _v[0].GetStart()
            except Exception:
                pass
        log.info("Placing SRT at timeline frame %d", tl_start)

        if srt_item:
            appended = media_pool.AppendToTimeline([{
                "mediaPoolItem": srt_item,
                "recordFrame": tl_start,
            }])
            if not appended:
                log.warning(
                    "AppendToTimeline returned empty — drag '%s' from Media Pool to subtitle track",
                    srt_path,
                )
            else:
                try:
                    _placed = timeline.GetItemListInTrack("subtitle", 1)
                    if _placed:
                        actual = _placed[0].GetStart()
                        log.info("Subtitle clip landed at frame %d (wanted %d)", actual, tl_start)
                        if actual != tl_start:
                            log.warning(
                                "recordFrame ignored by Resolve for subtitle clips — "
                                "drag subtitle clip to frame %d manually", tl_start
                            )
                        if style:
                            _styled = 0
                            for _item in _placed:
                                try:
                                    _cc = 0
                                    try:
                                        _cc = _item.GetFusionCompCount()
                                    except Exception:
                                        pass
                                    if _cc:
                                        _comp = _item.GetFusionCompByIndex(1)
                                        _tt = _comp.FindToolByID("TextPlus") if _comp else None
                                        if not _tt and _comp:
                                            try:
                                                _tools = _comp.GetToolList()
                                                log.info("Subtitle comp tools: %s", list(_tools.keys()) if _tools else "none")
                                            except Exception:
                                                pass
                                        if _tt:
                                            _tt.SetInput("Font", style.get("font_family", "Arial"))
                                            _tt.SetInput("Size", style.get("font_size", 36) / 360.0)
                                            _pc = style.get("primary_color", "#FFFFFF").lstrip("#")
                                            _tt.SetInput("Red1",   int(_pc[0:2], 16) / 255.0)
                                            _tt.SetInput("Green1", int(_pc[2:4], 16) / 255.0)
                                            _tt.SetInput("Blue1",  int(_pc[4:6], 16) / 255.0)
                                            if style.get("bold"):
                                                _tt.SetInput("Bold", 1)
                                            if style.get("italic"):
                                                _tt.SetInput("Italic", 1)
                                            _styled += 1
                                    else:
                                        try:
                                            _item.SetProperty("Font", style.get("font_family", "Arial"))
                                            _item.SetProperty("FontSize", str(int(style.get("font_size", 36))))
                                        except Exception as _sp:
                                            log.debug("SetProperty fallback failed: %s", _sp)
                                except Exception as _se:
                                    log.warning("Style on subtitle clip %d: %s", _styled, _se)
                            log.info("Applied style to %d/%d subtitle clips", _styled, len(_placed))
                except Exception as _e:
                    log.debug("Post-placement check failed: %s", _e)

        log.info("Subtitle file imported to media pool: %s", srt_path)
        return True

    except Exception as e:
        log.error("import_srt_to_timeline failed: %s", e)
        log.info("Manual import: drag '%s' from Media Pool to the subtitle track.", srt_path)
        return False
