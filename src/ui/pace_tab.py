"""Pace Control tab — adjust editing intensity via a single slider."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)

_PACE_PRESETS = {
    1:  {"threshold_db": -55, "min_silence_ms": 1500, "label": "Very Slow",
         "desc": "Documentary / cinematic — only remove very long pauses"},
    2:  {"threshold_db": -50, "min_silence_ms": 1200, "label": "Slow",
         "desc": "Long-form podcast / interview style"},
    3:  {"threshold_db": -45, "min_silence_ms": 900,  "label": "Relaxed",
         "desc": "Calm YouTube tutorial"},
    4:  {"threshold_db": -40, "min_silence_ms": 600,  "label": "Moderate",
         "desc": "Standard talking-head"},
    5:  {"threshold_db": -35, "min_silence_ms": 350,  "label": "YouTube",
         "desc": "Standard YouTube pacing — best all-round starting point"},
    6:  {"threshold_db": -33, "min_silence_ms": 280,  "label": "Crisp",
         "desc": "Tight YouTube / educational content"},
    7:  {"threshold_db": -30, "min_silence_ms": 220,  "label": "Snappy",
         "desc": "High-energy YouTube / commentary"},
    8:  {"threshold_db": -28, "min_silence_ms": 160,  "label": "Fast",
         "desc": "Instagram Reels / short-form"},
    9:  {"threshold_db": -25, "min_silence_ms": 120,  "label": "Very Fast",
         "desc": "TikTok-style aggressive cuts"},
    10: {"threshold_db": -22, "min_silence_ms": 80,   "label": "TikTok / Reels",
         "desc": "Maximum energy — every breath removed"},
}
_WPM_ESTIMATE  = {1: 100, 2: 115, 3: 125, 4: 135, 5: 145, 6: 155, 7: 165, 8: 175, 9: 185, 10: 200}
_RETENTION_EST = {1: 62,  2: 65,  3: 68,  4: 72,  5: 77,  6: 80,  7: 83,  8: 85,  9: 87,  10: 89}


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="PACE CONTROL  —  One slider for editing intensity",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Slider card ──
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    slider_row = ctk.CTkFrame(card, fg_color="transparent")
    slider_row.pack(fill="x", padx=12, pady=(12, 4))
    slider_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(slider_row, text="Slow", text_color="#888888").grid(row=0, column=0, padx=(0, 8))

    w["slider"] = ctk.CTkSlider(slider_row, from_=1, to=10, number_of_steps=9)
    w["slider"].set(5)
    w["slider"].grid(row=0, column=1, sticky="ew")

    ctk.CTkLabel(slider_row, text="Fast", text_color="#888888").grid(row=0, column=2, padx=(8, 0))

    info_row = ctk.CTkFrame(card, fg_color="transparent")
    info_row.pack(fill="x", padx=12, pady=(4, 12))

    w["level_lbl"] = ctk.CTkLabel(info_row, text="5",
                                   font=ctk.CTkFont(size=36, weight="bold"),
                                   text_color="#4fc3f7", width=56)
    w["level_lbl"].pack(side="left")

    desc_frame = ctk.CTkFrame(info_row, fg_color="transparent")
    desc_frame.pack(side="left", padx=8, fill="x", expand=True)

    w["pace_label"] = ctk.CTkLabel(desc_frame, text="YouTube",
                                    font=ctk.CTkFont(size=16, weight="bold"),
                                    text_color="#ffffff", anchor="w")
    w["pace_label"].pack(fill="x")

    w["pace_desc"] = ctk.CTkLabel(desc_frame,
                                   text="Standard YouTube pacing — best all-round starting point",
                                   font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w",
                                   wraplength=600)
    w["pace_desc"].pack(fill="x")

    # ── Auto-adjusted params ──
    params_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    params_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(params_card, text="AUTO-ADJUSTED PARAMETERS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    params_row = ctk.CTkFrame(params_card, fg_color="transparent")
    params_row.pack(fill="x", padx=10, pady=(0, 10))
    params_row.grid_columnconfigure((0, 1), weight=1)

    w["thresh_val"] = _mini_stat(params_row, "Threshold", "-35 dB", "#4fc3f7")
    w["thresh_val"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["dur_val"] = _mini_stat(params_row, "Min Silence", "350 ms", "#ffa726")
    w["dur_val"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    # ── Estimates ──
    est_row = ctk.CTkFrame(parent, fg_color="transparent")
    est_row.pack(fill="x", padx=10, pady=4)
    est_row.grid_columnconfigure((0, 1), weight=1)

    w["wpm_val"] = _mini_stat(est_row, "Est. Words Per Minute", "~145 WPM", "#66bb6a",
                               bg="#1b2838")
    w["wpm_val"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["retention_val"] = _mini_stat(est_row, "Est. Viewer Retention", "~77%", "#ab47bc",
                                     bg="#1b2838")
    w["retention_val"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    # ── Apply button ──
    w["apply_btn"] = ctk.CTkButton(
        parent,
        text="Apply Pace  (runs Smart Cuts with these settings)",
        fg_color="#1565c0", hover_color="#1976d2",
        font=ctk.CTkFont(size=13, weight="bold"),
        height=36,
    )
    w["apply_btn"].pack(fill="x", padx=10, pady=(8, 4))

    w["status"] = ctk.CTkLabel(
        parent, text="Adjust slider, then click Apply Pace.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w")
    w["status"].pack(fill="x", padx=12, pady=(0, 12))

    parent._w = w


def _mini_stat(parent: Any, label: str, default: str, color: str,
               bg: str = "#2a2a2a") -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=20, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color="#888888").pack(pady=(0, 8))
    card._val = val
    return card


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {"timeline_choice": ("new", None)}

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def _update(level: int) -> None:
        p = _PACE_PRESETS.get(level, _PACE_PRESETS[5])
        w["level_lbl"].configure(text=str(level))
        w["pace_label"].configure(text=p["label"])
        w["pace_desc"].configure(text=p["desc"])
        w["thresh_val"]._val.configure(text=f"{p['threshold_db']} dB")
        w["dur_val"]._val.configure(text=f"{p['min_silence_ms']} ms")
        w["wpm_val"]._val.configure(text=f"~{_WPM_ESTIMATE[level]} WPM")
        w["retention_val"]._val.configure(text=f"~{_RETENTION_EST[level]}%")

    def on_slider(value: float) -> None:
        _update(int(round(value)))

    def _apply_thread() -> None:
        from src.smartcuts.cutter import apply_cuts

        _mode, _target_tl = _state["timeline_choice"]
        _ui(lambda: w["apply_btn"].configure(state="disabled"))
        try:
            level = int(round(w["slider"].get()))
            p = _PACE_PRESETS.get(level, _PACE_PRESETS[5])

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                set_status("No clips found on Video Track 1.", "#ff6b6b")
                return

            def progress_cb(cur: int, total: int, msg: str) -> None:
                set_status(msg)

            if _target_tl is not None:
                set_status(f"Appending cuts to '{_target_tl.GetName()}'...")
            else:
                set_status("Creating new timeline with silence removed...")

            result = apply_cuts(
                resolve=app.resolve,
                timeline=app.timeline,
                clips=clips,
                threshold_db=float(p["threshold_db"]),
                min_duration_ms=float(p["min_silence_ms"]),
                padding_ms=120.0,
                progress_callback=progress_cb,
                target_timeline=_target_tl,
            )
            app.refresh_timeline()
            app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
            app.settings.add_stat("total_edits", 1)
            set_status(
                f"Done! Timeline '{result.new_timeline_name}' — {result.time_saved_sec:.1f}s removed.",
                "#66bb6a",
            )
        except Exception as e:
            log.error("Pace apply error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            _ui(lambda: w["apply_btn"].configure(state="normal"))

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
        threading.Thread(target=_apply_thread, daemon=True).start()

    w["slider"].configure(command=on_slider)
    w["apply_btn"].configure(command=on_apply)

    default_level = app.settings.get("default_pace", 5)
    w["slider"].set(default_level)
    _update(default_level)
