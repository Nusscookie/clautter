"""Auto Zooms tab — volume-peak-based intelligent zoom cuts."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.ui._zooms_workers import analyze_thread, apply_thread, preview_thread
from src.utils.logger import get_logger

log = get_logger(__name__)

_MODES = ["Conservative", "Standard", "High Energy"]


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="AUTO ZOOMS  —  Apply dynamic zoom cuts based on audio energy",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Settings card ──
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(card, text="ZOOM SETTINGS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    mode_row = ctk.CTkFrame(card, fg_color="transparent")
    mode_row.pack(fill="x", padx=10, pady=2)
    mode_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(mode_row, text="Energy Mode").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["mode"] = ctk.CTkComboBox(mode_row, values=_MODES, state="readonly")
    w["mode"].set("Standard")
    w["mode"].grid(row=0, column=1, sticky="ew")

    amount_row = ctk.CTkFrame(card, fg_color="transparent")
    amount_row.pack(fill="x", padx=10, pady=2)
    amount_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(amount_row, text="Zoom Amount").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["zoom_slider"] = ctk.CTkSlider(amount_row, from_=105, to=150, number_of_steps=45)
    w["zoom_slider"].set(115)
    w["zoom_slider"].grid(row=0, column=1, sticky="ew", padx=(0, 8))
    w["zoom_lbl"] = ctk.CTkLabel(amount_row, text="115%", text_color="#4fc3f7", width=44)
    w["zoom_lbl"].grid(row=0, column=2)

    max_row = ctk.CTkFrame(card, fg_color="transparent")
    max_row.pack(fill="x", padx=10, pady=2)
    max_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(max_row, text="Max Zooms Per Minute").grid(row=0, column=0, sticky="w",
                                                             padx=(0, 12))
    w["max_per_min"] = ctk.CTkEntry(max_row, width=70, justify="center")
    w["max_per_min"].insert(0, "4")
    w["max_per_min"].grid(row=0, column=1, sticky="w")

    check_row = ctk.CTkFrame(card, fg_color="transparent")
    check_row.pack(fill="x", padx=10, pady=(2, 10))
    w["fade_zoom"] = ctk.CTkCheckBox(check_row, text="Fade Zooms (Dynamic Zoom Ease)")
    w["fade_zoom"].pack(side="left", padx=(0, 16))
    w["fade_zoom"].select()
    w["hard_cut"] = ctk.CTkCheckBox(check_row, text="Hard Cut Zooms")
    w["hard_cut"].pack(side="left")

    # ── Buttons ──
    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=6)
    btn_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["analyze_btn"] = ctk.CTkButton(btn_row, text="Analyze Audio")
    w["analyze_btn"].grid(row=0, column=0, padx=(0, 3), sticky="ew")

    w["preview_btn"] = ctk.CTkButton(btn_row, text="Preview (Add Markers)",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["preview_btn"].grid(row=0, column=1, padx=3, sticky="ew")

    w["apply_btn"] = ctk.CTkButton(btn_row, text="Apply Zooms",
                                    fg_color="#6a1b9a", hover_color="#7b1fa2",
                                    state="disabled")
    w["apply_btn"].grid(row=0, column=2, padx=(3, 0), sticky="ew")

    # ── Progress ──
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(2, 0))

    w["status"] = ctk.CTkLabel(
        parent, text="Click Analyze to detect high-energy moments for zooms.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=6)

    # ── Results ──
    results_row = ctk.CTkFrame(parent, fg_color="transparent")
    results_row.pack(fill="x", padx=10, pady=4)
    results_row.grid_columnconfigure((0, 1), weight=1)

    w["found_count"] = _stat_card(results_row, "Zoom Points Found", "0", "#ab47bc")
    w["found_count"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["applied_count"] = _stat_card(results_row, "Zooms Applied", "0", "#66bb6a")
    w["applied_count"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    w["new_timeline_lbl"] = ctk.CTkLabel(
        parent, text="", font=ctk.CTkFont(size=11), text_color="#66bb6a", anchor="w")
    w["new_timeline_lbl"].pack(fill="x", padx=12, pady=(6, 12))

    parent._w = w


def _stat_card(parent: Any, label: str, default: str, color: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color="#888888").pack(pady=(0, 8))
    card._val = val
    return card


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "zoom_points": [],
        "clips": [],
        "timeline_choice": ("new", None),
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(value: float, visible: bool = True) -> None:
        def _apply() -> None:
            if visible:
                w["progress"].pack(in_=w["progress_frame"], fill="x")
                w["progress"].set(value / 100.0)
            else:
                w["progress"].pack_forget()
        _ui(_apply)

    def set_btn(name: str, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        _ui(lambda: w[name].configure(state=state))

    def on_analyze() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(
            target=analyze_thread,
            args=(w, app, _state, set_status, set_btn, set_progress, _ui),
            daemon=True,
        ).start()

    def on_apply() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        try:
            from src.ui.timeline_dialog import show_timeline_dialog
            choice = show_timeline_dialog(frame, app.project)
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", "#ff6b6b")
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice
        threading.Thread(
            target=apply_thread,
            args=(w, app, _state, set_status, set_btn, set_progress, _ui),
            daemon=True,
        ).start()

    def on_preview() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(
            target=preview_thread,
            args=(app, _state, set_status, set_btn),
            daemon=True,
        ).start()

    w["zoom_slider"].configure(command=lambda v: _ui(lambda: w["zoom_lbl"].configure(text=f"{int(v)}%")))
    w["analyze_btn"].configure(command=on_analyze)
    w["apply_btn"].configure(command=on_apply)
    w["preview_btn"].configure(command=on_preview)
