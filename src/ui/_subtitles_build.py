"""UI builder helpers for the Subtitles tab. Called from build() in subtitles_tab.py.

Provider slot, style controls, and text-style card live in _subtitles_build_style.py.
"""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.constants import COLORS
from src.ui._subtitles_data import (
    LANG_LABELS, STYLE_PRESETS,
)
from src.ui._subtitles_build_style import (
    build_provider_slot,
    build_style_controls,
    build_text_style_card,
)

# Re-export so subtitles_tab.py import continues to work unchanged.
__all__ = [
    "build_provider_slot",
    "build_settings_row",
    "build_style_controls",
    "build_text_style_card",
    "build_action_buttons",
    "build_transcript_panel",
]


def build_settings_row(parent: Any, w: dict) -> None:
    """Language + style preset dropdowns."""
    settings_row = ctk.CTkFrame(parent, fg_color="transparent")
    settings_row.pack(fill="x", padx=10, pady=4)
    settings_row.grid_columnconfigure((0, 1), weight=1)

    lang_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    lang_frame.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    ctk.CTkLabel(lang_frame, text="Language",
                 font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_MUTED).pack(anchor="w")
    w["language"] = ctk.CTkComboBox(lang_frame, values=LANG_LABELS, state="readonly")
    w["language"].set("Auto-detect")
    w["language"].pack(fill="x")

    preset_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    preset_frame.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    ctk.CTkLabel(preset_frame, text="Style Preset",
                 font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_MUTED).pack(anchor="w")
    w["preset"] = ctk.CTkComboBox(preset_frame, values=STYLE_PRESETS, state="readonly")
    w["preset"].set("YouTube")
    w["preset"].pack(fill="x")


def build_action_buttons(parent: Any, w: dict) -> None:
    """Generate / Create Track / Export buttons."""
    btn_row1 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row1.pack(fill="x", padx=10, pady=(6, 2))
    btn_row1.grid_columnconfigure((0, 1), weight=1)

    w["generate_btn"] = ctk.CTkButton(btn_row1, text="Generate Transcript",
                                       fg_color=COLORS.BTN_PRIMARY_BG, hover_color=COLORS.BTN_PRIMARY_HOVER,
                                       font=ctk.CTkFont(weight="bold"))
    w["generate_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["create_track_btn"] = ctk.CTkButton(btn_row1, text="Create Subtitle Track",
                                           fg_color=COLORS.BG_CARD, hover_color=COLORS.BG_HOVER,
                                           state="disabled")
    w["create_track_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    btn_row2 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row2.pack(fill="x", padx=10, pady=2)
    btn_row2.grid_columnconfigure((0, 1), weight=1)

    w["export_srt_btn"] = ctk.CTkButton(btn_row2, text="Export SRT",
                                         fg_color=COLORS.BG_CARD, hover_color=COLORS.BG_HOVER,
                                         state="disabled")
    w["export_srt_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["export_txt_btn"] = ctk.CTkButton(btn_row2, text="Export TXT",
                                         fg_color=COLORS.BG_CARD, hover_color=COLORS.BG_HOVER,
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
        font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_MUTED, anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color=COLORS.SEPARATOR, corner_radius=0).pack(
        fill="x", padx=10, pady=4)

    ctk.CTkLabel(parent, text="TRANSCRIPT  (editable)",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=COLORS.TEXT_DIM).pack(anchor="w", padx=12, pady=(8, 4))

    w["transcript"] = ctk.CTkTextbox(parent, height=180, font=ctk.CTkFont(size=12))
    w["transcript"].pack(fill="x", padx=10, pady=(0, 12))
    w["transcript"].insert("0.0", "Transcript will appear here after generation...")
