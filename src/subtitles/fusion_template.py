"""Locate or bootstrap a Fusion Title template in the DaVinci Resolve Media Pool."""

from __future__ import annotations
import os
import pathlib
from typing import Any

from src.subtitles.presets import FUSION_TITLE_TYPES
from src.utils.logger import get_logger

log = get_logger(__name__)


def walk_media_pool(folder: Any):
    """Yield all MediaPoolItem objects in folder tree."""
    try:
        for clip in (folder.GetClipList() or []):
            yield clip
    except Exception:
        pass
    try:
        for sub in (folder.GetSubFolderList() or []):
            yield from walk_media_pool(sub)
    except Exception:
        pass


def find_fusion_title_template(media_pool: Any) -> Any | None:
    """Return first Fusion Title item from Media Pool.

    If none found, imports the bundled subtitle_template.drb from Clutter's
    own assets folder (no external dependency).
    """
    def _scan():
        for clip in walk_media_pool(media_pool.GetRootFolder()):
            try:
                props = clip.GetClipProperty()
                clip_name = props.get("Clip Name", "").lower()
                if (props.get("Type") in FUSION_TITLE_TYPES
                        or "text+" in clip_name):
                    log.debug("Fusion Title template: %s (type=%s)",
                              props.get("Clip Name"), props.get("Type"))
                    return clip
            except Exception:
                pass
        return None

    def _import_drb(drb: str) -> None:
        for attempt in (
            lambda: media_pool.ImportFolderFromFile(drb, ""),
            lambda: media_pool.ImportFolderFromFile(drb),
        ):
            try:
                attempt()
                return
            except Exception:
                pass

    result = _scan()
    if result:
        log.info("Reusing Fusion Title template from Media Pool: %s",
                 result.GetClipProperty().get("Clip Name", "?"))
        return result

    _own_drb = str(
        pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "subtitle_template.drb"
    )
    if os.path.exists(_own_drb):
        log.info("No Fusion Title in Media Pool — importing bundled template: %s", _own_drb)
        _import_drb(_own_drb)
        result = _scan()
        if result:
            return result

    log.warning(
        "find_fusion_title_template: no Fusion Title template found and bundled DRB unavailable. "
        "Drag a Text+ title from the Titles panel into the Media Pool to create one."
    )
    return None


def bootstrap_textplus_template(
    resolve: Any, timeline: Any, style: dict, media_pool: Any
) -> Any | None:
    """Insert Resolve's stock Text+, apply our style, return MediaPoolItem.

    Returns the template MediaPoolItem to be used as the source for
    AppendToTimeline. Returns None on any failure.
    """
    try:
        bootstrap_clip = timeline.InsertFusionTitleIntoTimeline("Text+")
        if not bootstrap_clip:
            log.warning("Bootstrap: InsertFusionTitleIntoTimeline returned None")
            return None

        template_mp = bootstrap_clip.GetMediaPoolItem()
        if not template_mp:
            log.info("Bootstrap: GetMediaPoolItem returned None (Resolve Free) — scanning Media Pool")
            for candidate in walk_media_pool(media_pool.GetRootFolder()):
                try:
                    if candidate.GetClipProperty().get("Type") in FUSION_TITLE_TYPES:
                        template_mp = candidate
                        log.info("Bootstrap: found %s in Media Pool via scan",
                                 candidate.GetClipProperty().get("Clip Name"))
                        break
                except Exception:
                    continue
        if not template_mp:
            log.warning("Bootstrap: Media Pool scan also failed")
            try:
                timeline.DeleteClips([bootstrap_clip])
            except Exception:
                pass
            return None

        try:
            comp = template_mp.GetFusionCompByIndex(1)
            tool = comp.FindToolByID("TextPlus") if comp else None
            if tool:
                color_hex = style.get("primary_color", "#FFFFFF").lstrip("#")
                _font_style = style.get("font_style")
                if _font_style:
                    _style_str = _font_style
                else:
                    _b = style.get("bold", False)
                    _i = style.get("italic", False)
                    _style_str = (
                        "Bold Italic" if _b and _i else
                        "Bold" if _b else
                        "Italic" if _i else
                        "Regular"
                    )
                for attr, val in (
                    ("Font",     style.get("font_family", "Open Sans")),
                    ("Style",    _style_str),
                    ("Size",     style.get("font_size", 32) / 360.0),
                    ("Red1",     int(color_hex[0:2], 16) / 255.0 or 1e-7),
                    ("Green1",   int(color_hex[2:4], 16) / 255.0 or 1e-7),
                    ("Blue1",    int(color_hex[4:6], 16) / 255.0 or 1e-7),
                    ("Bold",     1 if _b else 0),
                    ("Italic",   1 if _i else 0),
                    ("Underline", 1 if style.get("underline", False) else 0),
                ):
                    try:
                        tool.SetInput(attr, val)
                    except Exception as e:
                        log.debug("template SetInput %s: %s", attr, e)
                ow = style.get("outline_width", 0)
                try:
                    tool.SetInput("BorderWidth", ow / 100.0)
                except Exception:
                    pass
                _outline_on = style.get("outline_enabled", True) and ow > 0
                try:
                    tool.SetInput("Enabled2", 1 if _outline_on else 0)
                except Exception:
                    pass
                oc_hex = style.get("outline_color", "#000000").lstrip("#")
                for attr, val in (
                    ("Red2",   int(oc_hex[0:2], 16) / 255.0 or 1e-7),
                    ("Green2", int(oc_hex[2:4], 16) / 255.0 or 1e-7),
                    ("Blue2",  int(oc_hex[4:6], 16) / 255.0 or 1e-7),
                ):
                    try:
                        tool.SetInput(attr, val)
                    except Exception:
                        pass
                try:
                    tool.SetInput("Enabled3", 1 if style.get("shadow", 0) else 0)
                except Exception:
                    pass
                for attr, val in (
                    ("VerticalJustificationNew",   style.get("vertical_align", 3)),
                    ("HorizontalJustificationNew", style.get("horizontal_align", 3)),
                ):
                    try:
                        tool.SetInput(attr, val)
                    except Exception:
                        pass
                v = style.get("vertical_position")
                if v is not None:
                    center_y = max(0.15, min(0.85, 0.5 + (v / 100.0) * 0.35))
                    try:
                        tool.SetInput("VerticalJustificationNew", 2)
                    except Exception:
                        pass
                    try:
                        tool.SetInput("Center", {1: 0.5, 2: center_y})
                    except Exception:
                        pass
                log.info(
                    "Bootstrap template styled: font=%s size=%.3f bold=%s",
                    style.get("font_family", "Open Sans"),
                    style.get("font_size", 36) / 360.0,
                    style.get("bold", False),
                )
        except Exception as e:
            log.debug("Bootstrap style apply: %s", e)

        try:
            timeline.DeleteClips([bootstrap_clip])
            log.debug("Bootstrap clip deleted; template MP kept for cloning")
        except Exception as e:
            log.warning("Bootstrap clip delete failed: %s", e)

        return template_mp

    except Exception as e:
        log.warning("Bootstrap template failed: %s", e)
        return None
