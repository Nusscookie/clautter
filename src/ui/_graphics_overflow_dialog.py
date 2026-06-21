"""Overflow guard dialog for the motion graphics pipeline.

Shown when LLM placements would extend past the timeline end.
Offers three resolution strategies before any rendering begins.
"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

import customtkinter as ctk

from src.constants import COLORS
from src.ui.icon_helper import apply_clautter_icon

if TYPE_CHECKING:
    from src.graphics.llm_director import GraphicPlacement


def apply_resolution(
    placements: list[Any],
    timeline_duration_sec: float,
    choice: str,
) -> list[Any]:
    """Return placement list corrected for the chosen overflow strategy.

    choice must be one of: "speed_up", "shift_left", "hard_cut".
    Placements that fit already are left untouched (except speed_up, which
    scales all uniformly to preserve relative timing).
    """
    from src.graphics.llm_director import GraphicPlacement

    if choice == "speed_up":
        max_end = max(p.start_sec + p.duration_sec for p in placements)
        if max_end <= 0:
            return placements
        scale = timeline_duration_sec / max_end
        return [
            GraphicPlacement(
                block=p.block,
                start_sec=p.start_sec * scale,
                duration_sec=p.duration_sec * scale,
                params=p.params,
            )
            for p in placements
        ]

    if choice == "shift_left":
        result = []
        for p in placements:
            if p.start_sec + p.duration_sec > timeline_duration_sec:
                new_start = max(0.0, timeline_duration_sec - p.duration_sec)
                result.append(GraphicPlacement(
                    block=p.block,
                    start_sec=new_start,
                    duration_sec=p.duration_sec,
                    params=p.params,
                ))
            else:
                result.append(p)
        return result

    if choice == "hard_cut":
        result = []
        for p in placements:
            if p.start_sec + p.duration_sec > timeline_duration_sec:
                new_dur = max(0.0, timeline_duration_sec - p.start_sec)
                if new_dur <= 0:
                    continue  # graphic starts at or past end — drop it
                result.append(GraphicPlacement(
                    block=p.block,
                    start_sec=p.start_sec,
                    duration_sec=new_dur,
                    params=p.params,
                ))
            else:
                result.append(p)
        return result

    return placements


def _fmt_time(sec: float) -> str:
    m = int(sec) // 60
    s = sec - m * 60
    return f"{m}:{s:04.1f}"


class GraphicsOverflowDialog(ctk.CTkToplevel):
    """Modal dialog shown when motion graphic placements overflow the timeline.

    Must be created on the tkinter main thread.
    After wait_window() returns, read .choice:
      "speed_up" | "shift_left" | "hard_cut" | None (cancelled)
    """

    def __init__(
        self,
        master: Any,
        *,
        overflowing: list[Any],
        timeline_duration_sec: float,
    ) -> None:
        super().__init__(master)
        apply_clautter_icon(self)
        self.title("Motion Graphics Overflow")
        self.choice: str | None = None

        dialog_w, dialog_h = 540, 360
        master.update_idletasks()
        rx = master.winfo_x() + (master.winfo_width()  - dialog_w) // 2
        ry = master.winfo_y() + (master.winfo_height() - dialog_h) // 2
        self.geometry(f"{dialog_w}x{dialog_h}+{rx}+{ry}")
        self.resizable(False, False)
        self.transient(master)
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.after(10, self.grab_set)

        self._build(overflowing, timeline_duration_sec)

    def _build(self, overflowing: list[Any], timeline_duration_sec: float) -> None:
        # ── Header ──────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="⚠  Motion Graphics Overflow",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS.WARNING,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            self,
            text=(
                f"The following graphic(s) extend past the timeline end "
                f"({_fmt_time(timeline_duration_sec)}). Choose how to fix them:"
            ),
            font=ctk.CTkFont(size=11),
            text_color=COLORS.TEXT_SECONDARY,
            anchor="w",
            wraplength=500,
            justify="left",
        ).pack(fill="x", padx=20, pady=(0, 8))

        # ── Overflow list ────────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            self,
            height=120,
            fg_color=COLORS.BG_DARK,
            corner_radius=6,
        )
        scroll.pack(fill="x", padx=20, pady=(0, 10))

        for p in overflowing:
            end_sec = p.start_sec + p.duration_sec
            overflow_sec = end_sec - timeline_duration_sec
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row,
                text=p.block,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLORS.TEXT_PRIMARY,
                anchor="w",
                width=200,
            ).pack(side="left", padx=(4, 8))

            ctk.CTkLabel(
                row,
                text=f"{_fmt_time(p.start_sec)} → {_fmt_time(end_sec)}",
                font=ctk.CTkFont(size=11),
                text_color=COLORS.TEXT_MUTED,
                anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=f"  +{overflow_sec:.1f}s past end",
                font=ctk.CTkFont(size=11),
                text_color=COLORS.ERROR,
                anchor="w",
            ).pack(side="left")

        # ── Divider ──────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=COLORS.SEPARATOR, corner_radius=0).pack(
            fill="x", padx=20, pady=(0, 12)
        )

        # ── Button row ───────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text="Shift Left",
            width=130,
            fg_color=COLORS.BTN_PRIMARY_BG,
            hover_color=COLORS.BTN_PRIMARY_HOVER,
            command=lambda: self._select("shift_left"),
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            btn_row,
            text="Hard Cut",
            width=130,
            fg_color=COLORS.BG_CARD,
            hover_color=COLORS.BG_HOVER,
            text_color=COLORS.TEXT_MUTED,
            command=lambda: self._select("hard_cut"),
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=80,
            fg_color=COLORS.SEPARATOR,
            hover_color=COLORS.TEXT_SUBTLE,
            text_color=COLORS.TEXT_MUTED,
            command=self.destroy,
        ).pack(side="left", padx=6)

        # ── Option descriptions ──────────────────────────────────────────────
        desc_frame = ctk.CTkFrame(self, fg_color="transparent")
        desc_frame.pack(fill="x", padx=20)

        ctk.CTkLabel(
            desc_frame,
            text=(
                "Shift Left — keep durations, move overflowing graphics earlier so they end at the video end.\n"
                "Hard Cut — trim overflowing graphics at the video end (may cut animation mid-play)."
            ),
            font=ctk.CTkFont(size=10),
            text_color=COLORS.TEXT_DIM,
            justify="left",
            anchor="w",
            wraplength=500,
        ).pack(anchor="w")

    def _select(self, choice: str) -> None:
        self.choice = choice
        self.destroy()
