"""Smart Cuts tab — silence detection and removal."""

from __future__ import annotations
import threading
from typing import Any

from src.constants import COLORS
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

    def set_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
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

    def _swap_threshold_field(method_key: str) -> None:
        def _apply() -> None:
            if method_key == "vad":
                w["threshold_row"].pack_forget()
                w["vad_threshold_row"].pack(fill="x")
            else:
                w["vad_threshold_row"].pack_forget()
                w["threshold_row"].pack(fill="x")
        _ui(_apply)

    def on_pace_slider(value: float) -> None:
        level = int(round(value))
        p = PACE_PRESETS.get(level, PACE_PRESETS[5])
        w["pace_level_lbl"].configure(text=str(level))
        w["pace_name_lbl"].configure(text=p["label"])
        w["pace_desc_lbl"].configure(text=p["desc"])
        w["threshold"].delete(0, "end")
        w["threshold"].insert(0, str(p["threshold_db"]))
        w["vad_threshold"].delete(0, "end")
        w["vad_threshold"].insert(0, str(p["vad_threshold"]))
        w["min_dur"].delete(0, "end")
        w["min_dur"].insert(0, str(p["min_silence_ms"]))
        w["padding"].delete(0, "end")
        w["padding"].insert(0, str(p["padding_ms"]))
        app.settings.set("default_pace", level)
        # Settings changed — previous results are stale
        if _state.get("total_silences", 0) > 0 or _state.get("clips"):
            w["found_count"]._val.configure(text="—")
            w["time_saved"]._val.configure(text="—")
            w["clips_count"]._val.configure(text="—")
            w["apply_btn"].configure(state="disabled")
            w["preview_btn"].configure(state="disabled")
            w["status"].configure(
                text="Settings changed — click Analyze to update results.",
                text_color=COLORS.WARNING,
            )

    def _on_retake_cb_toggle() -> None:
        if w["retake_cb"].get():
            w["delete_retakes_cb"].configure(state="normal")
        else:
            w["delete_retakes_cb"].deselect()
            w["delete_retakes_cb"].configure(state="disabled")

    def on_analyze() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", COLORS.ERROR)
            return
        threading.Thread(
            target=analyze_thread,
            args=(w, app, _state, set_status, set_btn, set_progress, _ui),
            daemon=True,
        ).start()

    def on_apply() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", COLORS.ERROR)
            return
        try:
            from src.ui.timeline_dialog import find_named_video_track, show_timeline_dialog, show_warning_dialog
            _retake_track_idx: int | None = None
            _has_other_tracks = False
            if app.timeline:
                _retake_track_idx = find_named_video_track(app.timeline, "Retakes")
                try:
                    _vcount = app.timeline.GetTrackCount("video")
                    _has_other_tracks = any(
                        bool(app.timeline.GetItemListInTrack("video", _ti))
                        for _ti in range(2, _vcount + 1)
                    )
                except Exception:
                    pass
            if _has_other_tracks:
                if not show_warning_dialog(
                    frame,
                    "This timeline has B-Roll or Subtitle tracks above Video 1.\n\n"
                    "After cuts are applied, those tracks will be out of sync "
                    "and need to be re-synced manually.",
                    title="Tracks will be out of sync",
                ):
                    set_status("Apply cancelled.", COLORS.TEXT_MUTED)
                    return
            choice = show_timeline_dialog(
                frame, app.project,
                current_timeline=app.timeline,
                secondary_section={
                    "detect": _retake_track_idx is not None,
                    "label": "Retake layer",
                    "existing_text": f"Use existing 'Retakes' layer (track {_retake_track_idx})",
                    "new_text": "Create new retake layer above",
                    "key": "track_mode",
                } if app.timeline else None,
            )
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", COLORS.ERROR)
            return
        if choice is None:
            set_status("Apply cancelled.", COLORS.TEXT_MUTED)
            return
        _state["timeline_choice"] = choice["timeline"]
        _state["track_mode"] = choice.get("track_mode", "new")
        _state["retake_track_index"] = (
            _retake_track_idx if choice.get("track_mode") == "existing" else None
        )
        threading.Thread(
            target=apply_thread,
            args=(w, app, _state, set_status, set_btn, set_progress, _ui),
            daemon=True,
        ).start()

    def on_preview() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", COLORS.ERROR)
            return
        threading.Thread(
            target=preview_thread,
            args=(app, _state, set_status, set_btn),
            daemon=True,
        ).start()

    saved_silence = str(app.settings.get("smartcuts_silence_method", "vad"))
    _swap_threshold_field(saved_silence)

    w["analyze_btn"].configure(command=on_analyze)
    w["apply_btn"].configure(command=on_apply)
    w["preview_btn"].configure(command=on_preview)
    w["pace_slider"].configure(command=on_pace_slider)
    w["retake_cb"].configure(command=_on_retake_cb_toggle)

    default_pace = app.settings.get("default_pace", 5)
    w["pace_slider"].set(default_pace)
    on_pace_slider(default_pace)
