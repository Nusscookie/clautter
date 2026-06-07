"""Subtitles tab — ElevenLabs or local Whisper STT + subtitle track creation."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.ui._subtitles_build import (
    build_action_buttons, build_provider_slot, build_settings_row,
    build_style_controls, build_text_style_card, build_transcript_panel,
)
from src.ui._subtitles_callbacks import make_callbacks
from src.ui._subtitles_data import STYLE_PRESETS, WHISPER_MODELS
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

    # ── Build callbacks ──
    cbs = make_callbacks(
        w, frame, app, _state,
        _text_color, _outline_color, _highlight_color,
        set_status, set_progress, set_btn, _ui,
    )

    # ── Wire up ──
    w["save_key_btn"].configure(command=cbs["on_save_key"])
    w["generate_btn"].configure(command=cbs["on_generate"])
    w["create_track_btn"].configure(command=cbs["on_create_track"])
    w["export_srt_btn"].configure(command=cbs["on_export_srt"])
    w["export_txt_btn"].configure(command=cbs["on_export_txt"])
    w["preset"].configure(command=cbs["on_preset_changed"])
    w["provider"].configure(command=on_provider_changed)
    w["whisper_model"].configure(command=cbs["on_whisper_model_changed"])
    w["wpl_slider"].configure(command=lambda v: w["wpl_label"].configure(text=str(int(v))))
    w["lpb_slider"].configure(command=lambda v: w["lpb_label"].configure(text=str(int(v))))
    w["font_size_slider"].configure(command=cbs["on_font_size"])
    w["outline_width_slider"].configure(command=cbs["on_outline_width"])
    w["vpos_slider"].configure(command=lambda v: w["vpos_lbl"].configure(text=f"{int(v)}%"))
    w["text_color_btn"].configure(
        command=lambda: cbs["pick_color"](_text_color, "text_color_btn", "Choose Text Color"))
    w["outline_color_btn"].configure(
        command=lambda: cbs["pick_color"](_outline_color, "outline_color_btn", "Choose Outline Color"))
    w["highlight_color_btn"].configure(
        command=lambda: cbs["pick_color"](_highlight_color, "highlight_color_btn", "Choose Highlight Color"))
    w["style_preset"].configure(command=cbs["on_style_preset_changed"])
    w["style_import_btn"].configure(command=cbs["on_import_style"])
    w["font_family"].configure(command=cbs["on_font_changed"])
    w["outline_enabled_check"].configure(command=cbs["on_outline_toggle"])

    # ── Apply saved settings ──
    cbs["on_preset_changed"](w["preset"].get())
    saved_provider = app.settings.get("stt_provider", "ElevenLabs")
    if saved_provider in ("ElevenLabs", "Local Whisper"):
        w["provider"].set(saved_provider)
        on_provider_changed(saved_provider)

    cbs["refresh_style_preset_list"]()
    active_style = app.settings.get("active_subtitle_style", "YouTube")
    presets = app.settings.get_style_presets()
    if active_style in presets:
        w["style_preset"].set(active_style)
    cbs["on_style_preset_changed"](w["style_preset"].get())
    cbs["on_font_changed"](w["font_family"].get())
    cbs["on_outline_toggle"]()
