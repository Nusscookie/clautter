"""UI builder and pace preset data for the Pace Control tab.

Extracted from pace_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations

from src.constants import COLORS
from typing import Any

import customtkinter as ctk

_PACE_PRESETS = {
    1:  {"threshold_db": -55, "min_silence_ms": 1500, "label": "Very Slow",
         "desc": "Documentary / cinematic — only remove very long pauses"},
    2:  {"threshold_db": -50, "min_silence_ms": 1200, "label": "Slow",
         "desc": "Long-form podcast / interview style"},
    3:  {"threshold_db": -45, "min_silence_ms": 900,  "label": "Relaxed",
         "desc": "Calm YouTube tutorial"},
    4:  {"threshold_db": -40, "min_silence_ms": 600,  "label": "Moderate",
         "desc": "Standard talking-head"},
    5:  {"threshold_db": -35, "min_silence_ms": 350,  "label": "YouTube",
         "desc": "Standard YouTube pacing — best all-round starting point"},
    6:  {"threshold_db": -33, "min_silence_ms": 280,  "label": "Crisp",
         "desc": "Tight YouTube / educational content"},
    7:  {"threshold_db": -30, "min_silence_ms": 220,  "label": "Snappy",
         "desc": "High-energy YouTube / commentary"},
    8:  {"threshold_db": -28, "min_silence_ms": 160,  "label": "Fast",
         "desc": "Instagram Reels / short-form"},
    9:  {"threshold_db": -25, "min_silence_ms": 120,  "label": "Very Fast",
         "desc": "TikTok-style aggressive cuts"},
    10: {"threshold_db": -22, "min_silence_ms": 80,   "label": "TikTok / Reels",
         "desc": "Maximum energy — every breath removed"},
}
_WPM_ESTIMATE  = {1: 100, 2: 115, 3: 125, 4: 135, 5: 145, 6: 155, 7: 165, 8: 175, 9: 185, 10: 200}
_RETENTION_EST = {1: 62,  2: 65,  3: 68,  4: 72,  5: 77,  6: 80,  7: 83,  8: 85,  9: 87,  10: 89}


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="PACE CONTROL  —  One slider for editing intensity",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    card = ctk.CTkFrame(parent, fg_color=COLORS.BG_CARD, corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    slider_row = ctk.CTkFrame(card, fg_color="transparent")
    slider_row.pack(fill="x", padx=12, pady=(12, 4))
    slider_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(slider_row, text="Slow", text_color=COLORS.TEXT_DIM).grid(row=0, column=0, padx=(0, 8))

    w["slider"] = ctk.CTkSlider(slider_row, from_=1, to=10, number_of_steps=9)
    w["slider"].set(5)
    w["slider"].grid(row=0, column=1, sticky="ew")

    ctk.CTkLabel(slider_row, text="Fast", text_color=COLORS.TEXT_DIM).grid(row=0, column=2, padx=(8, 0))

    info_row = ctk.CTkFrame(card, fg_color="transparent")
    info_row.pack(fill="x", padx=12, pady=(4, 12))

    w["level_lbl"] = ctk.CTkLabel(info_row, text="5",
                                   font=ctk.CTkFont(size=36, weight="bold"),
                                   text_color=COLORS.BRAND_PRIMARY, width=56)
    w["level_lbl"].pack(side="left")

    desc_frame = ctk.CTkFrame(info_row, fg_color="transparent")
    desc_frame.pack(side="left", padx=8, fill="x", expand=True)

    w["pace_label"] = ctk.CTkLabel(desc_frame, text="YouTube",
                                    font=ctk.CTkFont(size=16, weight="bold"),
                                    text_color=COLORS.TEXT_PRIMARY, anchor="w")
    w["pace_label"].pack(fill="x")

    w["pace_desc"] = ctk.CTkLabel(desc_frame,
                                   text="Standard YouTube pacing — best all-round starting point",
                                   font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_MUTED, anchor="w",
                                   wraplength=600)
    w["pace_desc"].pack(fill="x")

    params_card = ctk.CTkFrame(parent, fg_color=COLORS.BG_CARD, corner_radius=6)
    params_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(params_card, text="AUTO-ADJUSTED PARAMETERS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=COLORS.TEXT_DIM).pack(anchor="w", padx=10, pady=(8, 4))

    params_row = ctk.CTkFrame(params_card, fg_color="transparent")
    params_row.pack(fill="x", padx=10, pady=(0, 10))
    params_row.grid_columnconfigure((0, 1), weight=1)

    w["thresh_val"] = _mini_stat(params_row, "Threshold", "-35 dB", COLORS.BRAND_PRIMARY)
    w["thresh_val"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["dur_val"] = _mini_stat(params_row, "Min Silence", "350 ms", COLORS.WARNING)
    w["dur_val"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    est_row = ctk.CTkFrame(parent, fg_color="transparent")
    est_row.pack(fill="x", padx=10, pady=4)
    est_row.grid_columnconfigure((0, 1), weight=1)

    w["wpm_val"] = _mini_stat(est_row, "Est. Words Per Minute", "~145 WPM", COLORS.SUCCESS,
                               bg=COLORS.BG_CARD)
    w["wpm_val"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["retention_val"] = _mini_stat(est_row, "Est. Viewer Retention", "~77%", COLORS.BRAND_PRIMARY,
                                     bg=COLORS.BG_CARD)
    w["retention_val"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    w["apply_btn"] = ctk.CTkButton(
        parent,
        text="Apply Pace  (runs Smart Cuts with these settings)",
        fg_color=COLORS.BTN_PRIMARY_BG, hover_color=COLORS.BTN_PRIMARY_HOVER,
        font=ctk.CTkFont(size=13, weight="bold"),
        height=36,
    )
    w["apply_btn"].pack(fill="x", padx=10, pady=(8, 4))

    w["status"] = ctk.CTkLabel(
        parent, text="Adjust slider, then click Apply Pace.",
        font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_MUTED, anchor="w")
    w["status"].pack(fill="x", padx=12, pady=(0, 12))

    parent._w = w


def _mini_stat(parent: Any, label: str, default: str, color: str,
               bg: str = COLORS.BG_CARD) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=20, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color=COLORS.TEXT_DIM).pack(pady=(0, 8))
    card._val = val
    return card
