"""Floating console log window — shows live Clutter log output."""

from __future__ import annotations

from src.constants import COLORS
from typing import Any

import customtkinter as ctk


class ConsoleWindow:
    def __init__(self, root: Any) -> None:
        self._win = ctk.CTkToplevel(root)
        self._win.title("Clutter — Console")
        self._win.geometry("720x380")
        self._win.configure(fg_color=COLORS.BG_DARKEST)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._textbox = ctk.CTkTextbox(
            self._win,
            fg_color=COLORS.BG_CONSOLE,
            text_color=COLORS.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            wrap="none",
            corner_radius=0,
        )
        self._textbox.pack(fill="both", expand=True, padx=0, pady=0)

    def append(self, msg: str) -> None:
        self._textbox.configure(state="normal")
        self._textbox.insert("end", msg + "\n")
        self._textbox.configure(state="disabled")
        self._textbox.see("end")

    def _on_close(self) -> None:
        self._win.withdraw()

    def show(self) -> None:
        self._win.deiconify()
        self._win.lift()
