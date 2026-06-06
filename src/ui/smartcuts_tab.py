"""Smart Cuts tab — silence detection and removal."""

from __future__ import annotations
import threading
from typing import Any

from src.ui._smartcuts_build import build
from src.ui._smartcuts_data import PACE_PRESETS
from src.ui._smartcuts_workers import analyze_thread, apply_thread, preview_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


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
