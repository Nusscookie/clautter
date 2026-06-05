"""Main window — customtkinter-based, replaces UIManager version."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger
from src.ui import (
    dashboard_tab, smartcuts_tab, pace_tab,
    subtitles_tab, zooms_tab, broll_tab, graphics_tab,
)

log = get_logger(__name__)

_WIN_W = 920
_WIN_H = 700

_TABS: list[tuple[str, Any]] = [
    ("Dashboard",       dashboard_tab),
    ("Smart Cuts",      smartcuts_tab),
    ("Pace Control",    pace_tab),
    ("Subtitles",       subtitles_tab),
    ("Auto Zooms",      zooms_tab),
    ("B-Roll",          broll_tab),
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

        try:
            from PIL import Image, ImageTk
            from pathlib import Path
            _icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.png"
            if _icon_path.exists():
                self._icon_img = ImageTk.PhotoImage(Image.open(str(_icon_path)))
                root.iconphoto(False, self._icon_img)
        except Exception as _e:
            log.debug("Icon load failed: %s", _e)

        # ── Top bar ──
        top = ctk.CTkFrame(root, height=38, fg_color="#1a1a1a", corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="Clutter",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#4fc3f7",
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
