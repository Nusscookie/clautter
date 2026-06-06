"""B-Roll Assistant tab — folder scan + transcript keyword matching."""

from __future__ import annotations
import threading
from typing import Any

from src.ui._broll_build import build, _set_textbox
from src.ui._broll_workers import scan_thread, suggest_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "folder": "",
        "clips": [],
        "suggestions": [],
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_suggestions(text: str) -> None:
        _ui(lambda: _set_textbox(w["suggestions"], text))

    def on_browse() -> None:
        w["folder"].configure(state="normal")
        set_status("Type or paste the folder path, then click Scan Folder.", "#4fc3f7")
        w["scan_btn"].configure(state="normal")

    def on_analyze() -> None:
        if not app.transcript:
            set_status("No transcript found. Generate one in the Subtitles tab first.", "#ff6b6b")
            return
        set_status(f"Transcript has {len(app.transcript)} words. Ready to suggest B-roll.", "#66bb6a")
        w["suggest_btn"].configure(state="normal")

    def on_place() -> None:
        set_status(
            "Auto Place is coming in a future update. "
            "Use the suggestions above to manually place B-roll.",
            "#ffa726",
        )

    w["browse_btn"].configure(command=on_browse)
    w["scan_btn"].configure(command=lambda: threading.Thread(
        target=scan_thread, args=(w, _state, set_status, _ui), daemon=True).start())
    w["analyze_btn"].configure(command=on_analyze)
    w["suggest_btn"].configure(command=lambda: threading.Thread(
        target=suggest_thread, args=(w, app, _state, set_status, set_suggestions, _ui),
        daemon=True).start())
    w["place_btn"].configure(command=on_place)
