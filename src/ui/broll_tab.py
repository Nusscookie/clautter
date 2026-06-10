"""B-Roll Assistant tab — Manual and Autonomous modes."""

from __future__ import annotations
import threading
import tkinter.filedialog
from pathlib import Path
from typing import Any

from src.ui._broll_build import build, _set_textbox
from src.ui._broll_workers import (
    suggest_local_thread, search_online_thread, autonomous_thread,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "folder": "",
        "dl_folder": "",
        "auto_folder": "",
        "auto_dl_folder": "",
        "clips": [],
        "suggestions": [],
        "auto_running": False,
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_search_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["search_status"].configure(text=msg, text_color=color))

    def set_suggestions(text: str) -> None:
        _ui(lambda: _set_textbox(w["suggestions"], text))

    def set_auto_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["auto_status"].configure(text=msg, text_color=color))

    def _set_readonly_entry(entry: Any, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.configure(state="readonly")

    # ── Mode toggle ─────────────────────────────────────────────────

    def on_mode_change(value: str) -> None:
        app.settings.set("broll_mode", value)
        if value == "Manual":
            w["auto_container"].pack_forget()
            w["manual_container"].pack(fill="x")
        else:
            w["manual_container"].pack_forget()
            w["auto_container"].pack(fill="x")
            _refresh_auto_run_btn()

    w["mode_toggle"].configure(command=on_mode_change)

    # ── Hydrate manual settings ─────────────────────────────────────
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

    # ── Hydrate autonomous settings ─────────────────────────────────
    auto_local = bool(app.settings.get("broll_auto_use_local", True))
    auto_online = bool(app.settings.get("broll_auto_use_online", True))
    from src.utils.llm_providers import available_providers
    auto_cps = str(app.settings.get("broll_auto_clips_per_segment", 1))
    auto_provider = str(app.settings.get("broll_auto_provider", "Both"))
    auto_dl = str(app.settings.get("broll_auto_dl_folder", "") or str(Path.home() / "broll_downloads"))
    auto_folder = str(app.settings.get("last_broll_folder", ""))
    auto_max_clips = int(app.settings.get("broll_auto_max_clips", 10) or 10)
    auto_max_clips = max(1, min(30, auto_max_clips))

    _state["auto_dl_folder"] = auto_dl
    _state["auto_folder"] = auto_folder

    auto_fill_frame = bool(app.settings.get("broll_auto_fill_frame", False))
    auto_natural = bool(app.settings.get("broll_natural_placement", True))

    def _refresh_llm_mode() -> None:
        """Populate the autonomous LLM-mode dropdown from currently-keyed providers.

        Preserves the live selection if still valid, else the saved value, else "Off".
        """
        vals = ["Off"] + available_providers(app.settings)
        try:
            current = w["auto_llm_mode"].get()
        except Exception:
            current = ""
        saved = str(app.settings.get("broll_llm_mode", "Off"))
        chosen = current if current in vals else (saved if saved in vals else "Off")
        _ui(lambda: (
            w["auto_llm_mode"].configure(values=vals),
            w["auto_llm_mode"].set(chosen),
        ))

    def _hydrate_auto() -> None:
        if auto_local:
            w["auto_use_local"].select()
        if auto_online:
            w["auto_use_online"].select()
        _refresh_llm_mode()
        if auto_cps in ("1", "2", "3"):
            w["auto_clips_per_seg"].set(auto_cps)
        if auto_provider in ("Pixabay", "Pexels", "Both"):
            w["auto_provider"].set(auto_provider)
        if auto_dl:
            _set_readonly_entry(w["auto_dl_folder"], auto_dl)
        if auto_folder:
            _set_readonly_entry(w["auto_folder"], auto_folder)
        w["auto_max_clips"].set(auto_max_clips)
        w["auto_max_clips_value"].configure(text=str(int(auto_max_clips)))
        if auto_fill_frame:
            w["auto_fill_frame"].select()
        if auto_natural:
            w["auto_natural_placement"].select()

    _ui(_hydrate_auto)

    # ── Restore mode ─────────────────────────────────────────────────
    saved_mode = str(app.settings.get("broll_mode", "Manual"))
    if saved_mode not in ("Manual", "Autonomous"):
        saved_mode = "Manual"

    def _restore_mode() -> None:
        w["mode_toggle"].set(saved_mode)
        on_mode_change(saved_mode)

    _ui(_restore_mode)

    # ── Manual callbacks ────────────────────────────────────────────

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
        set_status(f"Selected: {path}", "#D97757")
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
        set_search_status(f"Download folder: {path}", "#D97757")

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
        else:
            ok = _have("pixabay_api_key") and _have("pexels_api_key")
        state = "normal" if ok else "disabled"
        _ui(lambda s=state: w["search_online_btn"].configure(state=s))

    def on_place() -> None:
        set_status(
            "Auto Place coming in a future update — will work for both local and online B-roll.",
            "#E8903A",
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
        set_search_status("Searching…", "#D97757")
        threading.Thread(
            target=search_online_thread,
            args=(w, frame, app, _state, pairs,
                  set_search_status, set_status, _ui),
            daemon=True,
        ).start()

    # ── Autonomous callbacks ────────────────────────────────────────

    def _refresh_auto_run_btn() -> None:
        use_local = w["auto_use_local"].get()
        use_online = w["auto_use_online"].get()
        has_folder = bool(_state.get("auto_folder", "").strip())
        has_dl = bool(_state.get("auto_dl_folder", "").strip())
        has_transcript = bool(app.transcript)

        ok = (
            has_transcript
            and (not use_local or has_folder)
            and (not use_online or has_dl)
            and (use_local or use_online)
        )
        _ui(lambda s=("normal" if ok else "disabled"):
            w["auto_run_btn"].configure(state=s))

    def on_auto_browse() -> None:
        initial = _state.get("auto_folder", "") or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select local B-Roll folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["auto_folder"] = path
        _set_readonly_entry(w["auto_folder"], path)
        app.settings.set("last_broll_folder", path)
        _refresh_auto_run_btn()

    def on_auto_dl_browse() -> None:
        initial = _state.get("auto_dl_folder", "") or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select download folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["auto_dl_folder"] = path
        _set_readonly_entry(w["auto_dl_folder"], path)
        app.settings.set("broll_auto_dl_folder", path)
        _refresh_auto_run_btn()

    def on_auto_source_change() -> None:
        app.settings.set("broll_auto_use_local", bool(w["auto_use_local"].get()))
        app.settings.set("broll_auto_use_online", bool(w["auto_use_online"].get()))
        _refresh_auto_run_btn()

    def on_auto_llm_mode_change(value: str) -> None:
        app.settings.set("broll_llm_mode", value)

    def on_auto_provider_change(value: str) -> None:
        app.settings.set("broll_auto_provider", value)

    def on_auto_cps_change(value: str) -> None:
        app.settings.set("broll_auto_clips_per_segment", int(value))

    def on_auto_max_clips_change(value: Any) -> None:
        n = int(round(float(value)))
        w["auto_max_clips_value"].configure(text=str(n))
        app.settings.set("broll_auto_max_clips", n)

    def on_auto_fill_frame_change() -> None:
        app.settings.set("broll_auto_fill_frame", bool(w["auto_fill_frame"].get()))

    def on_auto_natural_change() -> None:
        app.settings.set("broll_natural_placement", bool(w["auto_natural_placement"].get()))

    def on_auto_run() -> None:
        if _state.get("auto_running"):
            return
        if not app.transcript:
            set_auto_status("No transcript — generate one in the Subtitles tab first.", "#ff6b6b")
            return

        use_local = bool(w["auto_use_local"].get())
        use_online = bool(w["auto_use_online"].get())
        local_folder = _state.get("auto_folder", "").strip() if use_local else None
        dl_folder = _state.get("auto_dl_folder", "").strip() or str(Path.home() / "broll_downloads")

        provider_val = w["auto_provider"].get()
        providers: list[tuple[str, str]] = []
        if use_online:
            if provider_val in ("Pixabay", "Both"):
                k = (app.settings.get("pixabay_api_key", "") or "").strip()
                if k:
                    providers.append(("Pixabay", k))
            if provider_val in ("Pexels", "Both"):
                k = (app.settings.get("pexels_api_key", "") or "").strip()
                if k:
                    providers.append(("Pexels", k))

        llm_sel = w["auto_llm_mode"].get()
        llm_director = llm_sel != "Off"
        llm_provider = llm_sel if llm_director else None
        cloud_rerank = False
        clips_per_seg = int(w["auto_clips_per_seg"].get() or 1)
        max_clips = int(round(float(w["auto_max_clips"].get())))
        fill_frame = bool(w["auto_fill_frame"].get())
        natural_placement = bool(w["auto_natural_placement"].get())
        no_start_broll = bool(app.settings.get("broll_no_start_broll", True))
        intro_skip_sec = float(app.settings.get("broll_intro_skip_sec", 8.0))
        min_gap_sec = float(app.settings.get("broll_min_gap_sec", 5.0))
        max_broll_duration = float(app.settings.get("broll_max_broll_duration", 5.0))

        _state["auto_running"] = True
        _ui(lambda: w["auto_run_btn"].configure(state="disabled"))
        _ui(lambda: w["auto_progress"].pack(in_=w["auto_progress_frame"], fill="x"))
        _ui(lambda: w["auto_progress"].set(0))

        def _on_progress(msg: str, frac: float) -> None:
            set_auto_status(msg)
            _ui(lambda f=frac: w["auto_progress"].set(f))

        threading.Thread(
            target=autonomous_thread,
            args=(w, frame, app, _state, local_folder, providers, dl_folder,
                  cloud_rerank, clips_per_seg, max_clips, _on_progress, set_auto_status, _ui,
                  llm_director, fill_frame, natural_placement, no_start_broll,
                  intro_skip_sec, min_gap_sec, max_broll_duration, llm_provider),
            daemon=True,
        ).start()

    # ── Wire commands ───────────────────────────────────────────────
    # Manual
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

    # Autonomous
    w["auto_browse_btn"].configure(command=on_auto_browse)
    w["auto_dl_browse_btn"].configure(command=on_auto_dl_browse)
    w["auto_use_local"].configure(command=on_auto_source_change)
    w["auto_use_online"].configure(command=on_auto_source_change)
    w["auto_llm_mode"].configure(command=on_auto_llm_mode_change)
    w["auto_provider"].configure(command=on_auto_provider_change)
    w["auto_clips_per_seg"].configure(command=on_auto_cps_change)
    w["auto_max_clips"].configure(command=on_auto_max_clips_change)
    w["auto_fill_frame"].configure(command=on_auto_fill_frame_change)
    w["auto_natural_placement"].configure(command=on_auto_natural_change)
    w["auto_run_btn"].configure(command=on_auto_run)

    # Initial state
    _refresh_search_button()
    _refresh_auto_run_btn()

    # Live refresh when Settings → Apply adds/changes a key (no restart needed)
    app.on_settings_changed(_refresh_llm_mode)
    app.on_settings_changed(_refresh_search_button)
    app.on_settings_changed(_refresh_auto_run_btn)
