"""Read style from a Fusion Title clip in the active timeline."""

from __future__ import annotations
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def import_style_thread(
    app: Any,
    set_status: Callable,
    ui: Callable,
    apply_text_style_fn: Callable,
) -> None:
    """Read Text+ inputs from a Fusion Title clip and call apply_text_style_fn with the result."""
    try:
        if not app.timeline:
            set_status("No timeline — connect Resolve first.", "#ff6b6b")
            return
        item = app.timeline.GetCurrentVideoItem()

        if not item:
            log.debug("GetCurrentVideoItem returned None; scanning video tracks")
            try:
                _tc = app.timeline.GetTrackCount("video")
                for _ti in range(1, _tc + 1):
                    for _candidate in (app.timeline.GetItemListInTrack("video", _ti) or []):
                        try:
                            if _candidate.GetFusionCompCount():
                                _c = _candidate.GetFusionCompByIndex(1)
                                if _c and (
                                    _c.FindTool("Template") or _c.FindToolByID("TextPlus")
                                ):
                                    item = _candidate
                                    log.info("Found Fusion Title on video track %d", _ti)
                                    break
                        except Exception:
                            continue
                    if item:
                        break
            except Exception as _e:
                log.debug("Track scan failed: %s", _e)

        if not item:
            set_status(
                "No Fusion Title clip found. Move playhead over a subtitle clip and try again.",
                "#E8903A",
            )
            return

        try:
            comp_count = item.GetFusionCompCount()
        except Exception:
            comp_count = 0
        if not comp_count:
            set_status("Selected clip has no Fusion composition.", "#E8903A")
            return

        comp = item.GetFusionCompByIndex(1)
        text_tool = comp.FindToolByID("TextPlus") or comp.FindTool("Template")
        if not text_tool:
            set_status(
                "No Text+ tool in selected clip. Select a Fusion Title or Text+ generator.",
                "#E8903A",
            )
            return

        style: dict[str, Any] = {}

        font = text_tool.GetInput("Font")
        if font:
            style["font_family"] = str(font)

        size = text_tool.GetInput("Size")
        if size is not None:
            style["font_size"] = max(16, min(72, int(float(size) * 360)))

        r = text_tool.GetInput("Red1")
        g = text_tool.GetInput("Green1")
        b = text_tool.GetInput("Blue1")
        if all(v is not None for v in (r, g, b)):
            style["primary_color"] = "#{:02X}{:02X}{:02X}".format(
                int(float(r) * 255), int(float(g) * 255), int(float(b) * 255))

        style_val = text_tool.GetInput("Style")
        if style_val:
            _sv = str(style_val).lower()
            style["bold"]   = "bold" in _sv
            style["italic"] = "italic" in _sv
        else:
            bold = text_tool.GetInput("Bold")
            if bold is not None:
                style["bold"] = bool(int(float(bold)))
            italic = text_tool.GetInput("Italic")
            if italic is not None:
                style["italic"] = bool(int(float(italic)))

        underline = text_tool.GetInput("Underline")
        if underline is not None:
            style["underline"] = bool(int(float(underline)))

        bw = text_tool.GetInput("BorderWidth")
        if bw is not None:
            style["outline_width"] = max(0, min(6, round(float(bw) * 100)))

        br = text_tool.GetInput("Red2")
        bg = text_tool.GetInput("Green2")
        bb = text_tool.GetInput("Blue2")
        if all(v is not None for v in (br, bg, bb)):
            style["outline_color"] = "#{:02X}{:02X}{:02X}".format(
                int(float(br) * 255), int(float(bg) * 255), int(float(bb) * 255))

        enabled2 = text_tool.GetInput("Enabled2")
        if enabled2 is not None:
            style["outline_enabled"] = float(enabled2) > 0.5
        else:
            style["outline_enabled"] = style.get("outline_width", 0) > 0

        shadow = text_tool.GetInput("Enabled3")
        if shadow is not None:
            style["shadow"] = 1 if float(shadow) > 0.5 else 0

        if not style:
            try:
                inputs = text_tool.GetInputList()
                log.info("TextPlus inputs: %s", list(inputs.values()) if inputs else "none")
            except Exception as _e:
                log.debug("GetInputList failed: %s", _e)
            set_status(
                "Could not read style from clip. Check log for available inputs.", "#E8903A")
            return

        log.info("Imported style from Resolve clip: %s", style)
        ui(lambda: apply_text_style_fn(style))
        set_status("Style imported from Fusion clip.", "#66bb6a")

    except Exception as e:
        log.error("Import style from Resolve: %s", e)
        set_status(f"Import error: {e}", "#ff6b6b")
