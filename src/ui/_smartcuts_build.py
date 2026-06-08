"""UI builder for the Smart Cuts tab.

Extracted from smartcuts_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SMART CUTS  —  Remove silences from selected clips",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    pace_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    pace_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(pace_card, text="PACE PRESET",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    slider_row = ctk.CTkFrame(pace_card, fg_color="transparent")
    slider_row.pack(fill="x", padx=10, pady=(0, 4))
    slider_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(slider_row, text="Slow", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 8))
    w["pace_slider"] = ctk.CTkSlider(slider_row, from_=1, to=10, number_of_steps=9)
    w["pace_slider"].set(5)
    w["pace_slider"].grid(row=0, column=1, sticky="ew")
    ctk.CTkLabel(slider_row, text="Fast", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(8, 0))

    info_row = ctk.CTkFrame(pace_card, fg_color="transparent")
    info_row.pack(fill="x", padx=10, pady=(0, 10))

    w["pace_level_lbl"] = ctk.CTkLabel(info_row, text="5",
                                        font=ctk.CTkFont(size=22, weight="bold"),
                                        text_color="#D97757", width=36, anchor="w")
    w["pace_level_lbl"].pack(side="left")

    desc_col = ctk.CTkFrame(info_row, fg_color="transparent")
    desc_col.pack(side="left", padx=(6, 0), fill="x", expand=True)

    w["pace_name_lbl"] = ctk.CTkLabel(desc_col, text="YouTube",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       text_color="#ffffff", anchor="w")
    w["pace_name_lbl"].pack(fill="x")

    w["pace_desc_lbl"] = ctk.CTkLabel(desc_col,
                                       text="Standard YouTube pacing — best all-round starting point",
                                       font=ctk.CTkFont(size=10), text_color="#aaaaaa",
                                       anchor="w", wraplength=600)
    w["pace_desc_lbl"].pack(fill="x")

    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(card, text="DETECTION SETTINGS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    # Threshold container: holds one of two rows (swapped by setup on method change)
    threshold_container = ctk.CTkFrame(card, fg_color="transparent")
    threshold_container.pack(fill="x")

    threshold_row = ctk.CTkFrame(threshold_container, fg_color="transparent")
    threshold_row.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(threshold_row, text="Silence Threshold", anchor="w").grid(
        row=0, column=0, sticky="w", padx=10, pady=2)
    _thr_entry = ctk.CTkEntry(threshold_row, width=90, justify="center")
    _thr_entry.insert(0, "-35")
    _thr_entry.grid(row=0, column=1, padx=6)
    ctk.CTkLabel(threshold_row, text="dB", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(0, 10))
    w["threshold"] = _thr_entry
    w["threshold_row"] = threshold_row
    # Not packed here — setup() shows correct row based on saved method

    vad_row = ctk.CTkFrame(threshold_container, fg_color="transparent")
    vad_row.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(vad_row, text="VAD Sensitivity", anchor="w").grid(
        row=0, column=0, sticky="w", padx=10, pady=2)
    _vad_entry = ctk.CTkEntry(vad_row, width=90, justify="center")
    _vad_entry.insert(0, "0.50")
    _vad_entry.grid(row=0, column=1, padx=6)
    ctk.CTkLabel(vad_row, text="(0 – 1)", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(0, 10))
    w["vad_threshold"] = _vad_entry
    w["vad_threshold_row"] = vad_row
    # Not packed here — setup() shows correct row based on saved method

    w["min_dur"]   = _labeled_entry(card, "Min Silence Duration", "350", "ms")
    w["padding"]   = _labeled_entry(card, "Breathing Room (padding)", "120", "ms each side")

    ctk.CTkFrame(card, height=1, fg_color="#333333", corner_radius=0).pack(
        fill="x", padx=10, pady=(6, 2))
    w["retake_cb"] = ctk.CTkCheckBox(
        card,
        text="Detect & isolate retakes  (uses Whisper — adds ~30 s)",
        font=ctk.CTkFont(size=11),
        text_color="#aaaaaa",
        checkbox_width=16,
        checkbox_height=16,
    )
    w["retake_cb"].pack(anchor="w", padx=10, pady=(2, 10))

    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=6)
    btn_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["analyze_btn"] = ctk.CTkButton(btn_row, text="Analyze Audio")
    w["analyze_btn"].grid(row=0, column=0, padx=(0, 3), sticky="ew")

    w["preview_btn"] = ctk.CTkButton(btn_row, text="Preview (Add Markers)",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["preview_btn"].grid(row=0, column=1, padx=3, sticky="ew")

    w["apply_btn"] = ctk.CTkButton(btn_row, text="Apply Cuts",
                                    fg_color="#B85F3A", hover_color="#C96A45",
                                    state="disabled")
    w["apply_btn"].grid(row=0, column=2, padx=(3, 0), sticky="ew")

    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(2, 0))

    w["status"] = ctk.CTkLabel(
        parent,
        text="Ready. Select clips in the Edit page timeline, then click Analyze.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800,
    )
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=6)

    ctk.CTkLabel(parent, text="ANALYSIS RESULTS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    results_row = ctk.CTkFrame(parent, fg_color="transparent")
    results_row.pack(fill="x", padx=10, pady=2)
    results_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["found_count"] = _stat_card(results_row, "Silences Found", "0", "#D97757")
    w["found_count"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["time_saved"] = _stat_card(results_row, "Estimated Time Saved", "0.0 s", "#66bb6a")
    w["time_saved"].grid(row=0, column=1, padx=4, sticky="ew")
    w["clips_count"] = _stat_card(results_row, "Clips Analyzed", "0", "#D97757")
    w["clips_count"].grid(row=0, column=2, padx=(4, 0), sticky="ew")

    w["new_timeline_lbl"] = ctk.CTkLabel(
        parent, text="", font=ctk.CTkFont(size=11), text_color="#66bb6a", anchor="w")
    w["new_timeline_lbl"].pack(fill="x", padx=12, pady=(6, 12))

    parent._w = w


def _labeled_entry(parent: Any, label: str, default: str, unit: str) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=10, pady=2)
    row.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(row, text=label, anchor="w").grid(row=0, column=0, sticky="w")
    entry = ctk.CTkEntry(row, width=90, justify="center")
    entry.insert(0, default)
    entry.grid(row=0, column=1, padx=6)
    ctk.CTkLabel(row, text=unit, text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2)
    return entry


def _stat_card(parent: Any, label: str, default: str, color: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color="#888888").pack(pady=(0, 8))
    card._val = val
    return card
