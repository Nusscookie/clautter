"""Apply text style and content to Fusion Title clips."""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def apply_fusion_text_style(
    item: Any,
    text: str,
    style: dict,
    highlight_color: str | None = None,
) -> None:
    """Set text content and visual style on a Fusion Title clip.

    Handles both plain TextPlus clips (tool ID "TextPlus", input "StyledText")
    and AutoSubs Caption macro clips (tool name "Template", input "Text").
    Each SetInput is individually guarded so a missing input doesn't abort styling.
    """
    try:
        comp = item.GetFusionCompByIndex(1)
        if not comp:
            return
        # Prefer the actual TextPlus tool (accessible inside macros via FindToolByID).
        tool = comp.FindToolByID("TextPlus") or comp.FindTool("Template")
        if not tool:
            log.debug("apply_fusion_text_style: no TextPlus tool found in comp")
            return

        for input_name in ("StyledText", "Text"):
            try:
                tool.SetInput(input_name, text)
                break
            except Exception:
                pass

        color_hex = (highlight_color or style.get("primary_color", "#FFFFFF")).lstrip("#")
        for attr, val in (
            ("Font",   style.get("font_family", "Open Sans")),
            ("Size",   style.get("font_size", 36) / 360.0),
            ("Red1",   int(color_hex[0:2], 16) / 255.0),
            ("Green1", int(color_hex[2:4], 16) / 255.0),
            ("Blue1",  int(color_hex[4:6], 16) / 255.0),
        ):
            try:
                tool.SetInput(attr, val)
            except Exception:
                pass

        # Style selects the actual font face — authoritative over Bool Bold/Italic inputs.
        _b = style.get("bold", False)
        _i = style.get("italic", False)
        _style_str = ("Bold Italic" if _b and _i else "Bold" if _b else "Italic" if _i else "Regular")
        try:
            tool.SetInput("Style", _style_str)
        except Exception:
            pass
        for flag, attr in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
            try:
                tool.SetInput(attr, 1 if style.get(flag, False) else 0)
            except Exception:
                pass

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
            ("Red2",   int(oc_hex[0:2], 16) / 255.0),
            ("Green2", int(oc_hex[2:4], 16) / 255.0),
            ("Blue2",  int(oc_hex[4:6], 16) / 255.0),
        ):
            try:
                tool.SetInput(attr, val)
            except Exception:
                pass

        try:
            tool.SetInput("Enabled3", 1 if style.get("shadow", 0) else 0)
        except Exception:
            pass

    except Exception as e:
        log.debug("apply_fusion_text_style: %s", e)


def set_comp_text(comp: Any, text: str) -> bool:
    """Set the StyledText/Text input on a Fusion comp's TextPlus. Returns True if set."""
    if not comp:
        return False
    try:
        tool = comp.FindTool("Template") or comp.FindToolByID("TextPlus")
        if not tool:
            return False
        for input_name in ("StyledText", "Text"):
            try:
                tool.SetInput(input_name, text)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False
