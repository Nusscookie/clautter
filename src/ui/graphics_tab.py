"""Motion Graphics tab — fully automatic Hyperframes pipeline."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.constants import COLORS
from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="MOTION GRAPHICS  —  AI-powered Hyperframes renderer",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Provider row ──
    provider_row = ctk.CTkFrame(parent, fg_color="transparent")
    provider_row.pack(fill="x", padx=10, pady=4)
    provider_row.grid_columnconfigure(0, weight=1)

    provider_frame = ctk.CTkFrame(provider_row, fg_color="transparent")
    provider_frame.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ctk.CTkLabel(
        provider_frame,
        text="AI Provider",
        font=ctk.CTkFont(size=10),
        text_color=COLORS.TEXT_MUTED,
    ).pack(anchor="w")
    w["provider"] = ctk.CTkComboBox(provider_frame, values=["(auto)"], state="readonly")
    w["provider"].set("(auto)")
    w["provider"].pack(fill="x")

    w["generate_btn"] = ctk.CTkButton(
        provider_row,
        text="Generate Motion Graphics",
        width=190,
    )
    w["generate_btn"].grid(row=0, column=1, sticky="s")

    # ── Status ──
    w["status"] = ctk.CTkLabel(
        parent,
        text="Select a provider and click Generate. Requires transcript from Subtitles tab.",
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    )
    w["status"].pack(fill="x", padx=12, pady=(4, 2))

    # ── Progress bar (hidden until running) ──
    w["progress_frame"] = ctk.CTkFrame(parent, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(0, 4))
    w["progress"] = ctk.CTkProgressBar(w["progress_frame"])
    w["progress"].set(0)

    _divider(parent)

    # ── Info card ──
    info_card = ctk.CTkFrame(parent, fg_color=COLORS.BG_DARK, corner_radius=6)
    info_card.pack(fill="x", padx=10, pady=(8, 12))

    ctk.CTkLabel(
        info_card,
        text="HOW IT WORKS",
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color=COLORS.TEXT_DIM,
    ).pack(anchor="w", padx=10, pady=(8, 4))

    ctk.CTkLabel(
        info_card,
        text=(
            "1. LLM analyzes your transcript and picks Hyperframes templates (data charts,\n"
            "   callouts, lower thirds, etc.) that match the content.\n"
            "2. Each template is rendered to MP4 via the Hyperframes CLI (requires Node.js).\n"
            "3. Rendered clips are imported into Resolve and placed on the Motion Graphics track."
        ),
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
        justify="left",
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(0, 8))

    parent._w = w


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color=COLORS.SEPARATOR, corner_radius=0).pack(
        fill="x", padx=10, pady=4)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(current: int, total: int) -> None:
        value = current / total if total > 0 else 0
        _ui(lambda: w["progress"].set(value))

    def _refresh_providers() -> None:
        try:
            from src.utils.llm_providers import available_providers
            providers = available_providers(app.settings)
            values = ["(auto)"] + providers if providers else ["(auto)"]
            _ui(lambda: w["provider"].configure(values=values))
        except Exception:
            pass

    _refresh_providers()

    def on_generate() -> None:
        w["generate_btn"].configure(state="disabled")
        w["progress"].pack(in_=w["progress_frame"], fill="x")
        w["progress"].set(0)
        set_status("Starting…", COLORS.BRAND_PRIMARY)

        provider_val = w["provider"].get()
        chosen_provider = None if provider_val == "(auto)" else provider_val

        def _work() -> None:
            try:
                from src.graphics.engine import run
                placed, err = run(
                    app,
                    provider=chosen_provider,
                    status_cb=lambda msg: set_status(msg, COLORS.BRAND_PRIMARY),
                    progress_cb=set_progress,
                )
                if err:
                    set_status(f"Error: {err}", COLORS.ERROR)
                else:
                    set_status(
                        f"{placed} motion graphic(s) placed on timeline.",
                        COLORS.SUCCESS,
                    )
            except Exception as e:
                log.error("Motion graphics pipeline error: %s", e)
                set_status(f"Error: {e}", COLORS.ERROR)
            finally:
                _ui(lambda: w["generate_btn"].configure(state="normal"))
                _ui(lambda: w["progress"].pack_forget())

        threading.Thread(target=_work, daemon=True).start()

    w["generate_btn"].configure(command=on_generate)
