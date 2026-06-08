"""Main window — customtkinter-based, replaces UIManager version."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.ui.icon_helper import apply_clutter_icon
from src.utils.logger import get_logger
from src.ui import (
    dashboard_tab, smartcuts_tab,
    subtitles_tab, zooms_tab, broll_tab, graphics_tab, music_tab,
)
from src.ui.settings_window import open_settings

log = get_logger(__name__)

_WIN_W = 920
_WIN_H = 700

_TABS: list[tuple[str, Any]] = [
    ("Dashboard",       dashboard_tab),
    ("Smart Cuts",      smartcuts_tab),
    ("Subtitles",       subtitles_tab),
    ("Auto Zooms",      zooms_tab),
    ("B-Roll",          broll_tab),
    ("Music & SFX",     music_tab),
    ("Motion Graphics", graphics_tab),
]


class MainWindow:
    def __init__(self, app: Any) -> None:
        self._app = app
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._root = ctk.CTk()

    def run(self) -> None:
        try:
            self._build()
            self._root.mainloop()
        except Exception as e:
            log.error("MainWindow error: %s", e)
            raise

    def _build(self) -> None:
        root = self._root
        root.title("Clutter")
        root.geometry(f"{_WIN_W}x{_WIN_H}")
        root.resizable(True, True)
        root.configure(fg_color="#141414")

        apply_clutter_icon(root)

        # ── Top bar ──
        top = ctk.CTkFrame(root, height=38, fg_color="#1a1a1a", corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="Clutter",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#D97757",
        ).pack(side="left", padx=(14, 6), pady=6)

        ctk.CTkLabel(
            top, text="│",
            text_color="#333333",
        ).pack(side="left", padx=2, pady=6)

        self._status_lbl = ctk.CTkLabel(
            top,
            text=self._app.status_text(),
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        self._status_lbl.pack(side="left", padx=6, pady=6)

        ctk.CTkButton(
            top, text="⚙",
            font=ctk.CTkFont(size=15),
            fg_color="transparent", hover_color="#2a2a2a",
            text_color="#aaaaaa", width=32, height=32,
            corner_radius=4,
            command=lambda: open_settings(self._app),
        ).pack(side="right", padx=(0, 6), pady=3)

        # ── Project-wide BETA banner ──
        # Single source of truth for "this build is not finished".
        self._beta_banner = ctk.CTkFrame(
            root, height=26, fg_color="#1A0E00", corner_radius=0)
        self._beta_banner.pack(fill="x", side="top", after=top)
        self._beta_banner.pack_propagate(False)
        ctk.CTkLabel(
            self._beta_banner,
            text="⚠  BETA / ALPHA — Clutter is in active development. Expect rough edges.",
            font=ctk.CTkFont(size=11),
            text_color="#E8903A",
            anchor="w",
        ).pack(side="left", padx=12)

        # ── Tab view ──
        tabview = ctk.CTkTabview(root, anchor="nw", fg_color="#1e1e1e")
        tabview.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        for name, module in _TABS:
            tab = tabview.add(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)

            content = ctk.CTkScrollableFrame(tab, fg_color="transparent", corner_radius=0)
            content.grid(row=0, column=0, sticky="nsew")
            content.grid_columnconfigure(0, weight=1)

            try:
                module.build(content)
                module.setup(content, self._app)
            except Exception as e:
                log.error("Tab '%s' init error: %s", name, e)
                ctk.CTkLabel(
                    content,
                    text=f"Tab load error: {e}",
                    text_color="#ff6b6b",
                ).pack(padx=12, pady=12)
