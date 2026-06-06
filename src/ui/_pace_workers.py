"""Background thread worker for the Pace Control tab.

Extracted from pace_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def apply_thread(
    w: dict,
    app: Any,
    _state: dict,
    pace_presets: dict,
    set_status: Callable,
    _ui: Callable,
) -> None:
    """Run Smart Cuts with the current pace-slider settings."""
    from src.smartcuts.cutter import apply_cuts

    _mode, _target_tl = _state["timeline_choice"]
    _ui(lambda: w["apply_btn"].configure(state="disabled"))
    try:
        level = int(round(w["slider"].get()))
        p = pace_presets.get(level, pace_presets[5])

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
