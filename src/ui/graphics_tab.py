"""Motion Graphics tab — fully automatic Hyperframes pipeline."""

from __future__ import annotations
import threading
import tkinter.filedialog as _fd
from pathlib import Path
from typing import Any

import customtkinter as ctk

from src.constants import COLORS, SETTINGS_KEYS
from src.utils.logger import get_logger

log = get_logger(__name__)

_PLACEHOLDER = (
    "e.g. 'My YouTube channel is @TechTalk with 128K subs. Prefer data charts. "
    "Place graphics only in the second half.'"
)


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

    # ── Creative Mode toggle ──
    creative_row = ctk.CTkFrame(parent, fg_color="transparent")
    creative_row.pack(fill="x", padx=10, pady=(2, 0))
    w["creative_toggle"] = ctk.CTkSwitch(
        creative_row,
        text="Creative Mode — LLM builds custom animations from scratch (no catalog)",
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
    )
    w["creative_toggle"].pack(anchor="w")

    # ── User instructions ──
    instr_frame = ctk.CTkFrame(parent, fg_color="transparent")
    instr_frame.pack(fill="x", padx=10, pady=(6, 0))
    ctk.CTkLabel(
        instr_frame,
        text="Custom Instructions (optional)",
        font=ctk.CTkFont(size=10),
        text_color=COLORS.TEXT_MUTED,
    ).pack(anchor="w")
    w["instructions"] = ctk.CTkTextbox(instr_frame, height=60, font=ctk.CTkFont(size=11))
    w["instructions"].pack(fill="x")
    w["instructions"].insert("1.0", _PLACEHOLDER)
    w["instructions"].configure(text_color=COLORS.TEXT_SUBTLE)

    # ── Reference assets folder ──
    ref_frame = ctk.CTkFrame(parent, fg_color="transparent")
    ref_frame.pack(fill="x", padx=10, pady=(6, 0))
    ref_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        ref_frame,
        text="Reference Assets",
        font=ctk.CTkFont(size=10),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    ).grid(row=0, column=0, columnspan=3, sticky="w")

    w["ref_folder"] = ctk.CTkEntry(
        ref_frame,
        placeholder_text="Optional — folder with your icons / logos / images",
        font=ctk.CTkFont(size=11),
    )
    w["ref_folder"].grid(row=1, column=0, sticky="ew", pady=(2, 0))

    w["ref_clear"] = ctk.CTkButton(
        ref_frame, text="✕", width=28, height=28,
        fg_color=COLORS.BG_CARD, hover_color=COLORS.BG_HOVER,
        text_color=COLORS.TEXT_MUTED, font=ctk.CTkFont(size=11),
    )
    w["ref_clear"].grid(row=1, column=1, padx=(6, 0), pady=(2, 0))

    w["ref_browse"] = ctk.CTkButton(
        ref_frame, text="Browse", width=70, height=28,
        fg_color=COLORS.BG_CARD, hover_color=COLORS.BG_HOVER,
        text_color=COLORS.TEXT_MUTED, font=ctk.CTkFont(size=11),
    )
    w["ref_browse"].grid(row=1, column=2, padx=(6, 0), pady=(2, 0))

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

    # ── Ref folder — populate from settings + wire Browse ──
    saved_ref = str(app.settings.get(SETTINGS_KEYS.GRAPHICS_REF_FOLDER, "") or "")
    if saved_ref:
        w["ref_folder"].insert(0, saved_ref)

    def _on_ref_browse() -> None:
        chosen = _fd.askdirectory(title="Select Reference Assets Folder")
        if chosen:
            path = Path(chosen).as_posix()
            w["ref_folder"].delete(0, "end")
            w["ref_folder"].insert(0, path)
            app.settings.set(SETTINGS_KEYS.GRAPHICS_REF_FOLDER, path)

    def _on_ref_entry_change(_e: Any = None) -> None:
        app.settings.set(SETTINGS_KEYS.GRAPHICS_REF_FOLDER, w["ref_folder"].get().strip())

    def _on_ref_clear() -> None:
        w["ref_folder"].delete(0, "end")
        app.settings.set(SETTINGS_KEYS.GRAPHICS_REF_FOLDER, "")

    w["ref_browse"].configure(command=_on_ref_browse)
    w["ref_clear"].configure(command=_on_ref_clear)
    w["ref_folder"].bind("<FocusOut>", _on_ref_entry_change)

    # ── Instructions placeholder behaviour ──
    def _instr_text() -> str:
        return w["instructions"].get("1.0", "end-1c")

    def _on_focus_in(_e: Any) -> None:
        if _instr_text() == _PLACEHOLDER:
            w["instructions"].delete("1.0", "end")
            w["instructions"].configure(text_color=COLORS.TEXT_MUTED)

    def _on_focus_out(_e: Any) -> None:
        if not _instr_text().strip():
            w["instructions"].delete("1.0", "end")
            w["instructions"].insert("1.0", _PLACEHOLDER)
            w["instructions"].configure(text_color=COLORS.TEXT_SUBTLE)

    w["instructions"].bind("<FocusIn>", _on_focus_in)
    w["instructions"].bind("<FocusOut>", _on_focus_out)

    def on_generate() -> None:
        w["generate_btn"].configure(state="disabled")
        w["progress"].pack(in_=w["progress_frame"], fill="x")
        w["progress"].set(0)
        set_status("Starting…", COLORS.BRAND_PRIMARY)

        provider_val = w["provider"].get()
        chosen_provider = None if provider_val == "(auto)" else provider_val

        raw_instr = _instr_text().strip()
        user_instructions = raw_instr if raw_instr and raw_instr != _PLACEHOLDER else None

        creative_mode = bool(w["creative_toggle"].get())

        def _work() -> None:
            _event = threading.Event()
            _resolver_result: dict[str, Any] = {}

            def _overflow_resolver(placements: list, timeline_duration_sec: float) -> list | None:
                def _show() -> None:
                    from src.ui._graphics_overflow_dialog import (
                        GraphicsOverflowDialog, apply_resolution,
                    )
                    root = frame
                    while not isinstance(root, ctk.CTk):
                        root = root.master
                    overflowing = [
                        p for p in placements
                        if p.start_sec + p.duration_sec > timeline_duration_sec
                    ]
                    dlg = GraphicsOverflowDialog(
                        root,
                        overflowing=overflowing,
                        timeline_duration_sec=timeline_duration_sec,
                    )
                    dlg.wait_window()
                    choice = dlg.choice
                    if choice is None:
                        _resolver_result["placements"] = None
                    else:
                        _resolver_result["placements"] = apply_resolution(
                            placements, timeline_duration_sec, choice,
                        )
                    _event.set()

                frame.after(0, _show)
                _event.wait()
                return _resolver_result.get("placements")

            try:
                from src.graphics.engine import run
                placed, err = run(
                    app,
                    provider=chosen_provider,
                    user_instructions=user_instructions,
                    creative_mode=creative_mode,
                    status_cb=lambda msg: set_status(msg, COLORS.BRAND_PRIMARY),
                    progress_cb=set_progress,
                    overflow_resolver=_overflow_resolver,
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
