"""Motion Graphics tab — coming soon placeholder."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    banner = ctk.CTkFrame(parent, fg_color="#1A0E00", corner_radius=0, height=26)
    banner.pack(fill="x", side="top")
    banner.pack_propagate(False)
    ctk.CTkLabel(
        banner,
        text="⚠  Motion Graphics — coming in a future update. Not yet available.",
        font=ctk.CTkFont(size=11),
        text_color="#E8903A",
        anchor="w",
    ).pack(side="left", padx=12)

    ctk.CTkLabel(
        parent,
        text="Stay tuned.",
        font=ctk.CTkFont(size=11),
        text_color="#555555",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 0))

    parent._w = {}


def setup(frame: Any, app: Any) -> None:
    pass
