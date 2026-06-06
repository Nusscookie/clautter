"""Subtitles tab — ElevenLabs or local Whisper STT + subtitle track creation."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.ui._subtitles_build import (
    build_action_buttons, build_provider_slot, build_settings_row,
    build_style_controls, build_text_style_card, build_transcript_panel,
)
from src.ui._subtitles_data import (
    LANG_CODES, PRESET_DEFAULTS, STYLE_PRESETS, WHISPER_MODEL_MAP, WHISPER_MODELS,
)
from src.ui._subtitles_import import import_style_thread
from src.ui._subtitles_style import apply_text_style, get_style_overrides, get_text_style
from src.ui._subtitles_workers import create_track_thread, generate_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SUBTITLES  —  Generate captions via Speech-to-Text",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    build_provider_slot(parent, w)
    build_settings_row(parent, w)
    build_style_controls(parent, w)
    build_text_style_card(parent, w)
    build_action_buttons(parent, w)
    build_transcript_panel(parent, w)

    parent._w = w


def _unique_name(project: Any, base: str) -> str:
    try:
        existing = {
            project.GetTimelineByIndex(i + 1).GetName()
            for i in range(project.GetTimelineCount())
        }
    except Exception:
        existing = set()
    name = base
    i = 2
    while name in existing:
        name = f"{base}_{i}"
        i += 1
    return name


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "words": [],
        "srt_content": "",
        "srt_path": "",
        "timeline_choice": ("new", None),
        "words_are_remapped": False,
    }

    _text_color:      list[str] = ["#FFFFFF"]
    _outline_color:   list[str] = ["#000000"]
    _highlight_color: list[str] = ["#FFFF00"]

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(value: float, visible: bool = True) -> None:
        def _apply() -> None:
            if visible:
                w["progress"].pack(in_=w["progress_frame"], fill="x")
                w["progress"].set(value / 100.0)
            else:
                w["progress"].pack_forget()
        _ui(_apply)

    def set_btn(name: str, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        _ui(lambda: w[name].configure(state=state))

    # ── Provider toggle ──
    def on_provider_changed(value: str) -> None:
        app.settings.set("stt_provider", value)
        if value == "ElevenLabs":
            w["whisper_card"].pack_forget()
            w["api_card"].pack(fill="x", padx=10, pady=4)
        else:
            w["api_card"].pack_forget()
            w["whisper_card"].pack(fill="x", padx=10, pady=4)

    # ── Load saved state ──
    saved_key = app.settings.api_key
    if saved_key:
        w["api_key"].insert(0, saved_key)
        w["key_status"].configure(text="API key loaded from settings.")

    saved_preset = app.settings.get("subtitle_preset", "YouTube")
    if saved_preset in STYLE_PRESETS:
        w["preset"].set(saved_preset)

    saved_model = app.settings.get("whisper_model", "Base")
    if saved_model in WHISPER_MODELS:
        w["whisper_model"].set(saved_model)

    def _check_cuda() -> None:
        try:
            import ctranslate2  # type: ignore
            device = "CUDA" if "cuda" in ctranslate2.get_supported_compute_types("cuda") else "CPU"
        except Exception:
            device = "CPU"
        _ui(lambda: w["whisper_device_label"].configure(text=device))
    threading.Thread(target=_check_cuda, daemon=True).start()

    # ── Callbacks ──
    def on_save_key() -> None:
        key = w["api_key"].get().strip()
        if key:
            app.settings.api_key = key
            w["key_status"].configure(text="API key saved.")
        else:
            w["key_status"].configure(text="Key is empty — not saved.")

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
            from src.ui.timeline_dialog import show_timeline_dialog
            choice = show_timeline_dialog(frame, app.project)
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", "#ff6b6b")
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice
        _transcript_text = w["transcript"].get("0.0", "end").strip()
        _style      = get_style_overrides(w)
        _preset     = w["preset"].get()
        _text_style = get_text_style(w, _text_color, _outline_color, _highlight_color)
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
        wpl, lpb, caps, hcol = PRESET_DEFAULTS.get(value, (7, 2, False, "#FFFF00"))
        w["wpl_slider"].set(wpl)
        w["wpl_label"].configure(text=str(wpl))
        w["lpb_slider"].set(lpb)
        w["lpb_label"].configure(text=str(lpb))
        if caps:
            w["caps_check"].select()
        else:
            w["caps_check"].deselect()
        _highlight_color[0] = hcol
        w["highlight_color_btn"].configure(fg_color=hcol, hover_color=hcol)

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
            apply_text_style(w, style, _text_color, _outline_color, _highlight_color)
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
            apply_text_style(w, style, _text_color, _outline_color, _highlight_color)

        threading.Thread(
            target=import_style_thread,
            args=(app, set_status, _ui, _apply_style),
            daemon=True,
        ).start()

    # ── Wire up ──
    w["save_key_btn"].configure(command=on_save_key)
    w["generate_btn"].configure(command=on_generate)
    w["create_track_btn"].configure(command=on_create_track)
    w["export_srt_btn"].configure(command=on_export_srt)
    w["export_txt_btn"].configure(command=on_export_txt)
    w["preset"].configure(command=on_preset_changed)
    w["provider"].configure(command=on_provider_changed)
    w["whisper_model"].configure(command=on_whisper_model_changed)
    w["wpl_slider"].configure(command=lambda v: w["wpl_label"].configure(text=str(int(v))))
    w["lpb_slider"].configure(command=lambda v: w["lpb_label"].configure(text=str(int(v))))
    w["font_size_slider"].configure(command=on_font_size)
    w["outline_width_slider"].configure(command=on_outline_width)
    w["text_color_btn"].configure(
        command=lambda: _pick_color(_text_color, "text_color_btn", "Choose Text Color"))
    w["outline_color_btn"].configure(
        command=lambda: _pick_color(_outline_color, "outline_color_btn", "Choose Outline Color"))
    w["highlight_color_btn"].configure(
        command=lambda: _pick_color(_highlight_color, "highlight_color_btn", "Choose Highlight Color"))
    w["style_preset"].configure(command=on_style_preset_changed)
    w["style_import_btn"].configure(command=on_import_style)
    w["font_family"].configure(command=on_font_changed)
    w["outline_enabled_check"].configure(command=on_outline_toggle)

    # Apply saved settings
    on_preset_changed(w["preset"].get())
    saved_provider = app.settings.get("stt_provider", "ElevenLabs")
    if saved_provider in ("ElevenLabs", "Local Whisper"):
        w["provider"].set(saved_provider)
        on_provider_changed(saved_provider)

    _refresh_style_preset_list()
    active_style = app.settings.get("active_subtitle_style", "YouTube")
    presets = app.settings.get_style_presets()
    if active_style in presets:
        w["style_preset"].set(active_style)
    on_style_preset_changed(w["style_preset"].get())
    on_font_changed(w["font_family"].get())
    on_outline_toggle()
