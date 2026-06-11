"""UI builder for the Auto Zooms tab.

Extracted from zooms_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="AUTO ZOOMS  —  Apply dynamic zoom cuts at your edit's cut points",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(card, text="ZOOM SETTINGS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    # Track-face checkbox — centers each zoom on the speaker. Off = plain center
    # zoom (no OpenCV). Zooms are *triggered* by cut points either way.
    track_row = ctk.CTkFrame(card, fg_color="transparent")
    track_row.pack(fill="x", padx=10, pady=2)
    w["track_face"] = ctk.CTkCheckBox(track_row, text="Track face — center zoom on speaker")
    w["track_face"].select()  # default ON
    w["track_face"].pack(side="left")

    w["detect_note"] = ctk.CTkLabel(
        card,
        text="Face tracking requires opencv-python  •  pip install opencv-python",
        font=ctk.CTkFont(size=10),
        text_color="#888888",
        anchor="w",
    )
    w["detect_note"].pack(fill="x", padx=10, pady=(0, 4))

    amount_row = ctk.CTkFrame(card, fg_color="transparent")
    amount_row.pack(fill="x", padx=10, pady=2)
    amount_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(amount_row, text="Zoom Amount").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["zoom_slider"] = ctk.CTkSlider(amount_row, from_=105, to=150, number_of_steps=45)
    w["zoom_slider"].set(115)
    w["zoom_slider"].grid(row=0, column=1, sticky="ew", padx=(0, 8))
    w["zoom_lbl"] = ctk.CTkLabel(amount_row, text="115%", text_color="#D97757", width=44)
    w["zoom_lbl"].grid(row=0, column=2)

    take_row = ctk.CTkFrame(card, fg_color="transparent")
    take_row.pack(fill="x", padx=10, pady=2)
    take_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(take_row, text="Min Take Length (s)").grid(row=0, column=0, sticky="w",
                                                            padx=(0, 12))
    w["min_take"] = ctk.CTkEntry(take_row, width=70, justify="center")
    w["min_take"].insert(0, "2.0")
    w["min_take"].grid(row=0, column=1, sticky="w")

    max_row = ctk.CTkFrame(card, fg_color="transparent")
    max_row.pack(fill="x", padx=10, pady=2)
    max_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(max_row, text="Max Zooms Per Minute").grid(row=0, column=0, sticky="w",
                                                             padx=(0, 12))
    w["max_per_min"] = ctk.CTkEntry(max_row, width=70, justify="center")
    w["max_per_min"].insert(0, "4")
    w["max_per_min"].grid(row=0, column=1, sticky="w")

    # Smooth vs Hard are mutually exclusive — a single segmented control avoids
    # the old contradictory two-checkbox state. The worker reads zoom_style:
    # "Smooth" -> fade=True (animated Fusion ease), "Hard Cut" -> static zoom.
    style_row = ctk.CTkFrame(card, fg_color="transparent")
    style_row.pack(fill="x", padx=10, pady=(2, 10))
    ctk.CTkLabel(style_row, text="Zoom Style").pack(side="left", padx=(0, 12))
    w["zoom_style"] = ctk.CTkSegmentedButton(
        style_row, values=["Smooth (Ease In/Out)", "Hard Cut"])
    w["zoom_style"].set("Smooth (Ease In/Out)")
    w["zoom_style"].pack(side="left")

    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=6)
    btn_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["analyze_btn"] = ctk.CTkButton(btn_row, text="Analyze Cuts")
    w["analyze_btn"].grid(row=0, column=0, padx=(0, 3), sticky="ew")

    w["preview_btn"] = ctk.CTkButton(btn_row, text="Preview (Add Markers)",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["preview_btn"].grid(row=0, column=1, padx=3, sticky="ew")

    w["apply_btn"] = ctk.CTkButton(btn_row, text="Apply Zooms",
                                    fg_color="#6a1b9a", hover_color="#7b1fa2",
                                    state="disabled")
    w["apply_btn"].grid(row=0, column=2, padx=(3, 0), sticky="ew")

    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(2, 0))

    w["status"] = ctk.CTkLabel(
        parent, text="Run Smart Cuts first, then Analyze Cuts to place zooms at your cut points.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=6)

    results_row = ctk.CTkFrame(parent, fg_color="transparent")
    results_row.pack(fill="x", padx=10, pady=4)
    results_row.grid_columnconfigure((0, 1), weight=1)

    w["found_count"] = _stat_card(results_row, "Zoom Points Found", "0", "#ab47bc")
    w["found_count"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["applied_count"] = _stat_card(results_row, "Zooms Applied", "0", "#66bb6a")
    w["applied_count"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    w["new_timeline_lbl"] = ctk.CTkLabel(
        parent, text="", font=ctk.CTkFont(size=11), text_color="#66bb6a", anchor="w")
    w["new_timeline_lbl"].pack(fill="x", padx=12, pady=(6, 12))

    parent._w = w


def _stat_card(parent: Any, label: str, default: str, color: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color="#888888").pack(pady=(0, 8))
    card._val = val
    return card
