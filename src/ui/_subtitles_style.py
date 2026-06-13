"""Pure style read/write helpers for the Subtitles tab.

All functions take the widget dict `w` and mutable color lists explicitly
so they can live outside the setup() closure.
"""

from __future__ import annotations
from typing import Any


def get_style_overrides(w: dict) -> dict:
    return {
        "words_per_line":  int(w["wpl_slider"].get()),
        "lines_per_block": int(w["lpb_slider"].get()),
        "uppercase":       w["caps_check"].get() == 1,
    }


def get_text_style(
    w: dict,
    text_color: list[str],
    outline_color: list[str],
) -> dict:
    _outline_on = w["outline_enabled_check"].get() == 1
    return {
        "font_family":      w["font_family"].get(),
        "font_size":        int(w["font_size_slider"].get()),
        "bold":             w["bold_check"].get() == 1,
        "italic":           w["italic_check"].get() == 1,
        "underline":        w["underline_check"].get() == 1,
        "primary_color":    text_color[0],
        "outline_enabled":  _outline_on,
        "outline_color":    outline_color[0],
        "outline_width":    int(w["outline_width_slider"].get()) if _outline_on else 0,
        "shadow":           1 if w["shadow_check"].get() == 1 else 0,
        "vertical_position": int(w["vpos_slider"].get()),
    }


def apply_text_style(
    w: dict,
    style: dict,
    text_color: list[str],
    outline_color: list[str],
) -> None:
    w["font_family"].set(style.get("font_family", "Open Sans"))
    size = int(style.get("font_size", 36))
    w["font_size_slider"].set(size)
    w["font_size_lbl"].configure(text=str(size))

    if style.get("bold", False):
        w["bold_check"].select()
    else:
        w["bold_check"].deselect()
    if style.get("italic", False):
        w["italic_check"].select()
    else:
        w["italic_check"].deselect()
    if style.get("underline", False):
        w["underline_check"].select()
    else:
        w["underline_check"].deselect()
    if style.get("shadow", 0):
        w["shadow_check"].select()
    else:
        w["shadow_check"].deselect()

    tc = style.get("primary_color", "#FFFFFF")
    oc = style.get("outline_color", "#000000")
    text_color[0]    = tc
    outline_color[0] = oc
    w["text_color_btn"].configure(fg_color=tc, hover_color=tc)
    w["outline_color_btn"].configure(fg_color=oc, hover_color=oc)

    ow = int(style.get("outline_width", 3))
    w["outline_width_slider"].set(ow)
    w["outline_width_lbl"].configure(text=str(ow))

    _oe = style.get("outline_enabled", ow > 0)
    if _oe:
        w["outline_enabled_check"].select()
    else:
        w["outline_enabled_check"].deselect()
    _outline_ctrl_state = "normal" if _oe else "disabled"
    w["outline_color_btn"].configure(state=_outline_ctrl_state)
    w["outline_width_slider"].configure(state=_outline_ctrl_state)

    vp = int(style.get("vertical_position", -90))
    w["vpos_slider"].set(vp)
    w["vpos_lbl"].configure(text=f"{vp}%")
