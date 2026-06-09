"""Music & SFX tab — mood-matched background music and auto-placed sound effects."""

from __future__ import annotations
import threading
import tkinter.filedialog
from pathlib import Path
from typing import Any

from src.ui._music_build import build
from src.music._music_workers import music_thread, sfx_thread
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "running":           False,
        "sfx_running":       False,
        "dl_folder":         "",
        "local_music_folder": "",
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_sfx_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["sfx_status"].configure(text=msg, text_color=color))

    def set_progress(pct: int, visible: bool = True) -> None:
        def _do() -> None:
            if visible:
                w["music_progress"].pack(in_=w["music_progress_frame"], fill="x")
                w["music_progress"].set(pct / 100)
            else:
                w["music_progress"].pack_forget()
        _ui(_do)

    def set_sfx_progress(pct: int, visible: bool = True) -> None:
        def _do() -> None:
            if visible:
                w["sfx_progress"].pack(in_=w["sfx_progress_frame"], fill="x")
                w["sfx_progress"].set(pct / 100)
            else:
                w["sfx_progress"].pack_forget()
        _ui(_do)

    def _set_readonly_entry(entry: Any, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.configure(state="readonly")

    # ── Sections slider label update ────────────────────────────────
    def on_sections_slider(val: float) -> None:
        w["n_sections_lbl"].configure(text=str(int(val)))

    w["n_sections_slider"].configure(command=on_sections_slider)

    # ── Music source toggle: show/hide local folder row ─────────────
    def _update_local_music_row_visibility(source: str) -> None:
        if source in ("Local", "Both"):
            w["local_music_row"].pack(fill="x", padx=10, pady=2, before=w["dl_row"])
        else:
            w["local_music_row"].pack_forget()

    def on_music_source(value: str) -> None:
        app.settings.set("music_source", value.lower())
        _update_local_music_row_visibility(value)

    w["music_source"].configure(command=on_music_source)

    # ── Music mode toggle: show/hide sections row ────────────────────
    def on_music_mode(value: str) -> None:
        app.settings.set("music_mode", "segments" if value == "Segments" else "single")
        if value == "Segments":
            w["n_sections_frame"].pack(fill="x", padx=10, pady=2, before=w["dl_row"])
        else:
            w["n_sections_frame"].pack_forget()

    w["music_mode"].configure(command=on_music_mode)

    def on_mood_mode(value: str) -> None:
        app.settings.set("music_mood_mode", "llm" if value == "LLM" else "keywords")

    w["mood_mode"].configure(command=on_mood_mode)

    # ── Hydrate settings ─────────────────────────────────────────────
    saved_dl = str(app.settings.get("music_dl_folder", "") or
                   str(Path.home() / "audio_downloads"))
    _state["dl_folder"] = saved_dl
    _ui(lambda: _set_readonly_entry(w["dl_folder_entry"], saved_dl))

    saved_music_mode = str(app.settings.get("music_mode", "single") or "single")
    _ui(lambda: w["music_mode"].set("Segments" if saved_music_mode == "segments" else "Single Track"))

    saved_mood_mode = str(app.settings.get("music_mood_mode", "keywords") or "keywords")
    _ui(lambda: w["mood_mode"].set("LLM" if saved_mood_mode == "llm" else "Keywords"))

    saved_n = max(1, min(5, int(app.settings.get("music_n_sections", 3) or 3)))
    _ui(lambda: (
        w["n_sections_slider"].set(saved_n),
        w["n_sections_lbl"].configure(text=str(saved_n)),
    ))

    saved_music_source = str(app.settings.get("music_source", "jamendo") or "jamendo")
    _source_label = {"jamendo": "Jamendo", "local": "Local", "both": "Both"}.get(saved_music_source, "Jamendo")
    _ui(lambda: w["music_source"].set(_source_label))
    _update_local_music_row_visibility(_source_label)

    saved_local_music = str(app.settings.get("music_local_folder", "") or "")
    _state["local_music_folder"] = saved_local_music
    if saved_local_music:
        _ui(lambda: _set_readonly_entry(w["local_music_entry"], saved_local_music))

    saved_sfx_folder = str(app.settings.get("sfx_local_folder", "") or "")
    if saved_sfx_folder:
        _ui(lambda: _set_readonly_entry(w["sfx_folder_entry"], saved_sfx_folder))

    saved_cuts  = bool(app.settings.get("sfx_use_cuts",  True))
    saved_zooms = bool(app.settings.get("sfx_use_zooms", True))
    saved_broll = bool(app.settings.get("sfx_use_broll", True))
    _ui(lambda: (
        w["use_cuts_var"].set(1 if saved_cuts else 0),
        w["use_zooms_var"].set(1 if saved_zooms else 0),
        w["use_broll_var"].set(1 if saved_broll else 0),
    ))

    # If segments mode was saved, show sections row
    if saved_music_mode == "segments":
        _ui(lambda: w["n_sections_frame"].pack(fill="x", padx=10, pady=2, before=w["dl_row"]))

    # ── Browse callbacks ─────────────────────────────────────────────
    def on_browse_dl() -> None:
        folder = tkinter.filedialog.askdirectory(title="Select Music Download Folder",
                                                  initialdir=_state["dl_folder"] or str(Path.home()))
        if folder:
            _state["dl_folder"] = folder
            app.settings.set("music_dl_folder", folder)
            _set_readonly_entry(w["dl_folder_entry"], folder)

    def on_browse_local_music() -> None:
        folder = tkinter.filedialog.askdirectory(
            title="Select Local Music Folder",
            initialdir=_state["local_music_folder"] or str(Path.home()),
        )
        if folder:
            _state["local_music_folder"] = folder
            app.settings.set("music_local_folder", folder)
            _set_readonly_entry(w["local_music_entry"], folder)

    def on_browse_sfx() -> None:
        folder = tkinter.filedialog.askdirectory(title="Select Local SFX Folder")
        if folder:
            app.settings.set("sfx_local_folder", folder)
            _set_readonly_entry(w["sfx_folder_entry"], folder)

    w["dl_folder_btn"].configure(command=on_browse_dl)
    w["local_music_btn"].configure(command=on_browse_local_music)
    w["sfx_folder_btn"].configure(command=on_browse_sfx)

    # ── Run Music ────────────────────────────────────────────────────
    def on_run_music() -> None:
        music_source_now = w["music_source"].get().lower()
        jamendo_id = (app.settings.get("jamendo_client_id", "") or "").strip()
        if music_source_now != "local" and not jamendo_id:
            set_status("Jamendo Client ID required — add it in Settings (⚙).", "#ff6b6b")
            return
        if music_source_now in ("local", "both") and not _state["local_music_folder"]:
            set_status("Local Music Folder not set — browse to select one.", "#ff6b6b")
            return
        if not app.transcript:
            set_status("No transcript — generate one in the Subtitles tab first.", "#ff6b6b")
            return
        if _state["running"]:
            return

        _state["running"] = True
        _ui(lambda: w["run_music_btn"].configure(state="disabled"))

        music_mode    = "segments" if w["music_mode"].get() == "Segments" else "single"
        mood_mode     = "llm" if w["mood_mode"].get() == "LLM" else "keywords"
        n_sections    = max(1, min(5, int(w["n_sections_slider"].get())))
        dl_folder     = _state["dl_folder"] or str(Path.home() / "audio_downloads")
        music_source  = w["music_source"].get().lower()
        local_music   = _state["local_music_folder"] or None

        app.settings.set("music_n_sections", n_sections)

        threading.Thread(
            target=music_thread,
            kwargs=dict(
                frame=frame, app=app, state=_state,
                jamendo_client_id=jamendo_id, download_folder=dl_folder,
                music_mode=music_mode, mood_mode=mood_mode, n_sections=n_sections,
                music_source=music_source, local_music_folder=local_music,
                set_status=set_status, set_progress=set_progress, _ui=_ui, w=w,
            ),
            daemon=True,
        ).start()

    # ── Run SFX ──────────────────────────────────────────────────────
    def on_run_sfx() -> None:
        freesound_key = (app.settings.get("freesound_api_key", "") or "").strip()
        if not freesound_key:
            set_sfx_status("Freesound API key required — add it in Settings (⚙).", "#ff6b6b")
            return
        if _state["sfx_running"]:
            return

        _state["sfx_running"] = True
        _ui(lambda: w["run_sfx_btn"].configure(state="disabled"))

        use_cuts  = bool(w["use_cuts_var"].get())
        use_zooms = bool(w["use_zooms_var"].get())
        use_broll = bool(w["use_broll_var"].get())
        sfx_local = w["sfx_folder_entry"].get().strip() or None
        dl_folder = _state["dl_folder"] or str(Path.home() / "audio_downloads")

        app.settings.set("sfx_use_cuts",  use_cuts)
        app.settings.set("sfx_use_zooms", use_zooms)
        app.settings.set("sfx_use_broll", use_broll)

        threading.Thread(
            target=sfx_thread,
            kwargs=dict(
                frame=frame, app=app, state=_state,
                freesound_api_key=freesound_key, download_folder=dl_folder,
                use_cuts=use_cuts, use_zooms=use_zooms, use_broll=use_broll,
                local_sfx_folder=sfx_local,
                set_sfx_status=set_sfx_status, set_sfx_progress=set_sfx_progress,
                _ui=_ui, w=w,
            ),
            daemon=True,
        ).start()

    w["run_music_btn"].configure(command=on_run_music)
    w["run_sfx_btn"].configure(command=on_run_sfx)
