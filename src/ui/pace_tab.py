"""Pace Control tab — adjust editing intensity via a single slider."""

from __future__ import annotations
import threading
from typing import Any

from src.constants import COLORS
from src.ui._pace_build import build, _PACE_PRESETS, _WPM_ESTIMATE, _RETENTION_EST
from src.ui._pace_workers import apply_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {"timeline_choice": ("new", None)}

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
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

    def on_apply() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", COLORS.ERROR)
            return
        try:
            from src.ui.timeline_dialog import show_timeline_dialog
            choice = show_timeline_dialog(frame, app.project)
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", COLORS.ERROR)
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice
        threading.Thread(
            target=apply_thread,
            args=(w, app, _state, _PACE_PRESETS, set_status, _ui),
            daemon=True,
        ).start()

    w["slider"].configure(command=on_slider)
    w["apply_btn"].configure(command=on_apply)

    default_level = app.settings.get("default_pace", 5)
    w["slider"].set(default_level)
    _update(default_level)
