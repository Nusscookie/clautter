"""UI builder for the Enhance Audio tab.

Extracted from enhance_audio_tab.py so the tab file stays focused on callbacks.
Follows the same pattern as _music_build.py.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from src.constants import COLORS
from src.enhance_audio import engines


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="ENHANCE AUDIO  —  Clean up noisy / crappy source audio",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    card = ctk.CTkFrame(parent, fg_color=COLORS.BG_CARD, corner_radius=6)
    card.pack(fill="x", padx=10, pady=(0, 6))

    ctk.CTkLabel(card, text="ENHANCEMENT ENGINES",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=COLORS.TEXT_DIM).pack(anchor="w", padx=10, pady=(8, 4))

    # ── Engine checkboxes + per-engine strength sliders ──────────────
    w["engine_vars"] = {}
    w["strength_sliders"] = {}
    w["strength_lbls"] = {}

    eng_frame = ctk.CTkFrame(card, fg_color="transparent")
    eng_frame.pack(fill="x", padx=10, pady=2)

    for spec in engines.all_engines():
        blocked = not engines.is_available(spec)
        var = ctk.IntVar(value=1 if spec.id == "vad_gate" else 0)
        w["engine_vars"][spec.id] = var

        label = f"{spec.label}  [not available on Windows]" if blocked else spec.label
        cb = ctk.CTkCheckBox(
            eng_frame,
            text=label,
            variable=var,
            state="disabled" if blocked else "normal",
            text_color=COLORS.TEXT_SUBTLE if blocked else None,
        )
        cb.pack(anchor="w", pady=(4, 0))
        w[f"engine_cb_{spec.id}"] = cb

        if spec.has_strength and not blocked:
            str_row = ctk.CTkFrame(eng_frame, fg_color="transparent")
            str_row.pack(fill="x", pady=(2, 4), padx=(24, 0))
            str_row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                str_row, text="Attenuation strength",
                font=ctk.CTkFont(size=11),
                text_color=COLORS.TEXT_DIM,
            ).grid(row=0, column=0, sticky="w", padx=(0, 10))
            sl = ctk.CTkSlider(str_row, from_=0, to=100, number_of_steps=100)
            sl.set(50)
            sl.grid(row=0, column=1, sticky="ew", padx=(0, 8))
            lbl = ctk.CTkLabel(str_row, text="50%", text_color=COLORS.BRAND_PRIMARY, width=44)
            lbl.grid(row=0, column=2)
            w["strength_sliders"][spec.id] = sl
            w["strength_lbls"][spec.id] = lbl

    # ── Scope toggle ─────────────────────────────────────────────────
    scope_row = ctk.CTkFrame(card, fg_color="transparent")
    scope_row.pack(fill="x", padx=10, pady=(8, 2))
    scope_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(scope_row, text="Apply To").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["scope"] = ctk.CTkSegmentedButton(scope_row, values=["Selected Clip", "All Clips"])
    w["scope"].set("Selected Clip")
    w["scope"].grid(row=0, column=1, sticky="w")

    # ── Run button ───────────────────────────────────────────────────
    w["run_btn"] = ctk.CTkButton(
        card,
        text="▶  Enhance Audio",
        fg_color=COLORS.BTN_PRIMARY_BG,
        hover_color=COLORS.BTN_PRIMARY_HOVER,
        height=32,
    )
    w["run_btn"].pack(fill="x", padx=10, pady=(8, 4))

    # ── Auphonic stub (disabled — wired in a later branch) ───────────
    w["auphonic_btn"] = ctk.CTkButton(
        card,
        text="☁  Polish via Auphonic (cloud) — coming soon",
        fg_color=COLORS.BG_MID,
        hover_color=COLORS.BG_CARD,
        height=28,
        state="disabled",
    )
    w["auphonic_btn"].pack(fill="x", padx=10, pady=(0, 4))

    # ── Progress bar (hidden until running) ──────────────────────────
    w["progress_frame"] = ctk.CTkFrame(card, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=0)
    w["progress"] = ctk.CTkProgressBar(card, height=6)
    w["progress"].set(0)

    w["status"] = ctk.CTkLabel(
        card,
        text="Cleans the main track's audio and places the result on a new "
             "'Enhanced' track. Optional engines install on first use.",
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
        wraplength=820,
    )
    w["status"].pack(fill="x", padx=10, pady=(2, 10))

    parent._w = w
