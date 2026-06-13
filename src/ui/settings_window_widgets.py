"""Reusable row-builder widgets for the settings window.

Extracted from settings_window.py so the window/panel logic stays separate
from the small CTk layout helpers each panel composes. Pure presentation —
no app state, no settings access.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from src.constants import COLORS


def _key_row(
    parent: Any, label: str, placeholder: str | None = None
) -> tuple[ctk.CTkEntry, ctk.CTkLabel]:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 4))
    row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(row, text=f"{label}:", font=ctk.CTkFont(size=11),
                 text_color=COLORS.TEXT_MUTED, width=130, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, show="*",
                         placeholder_text=placeholder or f"Paste {label} API key")
    entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    status = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=10),
                          text_color=COLORS.TEXT_MUTED, anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 2))

    return entry, status


def _option_row(parent: Any, label: str, values: list[str]) -> ctk.CTkOptionMenu:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 6))

    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                 text_color=COLORS.TEXT_MUTED, width=150, anchor="w").pack(side="left")

    menu = ctk.CTkOptionMenu(
        row, values=values, width=240,
        fg_color=COLORS.BG_MID, button_color=COLORS.BG_MID, button_hover_color=COLORS.BG_HOVER,
    )
    menu.pack(side="left", padx=(6, 0))
    return menu


def _text_row(parent: Any, label: str, placeholder: str = "") -> ctk.CTkEntry:
    """Single-line free-text input row (visible, not masked)."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 6))
    row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                 text_color=COLORS.TEXT_MUTED, width=150, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, placeholder_text=placeholder)
    entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    return entry


def _numeric_row(
    parent: Any,
    label: str,
    min_val: float,
    max_val: float,
    default: str,
    hint: str = "",
) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 4))
    row.grid_columnconfigure(2, weight=1)

    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                 text_color=COLORS.TEXT_MUTED, width=130, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, width=80, placeholder_text=default)
    entry.grid(row=0, column=1, padx=(6, 8))
    entry.insert(0, default)

    if hint:
        ctk.CTkLabel(row, text=hint, font=ctk.CTkFont(size=10),
                     text_color=COLORS.TEXT_SUBTLE, anchor="w").grid(row=0, column=2, sticky="w")

    return entry


def _prefill(entry: ctk.CTkEntry, value: str) -> None:
    if value:
        entry.delete(0, "end")
        entry.insert(0, value)
