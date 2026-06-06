"""Smart Cuts tab — silence detection and removal."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.ui._smartcuts_data import PACE_PRESETS
from src.ui._smartcuts_workers import analyze_thread, apply_thread, preview_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SMART CUTS  —  Remove silences from selected clips",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Pace preset card ──
    pace_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    pace_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(pace_card, text="PACE PRESET",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    slider_row = ctk.CTkFrame(pace_card, fg_color="transparent")
    slider_row.pack(fill="x", padx=10, pady=(0, 4))
    slider_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(slider_row, text="Slow", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 8))
    w["pace_slider"] = ctk.CTkSlider(slider_row, from_=1, to=10, number_of_steps=9)
    w["pace_slider"].set(5)
    w["pace_slider"].grid(row=0, column=1, sticky="ew")
    ctk.CTkLabel(slider_row, text="Fast", text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(8, 0))

    info_row = ctk.CTkFrame(pace_card, fg_color="transparent")
    info_row.pack(fill="x", padx=10, pady=(0, 10))

    w["pace_level_lbl"] = ctk.CTkLabel(info_row, text="5",
                                        font=ctk.CTkFont(size=22, weight="bold"),
                                        text_color="#4fc3f7", width=36, anchor="w")
    w["pace_level_lbl"].pack(side="left")

    desc_col = ctk.CTkFrame(info_row, fg_color="transparent")
    desc_col.pack(side="left", padx=(6, 0), fill="x", expand=True)

    w["pace_name_lbl"] = ctk.CTkLabel(desc_col, text="YouTube",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       text_color="#ffffff", anchor="w")
    w["pace_name_lbl"].pack(fill="x")

    w["pace_desc_lbl"] = ctk.CTkLabel(desc_col,
                                       text="Standard YouTube pacing — best all-round starting point",
                                       font=ctk.CTkFont(size=10), text_color="#aaaaaa",
                                       anchor="w", wraplength=600)
    w["pace_desc_lbl"].pack(fill="x")

    # ── Settings card ──
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(card, text="DETECTION SETTINGS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    w["threshold"] = _labeled_entry(card, "Silence Threshold", "-35", "dB")
    w["min_dur"]   = _labeled_entry(card, "Min Silence Duration", "350", "ms")
    w["padding"]   = _labeled_entry(card, "Breathing Room (padding)", "120", "ms each side")

    ctk.CTkFrame(card, height=1, fg_color="#333333", corner_radius=0).pack(
        fill="x", padx=10, pady=(6, 2))
    w["retake_cb"] = ctk.CTkCheckBox(
        card,
        text="Detect & isolate retakes  (uses Whisper — adds ~30 s)",
        font=ctk.CTkFont(size=11),
        text_color="#aaaaaa",
        checkbox_width=16,
        checkbox_height=16,
    )
    w["retake_cb"].pack(anchor="w", padx=10, pady=(2, 10))

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

    w["apply_btn"] = ctk.CTkButton(btn_row, text="Apply Cuts",
                                    fg_color="#1565c0", hover_color="#1976d2",
                                    state="disabled")
    w["apply_btn"].grid(row=0, column=2, padx=(3, 0), sticky="ew")

    # ── Progress ──
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(2, 0))

    w["status"] = ctk.CTkLabel(
        parent,
        text="Ready. Select clips in the Edit page timeline, then click Analyze.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800,
    )
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=6)

    # ── Results ──
    ctk.CTkLabel(parent, text="ANALYSIS RESULTS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    results_row = ctk.CTkFrame(parent, fg_color="transparent")
    results_row.pack(fill="x", padx=10, pady=2)
    results_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["found_count"] = _stat_card(results_row, "Silences Found", "0", "#4fc3f7")
    w["found_count"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["time_saved"] = _stat_card(results_row, "Estimated Time Saved", "0.0 s", "#66bb6a")
    w["time_saved"].grid(row=0, column=1, padx=4, sticky="ew")
    w["clips_count"] = _stat_card(results_row, "Clips Analyzed", "0", "#ffa726")
    w["clips_count"].grid(row=0, column=2, padx=(4, 0), sticky="ew")

    w["new_timeline_lbl"] = ctk.CTkLabel(
        parent, text="", font=ctk.CTkFont(size=11), text_color="#66bb6a", anchor="w")
    w["new_timeline_lbl"].pack(fill="x", padx=12, pady=(6, 12))

    parent._w = w


def _labeled_entry(parent: Any, label: str, default: str, unit: str) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=10, pady=2)
    row.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(row, text=label, anchor="w").grid(row=0, column=0, sticky="w")
    entry = ctk.CTkEntry(row, width=90, justify="center")
    entry.insert(0, default)
    entry.grid(row=0, column=1, padx=6)
    ctk.CTkLabel(row, text=unit, text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2)
    return entry


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
        "silence_regions": [],
        "total_silences": 0,
        "total_time_saved": 0.0,
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

    def on_pace_slider(value: float) -> None:
        level = int(round(value))
        p = PACE_PRESETS.get(level, PACE_PRESETS[5])
        w["pace_level_lbl"].configure(text=str(level))
        w["pace_name_lbl"].configure(text=p["label"])
        w["pace_desc_lbl"].configure(text=p["desc"])
        w["threshold"].delete(0, "end")
        w["threshold"].insert(0, str(p["threshold_db"]))
        w["min_dur"].delete(0, "end")
        w["min_dur"].insert(0, str(p["min_silence_ms"]))
        app.settings.set("default_pace", level)

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

    w["analyze_btn"].configure(command=on_analyze)
    w["apply_btn"].configure(command=on_apply)
    w["preview_btn"].configure(command=on_preview)
    w["pace_slider"].configure(command=on_pace_slider)

    default_pace = app.settings.get("default_pace", 5)
    w["pace_slider"].set(default_pace)
    on_pace_slider(default_pace)
