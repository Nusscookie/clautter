"""Auto Zooms tab — face-detection or volume-peak-based zoom cuts."""

from __future__ import annotations
import threading
from typing import Any

from src.ui._zooms_build import build
from src.ui._zooms_workers import analyze_thread, apply_thread, preview_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "zoom_points": [],
        "clips": [],
        "timeline_choice": {"timeline": ("new", None)},
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

    def _toggle_mode_row(method: str) -> None:
        if method == "RMS Peaks":
            w["mode_row"].pack(fill="x", padx=10, pady=2)
            w["detect_note"].configure(text_color="#555555")
        else:
            w["mode_row"].pack_forget()
            w["detect_note"].configure(text_color="#888888")

    w["detect_method"].configure(command=lambda v: _ui(lambda: _toggle_mode_row(v)))
    w["zoom_slider"].configure(
        command=lambda v: _ui(lambda: w["zoom_lbl"].configure(text=f"{int(v)}%")))
    w["analyze_btn"].configure(command=on_analyze)
    w["apply_btn"].configure(command=on_apply)
    w["preview_btn"].configure(command=on_preview)
