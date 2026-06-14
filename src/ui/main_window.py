"""Main window — customtkinter-based, replaces UIManager version."""

from __future__ import annotations
from typing import Any
from pathlib import Path
import logging

import customtkinter as ctk

from src.constants import COLORS
from src.ui.icon_helper import apply_clautter_icon
from src.utils.logger import get_logger
from src.ui import (
    dashboard_tab, smartcuts_tab,
    subtitles_tab, zooms_tab, broll_tab, graphics_tab, music_tab,
)
from src.ui.settings_window import open_settings
from src.ui.console_window import ConsoleWindow
from src.utils.logger import UILogHandler

log = get_logger(__name__)

_WIN_W = 920
_WIN_H = 700

# Custom terracotta CTk theme — widget-level source of truth, mirrors COLORS.
_THEME_PATH = Path(__file__).resolve().parents[2] / "assets" / "clautter_theme.json"


def _apply_theme() -> None:
    """Load the Clautter terracotta theme; fall back to 'blue' so the app
    always boots even if the theme file is missing or malformed."""
    try:
        ctk.set_default_color_theme(str(_THEME_PATH))
        log.info("Loaded Clautter theme: %s", _THEME_PATH)
    except Exception as e:
        log.warning("Clautter theme load failed (%s) — falling back to 'blue'", e)
        ctk.set_default_color_theme("blue")

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
        _apply_theme()
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
        root.title("Clautter")
        root.geometry(f"{_WIN_W}x{_WIN_H}")
        root.resizable(True, True)
        root.configure(fg_color=COLORS.BG_DARKEST)

        apply_clautter_icon(root)

        # ── Top bar ──
        top = ctk.CTkFrame(root, height=38, fg_color=COLORS.BG_DARK, corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="Clautter",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS.BRAND_PRIMARY,
        ).pack(side="left", padx=(14, 6), pady=6)

        ctk.CTkLabel(
            top, text="│",
            text_color=COLORS.SEPARATOR_DARK,
        ).pack(side="left", padx=2, pady=6)

        # ── Connection status pill: a colored dot makes connected/disconnected
        #    legible at a glance instead of relying on text alone. ──
        pill = ctk.CTkFrame(top, fg_color=COLORS.BG_CARD, corner_radius=10)
        pill.pack(side="left", padx=6, pady=6)
        connected = self._app.connected
        self._status_dot = ctk.CTkLabel(
            pill, text="●",
            font=ctk.CTkFont(size=12),
            text_color=COLORS.SUCCESS if connected else COLORS.ERROR,
        )
        self._status_dot.pack(side="left", padx=(8, 4), pady=1)
        self._status_lbl = ctk.CTkLabel(
            pill,
            text=self._app.status_text(),
            font=ctk.CTkFont(size=11),
            text_color=COLORS.TEXT_SECONDARY if connected else COLORS.TEXT_DIM,
        )
        self._status_lbl.pack(side="left", padx=(0, 10), pady=1)

        ctk.CTkButton(
            top, text="⚙",
            font=ctk.CTkFont(size=15),
            fg_color="transparent", hover_color=COLORS.BG_CARD,
            text_color=COLORS.TEXT_MUTED, width=32, height=32,
            corner_radius=4,
            command=lambda: open_settings(self._app),
        ).pack(side="right", padx=(0, 6), pady=3)

        # ── Project-wide BETA banner ──

        # ── Tab view ──
        tabview = ctk.CTkTabview(root, anchor="nw", fg_color=COLORS.BG_MID)
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
                    text_color=COLORS.ERROR,
                ).pack(padx=12, pady=12)

        if self._app.settings.get("show_console_log", True):
            self._console: ConsoleWindow | None = None

            def _attach_console() -> None:
                self._console = ConsoleWindow(root)
                handler = UILogHandler(
                    lambda msg: root.after(0, self._console.append, msg)
                )
                handler.setLevel(logging.DEBUG)
                logging.getLogger().addHandler(handler)

            root.after(200, _attach_console)
