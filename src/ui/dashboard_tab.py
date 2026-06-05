"""Dashboard tab — session stats and connection status."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    # ── Title ──
    ctk.CTkLabel(
        parent,
        text="CLUTTER",
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color="#ffffff",
    ).pack(pady=(16, 2))

    ctk.CTkLabel(
        parent,
        text="DaVinci Resolve Plugin  •  v1.0.0",
        font=ctk.CTkFont(size=11),
        text_color="#888888",
    ).pack(pady=(0, 8))

    _divider(parent)

    # ── Stats ──
    ctk.CTkLabel(
        parent,
        text="SESSION STATS",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
    ).pack(anchor="w", padx=14, pady=(10, 4))

    row1 = ctk.CTkFrame(parent, fg_color="transparent")
    row1.pack(fill="x", padx=10, pady=2)
    row1.grid_columnconfigure((0, 1), weight=1)

    w["time_saved"] = _stat_card(row1, "Time Saved", "0.0 s", "#4fc3f7")
    w["time_saved"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["total_edits"] = _stat_card(row1, "Total Edits", "0", "#4fc3f7")
    w["total_edits"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    row2 = ctk.CTkFrame(parent, fg_color="transparent")
    row2.pack(fill="x", padx=10, pady=2)
    row2.grid_columnconfigure((0, 1), weight=1)

    w["zooms"] = _stat_card(row2, "Zooms Applied", "0", "#4fc3f7")
    w["zooms"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["subs"] = _stat_card(row2, "Subtitles Generated", "0", "#4fc3f7")
    w["subs"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    _divider(parent)

    # ── Quick start ──
    ctk.CTkLabel(
        parent,
        text="QUICK START",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
    ).pack(anchor="w", padx=14, pady=(10, 4))

    for tip in [
        "1. Smart Cuts  —  Select clips on timeline, then Analyze + Apply Cuts",
        "2. Subtitles  —  Enter ElevenLabs API key, then Generate Transcript",
        "3. Auto Zooms  —  After generating transcript, Analyze + Apply Zooms",
    ]:
        ctk.CTkLabel(
            parent,
            text=tip,
            font=ctk.CTkFont(size=12),
            text_color="#cccccc",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=1)

    # ── Spacer ──
    ctk.CTkFrame(parent, height=16, fg_color="transparent").pack()

    # ── Buttons ──
    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=(4, 12))
    btn_row.grid_columnconfigure((0, 1), weight=1)

    w["refresh_btn"] = ctk.CTkButton(btn_row, text="Refresh Stats")
    w["refresh_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["reconnect_btn"] = ctk.CTkButton(btn_row, text="Reconnect to Resolve",
                                        fg_color="#2a2a2a", hover_color="#3a3a3a")
    w["reconnect_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    parent._w = w


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


def _stat_card(parent: Any, label: str, default: str, color: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    val_lbl = ctk.CTkLabel(
        card,
        text=default,
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color=color,
    )
    val_lbl.pack(pady=(10, 2))
    ctk.CTkLabel(
        card,
        text=label,
        font=ctk.CTkFont(size=10),
        text_color="#888888",
    ).pack(pady=(0, 10))
    card._val_lbl = val_lbl
    return card


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    def _refresh() -> None:
        stats = app.settings.stats
        w["time_saved"]._val_lbl.configure(
            text=f"{stats.get('total_time_saved_sec', 0.0):.1f} s")
        w["total_edits"]._val_lbl.configure(
            text=str(int(stats.get("total_edits", 0))))
        w["zooms"]._val_lbl.configure(
            text=str(int(stats.get("total_zooms_applied", 0))))
        w["subs"]._val_lbl.configure(
            text=str(int(stats.get("total_subtitles_generated", 0))))

    def on_refresh() -> None:
        _refresh()

    def on_reconnect() -> None:
        w["reconnect_btn"].configure(state="disabled")
        ok = app.reconnect()
        log.info("Reconnect: %s", ok)
        w["reconnect_btn"].configure(state="normal")

    w["refresh_btn"].configure(command=on_refresh)
    w["reconnect_btn"].configure(command=on_reconnect)

    _refresh()
