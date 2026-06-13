"""Callback factory for the Subtitles tab.

All event handlers are closures over the shared state. Call make_callbacks()
from setup() and wire the returned dict to the widget commands.
"""

from __future__ import annotations
import threading
from typing import Any, Callable

from src.ui._subtitles_data import (
    LANG_CODES, PRESET_DEFAULTS, STYLE_PRESETS, WHISPER_MODEL_MAP, WHISPER_MODELS,
)
from src.ui._subtitles_style import apply_text_style, get_style_overrides, get_text_style
from src.ui._subtitles_generate import generate_thread
from src.ui._subtitles_workers import create_track_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def make_callbacks(
    w: dict,
    frame: Any,
    app: Any,
    _state: dict,
    _text_color: list[str],
    _outline_color: list[str],
    set_status: Callable,
    set_progress: Callable,
    set_btn: Callable,
    _ui: Callable,
) -> dict[str, Callable]:
    """Return all subtitle-tab callbacks as closures over the provided state."""

    def on_whisper_model_changed(value: str) -> None:
        app.settings.set("whisper_model", value)

    def on_generate() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(
            target=generate_thread,
            args=(w, frame, app, _state, LANG_CODES, WHISPER_MODEL_MAP,
                  set_status, set_btn, set_progress, _ui),
            daemon=True,
        ).start()

    def on_create_track() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        try:
            from src.ui.timeline_dialog import find_named_video_track, show_timeline_dialog
            _subtitle_track_idx: int | None = None
            if app.timeline:
                _subtitle_track_idx = find_named_video_track(app.timeline, "Subtitle")
            choice = show_timeline_dialog(
                frame, app.project,
                secondary_section={
                    "detect": _subtitle_track_idx is not None,
                    "label": "Subtitle layer",
                    "existing_text": f"Use existing 'Subtitle' layer (track {_subtitle_track_idx})",
                    "new_text": "Create new layer above",
                    "key": "track_mode",
                } if app.timeline else None,
            )
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", "#ff6b6b")
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice["timeline"]
        _state["track_mode"] = choice.get("track_mode", "new")
        _state["subtitle_track_index"] = (
            _subtitle_track_idx if choice.get("track_mode") == "existing" else None
        )
        _transcript_text = w["transcript"].get("0.0", "end").strip()
        _style      = get_style_overrides(w)
        _preset     = w["preset"].get()
        _text_style = get_text_style(w, _text_color, _outline_color)
        threading.Thread(
            target=create_track_thread,
            args=(w, app, _state, _transcript_text, _style, _preset, _text_style,
                  set_status, set_btn),
            daemon=True,
        ).start()

    def on_export_srt() -> None:
        try:
            from src.subtitles.exporter import export_srt
            import os
            if not _state["srt_content"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return
            path = os.path.join(os.path.expanduser("~"), "Desktop", "subtitles.srt")
            export_srt(_state["srt_content"], path)
            set_status(f"SRT exported to: {path}", "#66bb6a")
        except Exception as e:
            set_status(f"Export error: {e}", "#ff6b6b")

    def on_export_txt() -> None:
        try:
            from src.subtitles.exporter import export_txt
            import os
            if not _state["words"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return
            text = " ".join(w2["word"] for w2 in _state["words"] if w2.get("type") == "word")
            path = os.path.join(os.path.expanduser("~"), "Desktop", "transcript.txt")
            export_txt(text, path)
            set_status(f"TXT exported to: {path}", "#66bb6a")
        except Exception as e:
            set_status(f"Export error: {e}", "#ff6b6b")

    def on_preset_changed(value: str) -> None:
        app.settings.set("subtitle_preset", value)
        wpl, lpb, caps, _hcol = PRESET_DEFAULTS.get(value, (7, 2, False, "#FFFF00"))
        w["wpl_slider"].set(wpl)
        w["wpl_label"].configure(text=str(wpl))
        w["lpb_slider"].set(lpb)
        w["lpb_label"].configure(text=str(lpb))
        if caps:
            w["caps_check"].select()
        else:
            w["caps_check"].deselect()

    def on_font_size(val: float) -> None:
        w["font_size_lbl"].configure(text=str(int(val)))

    def on_outline_width(val: float) -> None:
        w["outline_width_lbl"].configure(text=str(int(val)))

    def _pick_color(current: list[str], btn_key: str, title: str) -> None:
        import tkinter.colorchooser
        result = tkinter.colorchooser.askcolor(color=current[0], title=title)
        if result and result[1]:
            current[0] = result[1].upper()
            w[btn_key].configure(fg_color=current[0], hover_color=current[0])

    def on_outline_toggle() -> None:
        enabled = w["outline_enabled_check"].get() == 1
        state = "normal" if enabled else "disabled"
        w["outline_color_btn"].configure(state=state)
        w["outline_width_slider"].configure(state=state)

    def _font_has_variant(family: str, *, bold: bool = False, italic: bool = False) -> bool:
        try:
            import tkinter.font as _tkfont
            weight = "bold" if bold else "normal"
            slant  = "italic" if italic else "roman"
            f = _tkfont.Font(family=family, weight=weight, slant=slant, size=12)
            return f.actual().get("family", "").lower() == family.lower()
        except Exception:
            return True

    def on_font_changed(value: str) -> None:
        state_bold   = "normal" if _font_has_variant(value, bold=True)   else "disabled"
        state_italic = "normal" if _font_has_variant(value, italic=True) else "disabled"
        w["bold_check"].configure(state=state_bold)
        w["italic_check"].configure(state=state_italic)

    def on_style_preset_changed(name: str) -> None:
        presets = app.settings.get_style_presets()
        style = presets.get(name)
        if style:
            apply_text_style(w, style, _text_color, _outline_color)
            app.settings.set("active_subtitle_style", name)

    def _refresh_style_preset_list(select: str | None = None) -> None:
        presets = app.settings.get_style_presets()
        keys = list(presets.keys())
        w["style_preset"].configure(values=keys)
        if select and select in keys:
            w["style_preset"].set(select)
        elif keys:
            w["style_preset"].set(keys[0])

    def on_import_style() -> None:
        if not app.connected:
            w["status"].configure(text="Not connected to DaVinci Resolve.", text_color="#ff6b6b")
            return

        def _apply_style(style: dict) -> None:
            apply_text_style(w, style, _text_color, _outline_color)

        from src.ui._subtitles_import import import_style_thread
        threading.Thread(
            target=import_style_thread,
            args=(app, set_status, _ui, _apply_style),
            daemon=True,
        ).start()

    return {
        "on_whisper_model_changed": on_whisper_model_changed,
        "on_generate": on_generate,
        "on_create_track": on_create_track,
        "on_export_srt": on_export_srt,
        "on_export_txt": on_export_txt,
        "on_preset_changed": on_preset_changed,
        "on_font_size": on_font_size,
        "on_outline_width": on_outline_width,
        "pick_color": _pick_color,
        "on_outline_toggle": on_outline_toggle,
        "on_font_changed": on_font_changed,
        "on_style_preset_changed": on_style_preset_changed,
        "refresh_style_preset_list": _refresh_style_preset_list,
        "on_import_style": on_import_style,
    }
