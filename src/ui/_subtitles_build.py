"""UI builder helpers for the Subtitles tab. Called from build() in subtitles_tab.py."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.ui._subtitles_data import (
    FONT_FAMILIES, LANG_LABELS, STYLE_PRESETS, WHISPER_MODELS,
)


def build_provider_slot(parent: Any, w: dict) -> None:
    """Provider toggle + ElevenLabs / Whisper cards."""
    w["provider"] = ctk.CTkSegmentedButton(
        parent,
        values=["ElevenLabs", "Local Whisper"],
        font=ctk.CTkFont(size=11),
    )
    w["provider"].set("ElevenLabs")
    w["provider"].pack(fill="x", padx=10, pady=(0, 4))

    _slot = ctk.CTkFrame(parent, fg_color="transparent")
    _slot.pack(fill="x")
    w["_slot"] = _slot

    # ElevenLabs card
    w["api_card"] = ctk.CTkFrame(_slot, fg_color="#2a2a2a", corner_radius=6)
    w["api_card"].pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(w["api_card"], text="ELEVENLABS API",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    key_row = ctk.CTkFrame(w["api_card"], fg_color="transparent")
    key_row.pack(fill="x", padx=10, pady=(0, 4))
    key_row.grid_columnconfigure(0, weight=1)

    w["api_key"] = ctk.CTkEntry(key_row, placeholder_text="Enter ElevenLabs API key...", show="*")
    w["api_key"].grid(row=0, column=0, sticky="ew", padx=(0, 6))
    w["save_key_btn"] = ctk.CTkButton(key_row, text="Save", width=70)
    w["save_key_btn"].grid(row=0, column=1)

    w["key_status"] = ctk.CTkLabel(w["api_card"], text="", font=ctk.CTkFont(size=10),
                                    text_color="#aaaaaa", anchor="w")
    w["key_status"].pack(fill="x", padx=10, pady=(0, 8))

    # Whisper card (hidden by default)
    w["whisper_card"] = ctk.CTkFrame(_slot, fg_color="#2a2a2a", corner_radius=6)

    ctk.CTkLabel(w["whisper_card"], text="LOCAL WHISPER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    whisper_row = ctk.CTkFrame(w["whisper_card"], fg_color="transparent")
    whisper_row.pack(fill="x", padx=10, pady=(0, 4))
    whisper_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(whisper_row, text="Model",
                 font=ctk.CTkFont(size=11), text_color="#aaaaaa",
                 width=60, anchor="w").grid(row=0, column=0, sticky="w")
    w["whisper_model"] = ctk.CTkComboBox(whisper_row, values=WHISPER_MODELS, state="readonly")
    w["whisper_model"].set("Base")
    w["whisper_model"].grid(row=0, column=1, sticky="ew", padx=(8, 8))
    w["whisper_device_label"] = ctk.CTkLabel(whisper_row, text="CPU",
                                              font=ctk.CTkFont(size=10),
                                              text_color="#4fc3f7", width=40, anchor="e")
    w["whisper_device_label"].grid(row=0, column=2, sticky="e")

    ctk.CTkLabel(
        w["whisper_card"],
        text="First run downloads the model automatically (~74 MB for Base).",
        font=ctk.CTkFont(size=10), text_color="#555555", anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 8))


def build_settings_row(parent: Any, w: dict) -> None:
    """Language + style preset dropdowns."""
    settings_row = ctk.CTkFrame(parent, fg_color="transparent")
    settings_row.pack(fill="x", padx=10, pady=4)
    settings_row.grid_columnconfigure((0, 1), weight=1)

    lang_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    lang_frame.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    ctk.CTkLabel(lang_frame, text="Language",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["language"] = ctk.CTkComboBox(lang_frame, values=LANG_LABELS, state="readonly")
    w["language"].set("Auto-detect")
    w["language"].pack(fill="x")

    preset_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    preset_frame.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    ctk.CTkLabel(preset_frame, text="Style Preset",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["preset"] = ctk.CTkComboBox(preset_frame, values=STYLE_PRESETS, state="readonly")
    w["preset"].set("YouTube")
    w["preset"].pack(fill="x")


def build_style_controls(parent: Any, w: dict) -> None:
    """Words-per-line, lines-per-block sliders + ALL CAPS checkbox."""
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


def build_text_style_card(parent: Any, w: dict) -> None:
    """Font family/size, bold/italic/underline/shadow, color pickers."""
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
    w["font_family"] = ctk.CTkComboBox(font_row, values=FONT_FAMILIES)
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
    for key, label in (("bold_check", "Bold"), ("italic_check", "Italic"),
                       ("underline_check", "Underline"), ("shadow_check", "Shadow")):
        w[key] = ctk.CTkCheckBox(check_row, text=label, font=ctk.CTkFont(size=11))
        w[key].pack(side="left", padx=(0, 14))

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
        color_row, text="Outline", font=ctk.CTkFont(size=11), text_color="#aaaaaa", width=20)
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
        color_row, text="3", font=ctk.CTkFont(size=11), text_color="#4fc3f7",
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


def build_action_buttons(parent: Any, w: dict) -> None:
    """Generate / Create Track / Export buttons."""
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


def build_transcript_panel(parent: Any, w: dict) -> None:
    """Progress bar, status label, and editable transcript textbox."""
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(4, 0))

    w["status"] = ctk.CTkLabel(
        parent, text="Select provider and click Generate Transcript.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)

    ctk.CTkLabel(parent, text="TRANSCRIPT  (editable)",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["transcript"] = ctk.CTkTextbox(parent, height=180, font=ctk.CTkFont(size=12))
    w["transcript"].pack(fill="x", padx=10, pady=(0, 12))
    w["transcript"].insert("0.0", "Transcript will appear here after generation...")
