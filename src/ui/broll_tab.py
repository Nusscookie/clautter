"""B-Roll Assistant tab — local folder scan + online search (Pixabay/Pexels)."""

from __future__ import annotations
import threading
import tkinter.filedialog
from pathlib import Path
from typing import Any

from src.ui._broll_build import build, _set_textbox
from src.ui._broll_workers import (
    suggest_local_thread, search_online_thread,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "folder": "",
        "dl_folder": "",
        "clips": [],
        "suggestions": [],
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_search_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["search_status"].configure(text=msg, text_color=color))

    def set_suggestions(text: str) -> None:
        _ui(lambda: _set_textbox(w["suggestions"], text))

    def _set_readonly_entry(entry: Any, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.configure(state="readonly")

    # ── Hydrate from settings ───────────────────────────────────────
    saved_provider = str(app.settings.get("broll_provider", "Both"))
    if saved_provider not in ("Pixabay", "Pexels", "Both"):
        saved_provider = "Both"
    _ui(lambda: w["provider"].set(saved_provider))

    saved_top_n = int(app.settings.get("broll_top_n", 10) or 10)
    saved_top_n = max(5, min(15, saved_top_n))
    _ui(lambda v=saved_top_n: (
        w["top_n_slider"].set(v),
        w["top_n_value"].configure(text=str(int(v))),
    ))

    saved_dl = str(app.settings.get("last_broll_folder", "") or "")
    if not saved_dl:
        saved_dl = str(Path.home() / "broll_downloads")
    _state["dl_folder"] = saved_dl
    _ui(lambda v=saved_dl: _set_readonly_entry(w["dl_folder"], v))

    # ── Callbacks ──────────────────────────────────────────────────

    def on_browse() -> None:
        initial = str(app.settings.get("last_broll_folder", "") or Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select B-Roll folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["folder"] = path
        _set_readonly_entry(w["folder"], path)
        app.settings.set("last_broll_folder", path)
        set_status(f"Selected: {path}", "#4fc3f7")
        _ui(lambda: w["suggest_local_btn"].configure(state="normal"))

    def on_pick_dl_folder() -> None:
        initial = _state["dl_folder"] or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select download folder for B-roll clips",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["dl_folder"] = path
        _set_readonly_entry(w["dl_folder"], path)
        app.settings.set("last_broll_folder", path)
        set_search_status(f"Download folder: {path}", "#4fc3f7")

    def on_provider_change(value: str) -> None:
        app.settings.set("broll_provider", value)
        _refresh_search_button()

    def on_top_n_change(value: Any) -> None:
        n = int(round(float(value)))
        w["top_n_value"].configure(text=str(n))
        app.settings.set("broll_top_n", n)

    def _refresh_search_button() -> None:
        if not app.transcript:
            _ui(lambda: w["search_online_btn"].configure(state="disabled"))
            return
        provider = w["provider"].get()

        def _have(name: str) -> bool:
            return bool((app.settings.get(name, "") or "").strip())

        if provider == "Pixabay":
            ok = _have("pixabay_api_key")
        elif provider == "Pexels":
            ok = _have("pexels_api_key")
        else:  # "Both"
            ok = _have("pixabay_api_key") and _have("pexels_api_key")
        state = "normal" if ok else "disabled"
        _ui(lambda s=state: w["search_online_btn"].configure(state=s))

    def on_place() -> None:
        set_status(
            "Auto Place coming in a future update — will work for both local and online B-roll.",
            "#ffa726",
        )

    def on_search_online() -> None:
        if not app.transcript:
            set_search_status("No transcript. Generate one in the Subtitles tab first.", "#ff6b6b")
            return
        provider = w["provider"].get()
        pairs: list[tuple[str, str]] = []
        missing: list[str] = []
        if provider in ("Pixabay", "Both"):
            k = (app.settings.get("pixabay_api_key", "") or "").strip()
            if k:
                pairs.append(("Pixabay", k))
            else:
                missing.append("Pixabay")
        if provider in ("Pexels", "Both"):
            k = (app.settings.get("pexels_api_key", "") or "").strip()
            if k:
                pairs.append(("Pexels", k))
            else:
                missing.append("Pexels")
        if missing:
            set_search_status(
                f"Missing key(s): {', '.join(missing)}. Add in Settings (⚙ top-right).",
                "#ff6b6b",
            )
            return
        if not pairs:
            set_search_status("Select a provider first.", "#ff6b6b")
            return
        _ui(lambda: w["search_online_btn"].configure(state="disabled"))
        set_search_status("Searching…", "#4fc3f7")
        threading.Thread(
            target=search_online_thread,
            args=(w, frame, app, _state, pairs,
                  set_search_status, set_status, _ui),
            daemon=True,
        ).start()

    # ── Wire commands ──────────────────────────────────────────────
    w["browse_btn"].configure(command=on_browse)
    w["dl_folder_btn"].configure(command=on_pick_dl_folder)
    w["provider"].configure(command=on_provider_change)
    w["top_n_slider"].configure(command=on_top_n_change)
    w["suggest_local_btn"].configure(command=lambda: threading.Thread(
        target=suggest_local_thread,
        args=(w, app, _state, set_status, set_suggestions, _ui),
        daemon=True).start())
    w["place_btn"].configure(command=on_place)
    w["search_online_btn"].configure(command=on_search_online)

    # Initial state for the search button (disabled until transcript + key)
    _refresh_search_button()
