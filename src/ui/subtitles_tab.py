"""Subtitles tab — ElevenLabs or local Whisper STT + subtitle track creation."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)

_LANGUAGES = [
    ("Auto-detect", ""), ("English", "en"), ("German", "de"), ("French", "fr"),
    ("Spanish", "es"), ("Italian", "it"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Dutch", "nl"), ("Swedish", "sv"),
    ("Norwegian", "no"), ("Danish", "da"), ("Mandarin (Simplified)", "zh"),
]
_LANG_LABELS = [l for l, _ in _LANGUAGES]
_LANG_CODES  = {l: c for l, c in _LANGUAGES}

_PRESETS = ["YouTube", "Standard", "TikTok", "Alex Hormozi Style"]

_FONT_FAMILIES = [
    "Open Sans", "Arial", "Calibri", "Georgia", "Impact",
    "Montserrat", "Roboto", "Times New Roman", "Trebuchet MS", "Verdana",
]

_WHISPER_MODELS = ["Tiny (fast)", "Base", "Small", "Medium", "Large v2", "Large v3"]
_WHISPER_MODEL_MAP = {
    "Tiny (fast)": "tiny",
    "Base": "base",
    "Small": "small",
    "Medium": "medium",
    "Large v2": "large-v2",
    "Large v3": "large-v3",
}


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SUBTITLES  —  Generate captions via Speech-to-Text",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Provider selector ──
    w["provider"] = ctk.CTkSegmentedButton(
        parent,
        values=["ElevenLabs", "Local Whisper"],
        font=ctk.CTkFont(size=11),
    )
    w["provider"].set("ElevenLabs")
    w["provider"].pack(fill="x", padx=10, pady=(0, 4))

    # Slot frame: holds either api_card or whisper_card (never both at once)
    _slot = ctk.CTkFrame(parent, fg_color="transparent")
    _slot.pack(fill="x")
    w["_slot"] = _slot

    # ── ElevenLabs API card ──
    w["api_card"] = ctk.CTkFrame(_slot, fg_color="#2a2a2a", corner_radius=6)
    w["api_card"].pack(fill="x", padx=10, pady=4)  # visible by default

    ctk.CTkLabel(w["api_card"], text="ELEVENLABS API",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    key_row = ctk.CTkFrame(w["api_card"], fg_color="transparent")
    key_row.pack(fill="x", padx=10, pady=(0, 4))
    key_row.grid_columnconfigure(0, weight=1)

    w["api_key"] = ctk.CTkEntry(key_row, placeholder_text="Enter ElevenLabs API key...",
                                 show="*")
    w["api_key"].grid(row=0, column=0, sticky="ew", padx=(0, 6))

    w["save_key_btn"] = ctk.CTkButton(key_row, text="Save", width=70)
    w["save_key_btn"].grid(row=0, column=1)

    w["key_status"] = ctk.CTkLabel(w["api_card"], text="", font=ctk.CTkFont(size=10),
                                    text_color="#aaaaaa", anchor="w")
    w["key_status"].pack(fill="x", padx=10, pady=(0, 8))

    # ── Local Whisper card (hidden by default) ──
    w["whisper_card"] = ctk.CTkFrame(_slot, fg_color="#2a2a2a", corner_radius=6)
    # not packed initially; on_provider_changed will show it when selected

    ctk.CTkLabel(w["whisper_card"], text="LOCAL WHISPER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    whisper_row = ctk.CTkFrame(w["whisper_card"], fg_color="transparent")
    whisper_row.pack(fill="x", padx=10, pady=(0, 4))
    whisper_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(whisper_row, text="Model",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=60, anchor="w").grid(row=0, column=0, sticky="w")

    w["whisper_model"] = ctk.CTkComboBox(whisper_row, values=_WHISPER_MODELS, state="readonly")
    w["whisper_model"].set("Base")
    w["whisper_model"].grid(row=0, column=1, sticky="ew", padx=(8, 8))

    w["whisper_device_label"] = ctk.CTkLabel(whisper_row, text="CPU",
                                              font=ctk.CTkFont(size=10),
                                              text_color="#4fc3f7", width=40, anchor="e")
    w["whisper_device_label"].grid(row=0, column=2, sticky="e")

    ctk.CTkLabel(
        w["whisper_card"],
        text="First run downloads the model automatically (~74 MB for Base).",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 8))

    # ── Settings row (language + preset) ──
    settings_row = ctk.CTkFrame(parent, fg_color="transparent")
    settings_row.pack(fill="x", padx=10, pady=4)
    settings_row.grid_columnconfigure((0, 1), weight=1)

    lang_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    lang_frame.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    ctk.CTkLabel(lang_frame, text="Language",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["language"] = ctk.CTkComboBox(lang_frame, values=_LANG_LABELS, state="readonly")
    w["language"].set("Auto-detect")
    w["language"].pack(fill="x")

    preset_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    preset_frame.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    ctk.CTkLabel(preset_frame, text="Style Preset",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["preset"] = ctk.CTkComboBox(preset_frame, values=_PRESETS, state="readonly")
    w["preset"].set("YouTube")
    w["preset"].pack(fill="x")

    # ── Style controls ──
    style_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    style_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(style_card, text="STYLE CONTROLS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    wpl_row = ctk.CTkFrame(style_card, fg_color="transparent")
    wpl_row.pack(fill="x", padx=10, pady=(0, 4))
    wpl_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(wpl_row, text="Words per line",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=120, anchor="w").grid(row=0, column=0, sticky="w")
    w["wpl_slider"] = ctk.CTkSlider(wpl_row, from_=1, to=12, number_of_steps=11)
    w["wpl_slider"].set(7)
    w["wpl_slider"].grid(row=0, column=1, sticky="ew", padx=(8, 8))
    w["wpl_label"] = ctk.CTkLabel(wpl_row, text="7",
                                   font=ctk.CTkFont(size=11), text_color="#4fc3f7",
                                   width=24, anchor="e")
    w["wpl_label"].grid(row=0, column=2, sticky="e")

    lpb_row = ctk.CTkFrame(style_card, fg_color="transparent")
    lpb_row.pack(fill="x", padx=10, pady=(0, 4))
    lpb_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(lpb_row, text="Lines per block",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=120, anchor="w").grid(row=0, column=0, sticky="w")
    w["lpb_slider"] = ctk.CTkSlider(lpb_row, from_=1, to=3, number_of_steps=2)
    w["lpb_slider"].set(2)
    w["lpb_slider"].grid(row=0, column=1, sticky="ew", padx=(8, 8))
    w["lpb_label"] = ctk.CTkLabel(lpb_row, text="2",
                                   font=ctk.CTkFont(size=11), text_color="#4fc3f7",
                                   width=24, anchor="e")
    w["lpb_label"].grid(row=0, column=2, sticky="e")

    w["caps_check"] = ctk.CTkCheckBox(style_card, text="ALL CAPS",
                                       font=ctk.CTkFont(size=11))
    w["caps_check"].pack(anchor="w", padx=10, pady=(0, 8))

    # ── Text Style card ──
    ts_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    ts_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(ts_card, text="TEXT STYLE",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    preset_row = ctk.CTkFrame(ts_card, fg_color="transparent")
    preset_row.pack(fill="x", padx=10, pady=(0, 4))
    preset_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(preset_row, text="Preset",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=60, anchor="w").grid(row=0, column=0, sticky="w")
    w["style_preset"] = ctk.CTkComboBox(preset_row, state="readonly")
    w["style_preset"].grid(row=0, column=1, sticky="ew", padx=(8, 8))
    w["style_import_btn"] = ctk.CTkButton(
        preset_row, text="Import from Resolve", width=148,
        fg_color="#2a2a2a", hover_color="#3a3a3a",
        border_width=1, border_color="#555555",
    )
    w["style_import_btn"].grid(row=0, column=2)

    ctk.CTkFrame(ts_card, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)

    font_row = ctk.CTkFrame(ts_card, fg_color="transparent")
    font_row.pack(fill="x", padx=10, pady=(0, 4))
    font_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(font_row, text="Font",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=60, anchor="w").grid(row=0, column=0, sticky="w")
    w["font_family"] = ctk.CTkComboBox(font_row, values=_FONT_FAMILIES)
    w["font_family"].set("Open Sans")
    w["font_family"].grid(row=0, column=1, sticky="ew", padx=(8, 8))
    ctk.CTkLabel(font_row, text="Size",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=30, anchor="e").grid(row=0, column=2, padx=(0, 6))
    w["font_size_slider"] = ctk.CTkSlider(font_row, from_=16, to=72,
                                           number_of_steps=56, width=90)
    w["font_size_slider"].set(36)
    w["font_size_slider"].grid(row=0, column=3, padx=(0, 6))
    w["font_size_lbl"] = ctk.CTkLabel(font_row, text="36",
                                       font=ctk.CTkFont(size=11), text_color="#4fc3f7",
                                       width=28, anchor="w")
    w["font_size_lbl"].grid(row=0, column=4)

    check_row = ctk.CTkFrame(ts_card, fg_color="transparent")
    check_row.pack(fill="x", padx=10, pady=(0, 4))
    w["bold_check"] = ctk.CTkCheckBox(check_row, text="Bold",
                                       font=ctk.CTkFont(size=11))
    w["bold_check"].pack(side="left", padx=(0, 14))
    w["italic_check"] = ctk.CTkCheckBox(check_row, text="Italic",
                                         font=ctk.CTkFont(size=11))
    w["italic_check"].pack(side="left", padx=(0, 14))
    w["underline_check"] = ctk.CTkCheckBox(check_row, text="Underline",
                                            font=ctk.CTkFont(size=11))
    w["underline_check"].pack(side="left", padx=(0, 14))
    w["shadow_check"] = ctk.CTkCheckBox(check_row, text="Shadow",
                                         font=ctk.CTkFont(size=11))
    w["shadow_check"].pack(side="left")

    color_row = ctk.CTkFrame(ts_card, fg_color="transparent")
    color_row.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkLabel(color_row, text="Text",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa").pack(side="left", padx=(0, 4))
    w["text_color_btn"] = ctk.CTkButton(
        color_row, text="", width=36, height=26, corner_radius=4,
        fg_color="#FFFFFF", hover_color="#FFFFFF",
        border_width=2, border_color="#555555",
    )
    w["text_color_btn"].pack(side="left", padx=(0, 16))
    w["outline_enabled_check"] = ctk.CTkCheckBox(
        color_row, text="Outline",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa",
        width=20,
    )
    w["outline_enabled_check"].select()
    w["outline_enabled_check"].pack(side="left", padx=(0, 6))
    w["outline_color_btn"] = ctk.CTkButton(
        color_row, text="", width=36, height=26, corner_radius=4,
        fg_color="#000000", hover_color="#000000",
        border_width=2, border_color="#555555",
    )
    w["outline_color_btn"].pack(side="left", padx=(0, 16))
    ctk.CTkLabel(color_row, text="Outline Width",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa").pack(side="left", padx=(0, 6))
    w["outline_width_slider"] = ctk.CTkSlider(
        color_row, from_=0, to=6, number_of_steps=6, width=90)
    w["outline_width_slider"].set(3)
    w["outline_width_slider"].pack(side="left", padx=(0, 6))
    w["outline_width_lbl"] = ctk.CTkLabel(
        color_row, text="3",
        font=ctk.CTkFont(size=11), text_color="#4fc3f7",
        width=20, anchor="w")
    w["outline_width_lbl"].pack(side="left")

    ctk.CTkLabel(color_row, text="Highlight",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa").pack(side="left", padx=(16, 4))
    w["highlight_color_btn"] = ctk.CTkButton(
        color_row, text="", width=36, height=26, corner_radius=4,
        fg_color="#FFFF00", hover_color="#FFFF00",
        border_width=2, border_color="#555555",
    )
    w["highlight_color_btn"].pack(side="left")

    # ── Action buttons ──
    btn_row1 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row1.pack(fill="x", padx=10, pady=(6, 2))
    btn_row1.grid_columnconfigure((0, 1), weight=1)

    w["generate_btn"] = ctk.CTkButton(btn_row1, text="Generate Transcript",
                                       fg_color="#1565c0", hover_color="#1976d2",
                                       font=ctk.CTkFont(weight="bold"))
    w["generate_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["create_track_btn"] = ctk.CTkButton(btn_row1, text="Create Subtitle Track",
                                           fg_color="#2a2a2a", hover_color="#3a3a3a",
                                           state="disabled")
    w["create_track_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    btn_row2 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row2.pack(fill="x", padx=10, pady=2)
    btn_row2.grid_columnconfigure((0, 1), weight=1)

    w["export_srt_btn"] = ctk.CTkButton(btn_row2, text="Export SRT",
                                         fg_color="#2a2a2a", hover_color="#3a3a3a",
                                         state="disabled")
    w["export_srt_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["export_txt_btn"] = ctk.CTkButton(btn_row2, text="Export TXT",
                                         fg_color="#2a2a2a", hover_color="#3a3a3a",
                                         state="disabled")
    w["export_txt_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    # ── Progress ──
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(4, 0))

    w["status"] = ctk.CTkLabel(
        parent, text="Select provider and click Generate Transcript.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    _divider(parent)

    # ── Transcript panel ──
    ctk.CTkLabel(parent, text="TRANSCRIPT  (editable)",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["transcript"] = ctk.CTkTextbox(parent, height=180,
                                      font=ctk.CTkFont(size=12))
    w["transcript"].pack(fill="x", padx=10, pady=(0, 12))
    w["transcript"].insert("0.0", "Transcript will appear here after generation...")

    parent._w = w


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


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


_PRESET_DEFAULTS: dict[str, tuple[int, int, bool, str]] = {
    "Standard":           (8, 2, False, "#FFFF00"),
    "YouTube":            (7, 2, False, "#FFFF00"),
    "TikTok":             (5, 1, True,  "#FF0000"),
    "Alex Hormozi Style": (3, 1, True,  "#FFFF00"),
}


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "words": [],
        "srt_content": "",
        "srt_path": "",
        "timeline_choice": ("new", None),
    }

    # Mutable closure vars for color picker state (list wrapper allows reassignment)
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

    def _get_style_overrides() -> dict:
        return {
            "words_per_line":  int(w["wpl_slider"].get()),
            "lines_per_block": int(w["lpb_slider"].get()),
            "uppercase":       w["caps_check"].get() == 1,
        }

    def _get_text_style() -> dict:
        _outline_on = w["outline_enabled_check"].get() == 1
        return {
            "font_family":     w["font_family"].get(),
            "font_size":       int(w["font_size_slider"].get()),
            "bold":            w["bold_check"].get() == 1,
            "italic":          w["italic_check"].get() == 1,
            "underline":       w["underline_check"].get() == 1,
            "primary_color":   _text_color[0],
            "outline_enabled": _outline_on,
            "outline_color":   _outline_color[0],
            "outline_width":   int(w["outline_width_slider"].get()) if _outline_on else 0,
            "shadow":          1 if w["shadow_check"].get() == 1 else 0,
            "highlight_color": _highlight_color[0],
        }

    def _apply_text_style(style: dict) -> None:
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
        _text_color[0]    = tc
        _outline_color[0] = oc
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
        if "highlight_color" in style:
            hc = style["highlight_color"]
            _highlight_color[0] = hc
            w["highlight_color_btn"].configure(fg_color=hc, hover_color=hc)

    def on_wpl(val: float) -> None:
        w["wpl_label"].configure(text=str(int(val)))

    def on_lpb(val: float) -> None:
        w["lpb_label"].configure(text=str(int(val)))

    w["wpl_slider"].configure(command=on_wpl)
    w["lpb_slider"].configure(command=on_lpb)

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
    if saved_preset in _PRESETS:
        w["preset"].set(saved_preset)

    saved_model = app.settings.get("whisper_model", "Base")
    if saved_model in _WHISPER_MODELS:
        w["whisper_model"].set(saved_model)

    # Check for CUDA (informational label only)
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

    def _generate_thread() -> None:
        try:
            from src.utils.resolve_api import get_clip_file_path

            set_btn("generate_btn", False)
            set_progress(0, True)
            set_status("Checking configuration...")

            provider = w["provider"].get()
            lang_label = w["language"].get()
            lang_code = _LANG_CODES.get(lang_label, "")

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                set_status("No clips found on Video Track 1.", "#ff6b6b")
                set_progress(0, False)
                return

            file_path = get_clip_file_path(clips[0])
            if not file_path:
                set_status("Could not get media file path from first clip.", "#ff6b6b")
                set_progress(0, False)
                return

            set_progress(20)

            if provider == "Local Whisper":
                from src.subtitles.whisper_client import WhisperClient
                model_label = w["whisper_model"].get()
                model_name = _WHISPER_MODEL_MAP.get(model_label, "base")
                set_status(
                    f"Loading Whisper {model_label} — first run downloads model automatically..."
                )
                client = WhisperClient(model_name)
                words = client.transcribe(file_path, language=lang_code)
            else:
                from src.subtitles.elevenlabs import ElevenLabsClient
                api_key = w["api_key"].get().strip()
                if not api_key:
                    set_status("API key is empty. Enter your ElevenLabs key first.", "#ff6b6b")
                    set_progress(0, False)
                    return
                set_status(f"Sending to ElevenLabs STT: {file_path.split(chr(92))[-1]}")
                client = ElevenLabsClient(api_key)
                words = client.transcribe(file_path, language=lang_code)

            set_progress(60)

            _state["words"] = words
            app.transcript = words

            preview = " ".join(w2["word"] for w2 in words if w2.get("type", "word") == "word")
            _ui(lambda: (
                w["transcript"].delete("0.0", "end"),
                w["transcript"].insert("0.0", preview),
            ))

            from src.subtitles.generator import words_to_srt
            preset_name = w["preset"].get()
            srt = words_to_srt(words, preset_name, **_get_style_overrides())
            _state["srt_content"] = srt

            set_progress(90)

            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                suffix=".srt", delete=False,
                mode="w", encoding="utf-8", prefix="clutter_"
            )
            tmp.write(srt)
            tmp.close()
            _state["srt_path"] = tmp.name

            set_progress(100)
            word_count = len([w2 for w2 in words if w2.get("type", "word") == "word"])
            set_status(
                f"Transcript ready: {word_count} words. "
                "Click 'Create Subtitle Track' to add to timeline.",
                "#66bb6a",
            )
            set_btn("create_track_btn", True)
            set_btn("export_srt_btn", True)
            set_btn("export_txt_btn", True)
            app.settings.add_stat("total_subtitles_generated", 1)
            set_progress(0, False)

        except Exception as e:
            log.error("Generate thread error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
            set_progress(0, False)
        finally:
            set_btn("generate_btn", True)

    def _create_track_thread(
        transcript_text: str,
        style_overrides: dict,
        preset_name: str,
        text_style: dict,
    ) -> None:
        try:
            from src.subtitles.generator import import_srt_to_timeline, remap_words_to_timeline
            import tempfile as _tempfile

            set_btn("create_track_btn", False)

            if not _state["words"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return

            # Merge textbox edits into word list (keeps timestamps, updates text).
            # transcript_text was captured on the main thread — thread-safe.
            _placeholder = "Transcript will appear here after generation..."
            _orig_words = [wd for wd in _state["words"] if wd.get("type", "word") == "word"]
            if transcript_text and transcript_text != _placeholder:
                _tokens = transcript_text.split()
                if len(_tokens) == len(_orig_words):
                    _tok_iter = iter(_tokens)
                    _words_src: list[Any] = [
                        {**wd, "word": next(_tok_iter)} if wd.get("type", "word") == "word" else wd
                        for wd in _state["words"]
                    ]
                    log.info("Applied %d transcript edits to subtitle words", len(_tokens))
                else:
                    if _orig_words:
                        t0   = _orig_words[0]["start_sec"]
                        t1   = _orig_words[-1]["end_sec"]
                        step = (t1 - t0) / max(len(_tokens), 1)
                        _words_src = [
                            {
                                "word": tok,
                                "start_sec": t0 + i * step,
                                "end_sec": t0 + (i + 1) * step,
                                "type": "word",
                            }
                            for i, tok in enumerate(_tokens)
                        ]
                        log.info(
                            "Word count changed (%d→%d) — using proportional timing fallback",
                            len(_orig_words), len(_tokens),
                        )
                        set_status(
                            f"Word count changed ({len(_orig_words)}→{len(_tokens)}) — timing approximated.",
                            "#ffa726",
                        )
                    else:
                        _words_src = _state["words"]
            else:
                _words_src = _state["words"]

            _mode, _target_tl = _state["timeline_choice"]
            if _mode == "existing" and _target_tl is not None:
                app.project.SetCurrentTimeline(_target_tl)
                app.refresh_timeline()
                set_status(f"Adding subtitle track to '{_target_tl.GetName()}'...")
            elif _mode == "new":
                if not app.timeline:
                    set_status("No active timeline. Open a timeline in Resolve first.", "#ff6b6b")
                    return
                set_status(f"Adding subtitle track to '{app.timeline.GetName()}'...")
            else:
                set_status("Adding subtitle track to current timeline...")

            # Remap word timestamps to the current (possibly cut) timeline.
            if app.timeline:
                try:
                    clips = app.get_video_clips(1)
                    tl_start = app.timeline.GetStartFrame()
                    remapped = remap_words_to_timeline(_words_src, clips, app.fps, tl_start)
                    log.info("Remapped %d words to current timeline", len(remapped))
                except Exception as _e:
                    log.warning("Word remap failed, using original timestamps: %s", _e)
                    remapped = [wd for wd in _words_src if wd.get("type", "word") == "word"]
            else:
                remapped = [wd for wd in _words_src if wd.get("type", "word") == "word"]

            # Primary path: Fusion Title clips on a video track (full styling + word highlight).
            from src.subtitles.generator import place_fusion_titles
            ok = place_fusion_titles(
                app.resolve, remapped, app.fps, app.timeline,
                text_style, preset_name, **style_overrides,
            )
            if not ok:
                # Fusion path failed (Resolve not connected, or Text+ not available).
                # Fall back to SRT on subtitle track — no custom styling but clips land.
                log.info("Fusion titles failed; falling back to SRT subtitle track")
                from src.subtitles.generator import words_to_srt
                _srt_tmp = _tempfile.NamedTemporaryFile(
                    suffix=".srt", delete=False, mode="w", encoding="utf-8",
                    prefix="clutter_fallback_",
                )
                _srt_tmp.write(words_to_srt(remapped, preset_name, **style_overrides))
                _srt_tmp.close()
                ok = import_srt_to_timeline(app.resolve, _srt_tmp.name, app.timeline)

            if ok:
                set_status("Subtitle track created.", "#66bb6a")
            else:
                set_status(
                    f"Could not auto-import. Drag file from Media Pool: {srt_path_for_import}",
                    "#ffa726",
                )
        except Exception as e:
            log.error("Create track error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            set_btn("create_track_btn", True)

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

    def on_generate() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_generate_thread, daemon=True).start()

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
        # Capture all widget state on the main thread before launching background thread.
        # CTkTextbox.get() and slider/checkbox reads hit the Tk C layer — not thread-safe.
        _transcript_text = w["transcript"].get("0.0", "end").strip()
        _style      = _get_style_overrides()
        _preset     = w["preset"].get()
        _text_style = _get_text_style()
        threading.Thread(
            target=_create_track_thread,
            args=(_transcript_text, _style, _preset, _text_style),
            daemon=True,
        ).start()

    def on_preset_changed(value: str) -> None:
        app.settings.set("subtitle_preset", value)
        wpl, lpb, caps, hcol = _PRESET_DEFAULTS.get(value, (7, 2, False, "#FFFF00"))
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

    # ── Text style handlers ──
    def on_font_size(val: float) -> None:
        w["font_size_lbl"].configure(text=str(int(val)))

    def on_outline_width(val: float) -> None:
        w["outline_width_lbl"].configure(text=str(int(val)))

    def on_text_color() -> None:
        import tkinter.colorchooser
        result = tkinter.colorchooser.askcolor(
            color=_text_color[0], title="Choose Text Color"
        )
        if result and result[1]:
            _text_color[0] = result[1].upper()
            w["text_color_btn"].configure(
                fg_color=_text_color[0], hover_color=_text_color[0])

    def on_outline_color() -> None:
        import tkinter.colorchooser
        result = tkinter.colorchooser.askcolor(
            color=_outline_color[0], title="Choose Outline Color"
        )
        if result and result[1]:
            _outline_color[0] = result[1].upper()
            w["outline_color_btn"].configure(
                fg_color=_outline_color[0], hover_color=_outline_color[0])

    def on_highlight_color() -> None:
        import tkinter.colorchooser
        result = tkinter.colorchooser.askcolor(
            color=_highlight_color[0], title="Choose Highlight Color"
        )
        if result and result[1]:
            _highlight_color[0] = result[1].upper()
            w["highlight_color_btn"].configure(
                fg_color=_highlight_color[0], hover_color=_highlight_color[0])

    def on_style_preset_changed(name: str) -> None:
        presets = app.settings.get_style_presets()
        style = presets.get(name)
        if style:
            _apply_text_style(style)
            app.settings.set("active_subtitle_style", name)

    def _refresh_style_preset_list(select: str | None = None) -> None:
        presets = app.settings.get_style_presets()
        keys = list(presets.keys())
        w["style_preset"].configure(values=keys)
        if select and select in keys:
            w["style_preset"].set(select)
        elif keys:
            w["style_preset"].set(keys[0])

    def _import_style_thread() -> None:
        try:
            if not app.timeline:
                set_status("No timeline — connect Resolve first.", "#ff6b6b")
                return
            item = app.timeline.GetCurrentVideoItem()

            if not item:
                # GetCurrentVideoItem only sees track 1 — scan all video tracks for any Fusion Title
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
                    "#ffa726",
                )
                return

            try:
                comp_count = item.GetFusionCompCount()
            except Exception:
                comp_count = 0
            if not comp_count:
                set_status("Selected clip has no Fusion composition.", "#ffa726")
                return

            comp = item.GetFusionCompByIndex(1)
            # Prefer inner TextPlus (FindToolByID searches inside macros).
            # AutoSubs macro wrapper only publishes a subset — border attrs not accessible.
            text_tool = comp.FindToolByID("TextPlus") or comp.FindTool("Template")
            if not text_tool:
                set_status(
                    "No Text+ tool in selected clip. Select a Fusion Title or Text+ generator.",
                    "#ffa726",
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

            # Style input ("Bold", "Italic", "Bold Italic", "Regular") is authoritative.
            # Bool inputs Bold/Italic apply a synthetic effect and don't reflect face selection.
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

            # Read outline width (Fusion BorderWidth is 0–1 range)
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
                    "Could not read style from clip. Check log for available inputs.", "#ffa726")
                return

            log.info("Imported style from Resolve clip: %s", style)
            _ui(lambda: _apply_text_style(style))
            set_status("Style imported from Fusion clip.", "#66bb6a")

        except Exception as e:
            log.error("Import style from Resolve: %s", e)
            set_status(f"Import error: {e}", "#ff6b6b")

    def on_import_style() -> None:
        if not app.connected:
            w["status"].configure(text="Not connected to DaVinci Resolve.", text_color="#ff6b6b")
            return
        threading.Thread(target=_import_style_thread, daemon=True).start()

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

    def on_outline_toggle() -> None:
        enabled = w["outline_enabled_check"].get() == 1
        state = "normal" if enabled else "disabled"
        w["outline_color_btn"].configure(state=state)
        w["outline_width_slider"].configure(state=state)

    # ── Wire up all callbacks ──
    w["save_key_btn"].configure(command=on_save_key)
    w["generate_btn"].configure(command=on_generate)
    w["create_track_btn"].configure(command=on_create_track)
    w["export_srt_btn"].configure(command=on_export_srt)
    w["export_txt_btn"].configure(command=on_export_txt)
    w["preset"].configure(command=on_preset_changed)
    w["provider"].configure(command=on_provider_changed)
    w["whisper_model"].configure(command=on_whisper_model_changed)
    w["font_size_slider"].configure(command=on_font_size)
    w["outline_width_slider"].configure(command=on_outline_width)
    w["text_color_btn"].configure(command=on_text_color)
    w["outline_color_btn"].configure(command=on_outline_color)
    w["highlight_color_btn"].configure(command=on_highlight_color)
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

    # Init text style from saved settings
    _refresh_style_preset_list()
    active_style = app.settings.get("active_subtitle_style", "YouTube")
    presets = app.settings.get_style_presets()
    if active_style in presets:
        w["style_preset"].set(active_style)
    on_style_preset_changed(w["style_preset"].get())
    on_font_changed(w["font_family"].get())
    on_outline_toggle()
