"""UI builder for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="B-ROLL ASSISTANT  —  Smart B-roll suggestions from transcript",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    ctk.CTkLabel(
        parent,
        text="⚠  BETA — B-Roll matching is experimental. Auto Place coming in a future update.",
        font=ctk.CTkFont(size=11),
        text_color="#ff8f00",
        fg_color="#1a1200",
        corner_radius=4,
        anchor="w",
    ).pack(fill="x", padx=10, pady=4, ipady=6, ipadx=8)

    folder_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    folder_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(folder_card, text="B-ROLL FOLDER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    folder_row = ctk.CTkFrame(folder_card, fg_color="transparent")
    folder_row.pack(fill="x", padx=10, pady=(0, 8))
    folder_row.grid_columnconfigure(0, weight=1)

    w["folder"] = ctk.CTkEntry(folder_row,
                                placeholder_text="Select folder containing B-roll clips...")
    w["folder"].grid(row=0, column=0, sticky="ew", padx=(0, 6))

    w["browse_btn"] = ctk.CTkButton(folder_row, text="Browse", width=80)
    w["browse_btn"].grid(row=0, column=1)

    btn_row1 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row1.pack(fill="x", padx=10, pady=(4, 2))
    btn_row1.grid_columnconfigure((0, 1), weight=1)

    w["scan_btn"] = ctk.CTkButton(btn_row1, text="Scan Folder",
                                   fg_color="#2a2a2a", hover_color="#3a3a3a",
                                   state="disabled")
    w["scan_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["analyze_btn"] = ctk.CTkButton(btn_row1, text="Analyze Transcript",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["analyze_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    btn_row2 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row2.pack(fill="x", padx=10, pady=2)
    btn_row2.grid_columnconfigure((0, 1), weight=1)

    w["suggest_btn"] = ctk.CTkButton(btn_row2, text="Suggest B-Roll",
                                      fg_color="#1b5e20", hover_color="#2e7d32",
                                      state="disabled")
    w["suggest_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["place_btn"] = ctk.CTkButton(btn_row2, text="Auto Place on V2",
                                    fg_color="#2a2a2a", hover_color="#3a3a3a",
                                    state="disabled")
    w["place_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    w["status"] = ctk.CTkLabel(
        parent, text="Browse a folder of B-roll clips to start.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(4, 4))

    _divider(parent)

    ctk.CTkLabel(parent, text="CLIP LIBRARY  /  SUGGESTIONS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["suggestions"] = ctk.CTkTextbox(parent, height=200, state="disabled",
                                       font=ctk.CTkFont(size=12))
    w["suggestions"].pack(fill="x", padx=10, pady=(0, 4))
    _set_textbox(w["suggestions"], "Scan a folder, then generate suggestions...")

    ctk.CTkLabel(
        parent,
        text="Note: Requires transcript from the Subtitles tab. "
             "Auto-place places suggestions on V2, never overwrites existing clips.",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        wraplength=800,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(0, 12))

    parent._w = w


def _set_textbox(tb: ctk.CTkTextbox, text: str) -> None:
    tb.configure(state="normal")
    tb.delete("0.0", "end")
    tb.insert("0.0", text)
    tb.configure(state="disabled")


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)
