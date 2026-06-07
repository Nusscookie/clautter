"""B-Roll Assistant tab — local folder scan + online search (Pixabay/Pexels)."""

from __future__ import annotations
import threading
import tkinter.filedialog
from pathlib import Path
from typing import Any

from src.ui._broll_build import build, _set_textbox
from src.ui._broll_workers import (
    scan_thread, search_online_thread, suggest_thread,
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

    def set_provider_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["provider_status"].configure(text=msg, text_color=color))

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

    saved_pixabay = str(app.settings.get("pixabay_api_key", ""))
    if saved_pixabay:
        _ui(lambda v=saved_pixabay: w["pixabay_key"].insert(0, v))

    saved_pexels = str(app.settings.get("pexels_api_key", ""))
    if saved_pexels:
        _ui(lambda v=saved_pexels: w["pexels_key"].insert(0, v))

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

    _METHOD_LABELS: dict[str, str] = {
        "spacy":     "spaCy (en_core_web_sm)",
        "yake":      "YAKE",
        "keybert":   "KeyBERT",
        "frequency": "Frequency (no deps)",
    }
    _METHOD_KEYS: dict[str, str] = {v: k for k, v in _METHOD_LABELS.items()}

    saved_method = str(app.settings.get("broll_keyword_method", "keybert"))
    saved_method_label = _METHOD_LABELS.get(saved_method, "spaCy (en_core_web_sm)")
    _ui(lambda lbl=saved_method_label: w["keyword_method"].set(lbl))

    def _apply_provider_visibility(provider: str) -> None:
        """Show/hide the API-key input rows based on the chosen provider.
        Re-pack uses ``before=save_keys_btn`` so the row always lands
        above the Save Keys button — Tk's pack manager otherwise appends
        re-packed widgets to the end of the parent's pack list."""
        px_row = w.get("px_row")
        pex_row = w.get("pex_row")
        save_btn = w.get("save_keys_btn")
        if px_row is None or pex_row is None or save_btn is None:
            return

        def _show_px() -> None:
            px_row.pack(fill="x", padx=10, pady=(4, 2), before=save_btn)

        def _hide_px() -> None:
            px_row.pack_forget()

        def _show_pex() -> None:
            pex_row.pack(fill="x", padx=10, pady=(2, 4), before=save_btn)

        def _hide_pex() -> None:
            pex_row.pack_forget()

        if provider == "Pixabay":
            _ui(_show_px)
            _ui(_hide_pex)
        elif provider == "Pexels":
            _ui(_hide_px)
            _ui(_show_pex)
        else:  # "Both"
            _ui(_show_px)
            _ui(_show_pex)

    _ui(lambda v=saved_provider: _apply_provider_visibility(v))

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
        _ui(lambda: w["scan_btn"].configure(state="normal"))

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

    def _persist_keys(show_status: bool = False) -> None:
        provider = w["provider"].get()
        if provider in ("Pixabay", "Both"):
            val = w["pixabay_key"].get().strip()
            if val:
                app.settings.set("pixabay_api_key", val)
        if provider in ("Pexels", "Both"):
            val = w["pexels_key"].get().strip()
            if val:
                app.settings.set("pexels_api_key", val)
        app.settings.set("broll_provider", provider)
        if show_status:
            set_provider_status("Keys saved.", "#66bb6a")
        _refresh_search_button()

    def on_save_keys() -> None:
        _persist_keys(show_status=True)

    def on_provider_change(value: str) -> None:
        app.settings.set("broll_provider", value)
        _apply_provider_visibility(value)
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

    def on_analyze() -> None:
        if not app.transcript:
            set_status("No transcript found. Generate one in the Subtitles tab first.", "#ff6b6b")
            return
        set_status(f"Transcript has {len(app.transcript)} words. Ready to suggest B-roll.", "#66bb6a")
        _ui(lambda: w["suggest_btn"].configure(state="normal"))
        _refresh_search_button()

    def on_place() -> None:
        set_status(
            "Auto Place is coming in a future update. "
            "V2 will be renamed to 'B-roll' then. "
            "Use the suggestions or downloaded clips above to manually place B-roll.",
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
                f"Missing key(s): {', '.join(missing)}. Paste and Save first.",
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

    def on_advanced_toggle() -> None:
        adv = w["advanced_frame"]
        btn = w["advanced_toggle"]
        if adv.winfo_ismapped():
            adv.pack_forget()
            btn.configure(text="▶  ADVANCED SETTINGS")
        else:
            adv.pack(fill="x", padx=10, pady=(0, 8))
            btn.configure(text="▼  ADVANCED SETTINGS")

    def on_keyword_method_change(label: str) -> None:
        key = _METHOD_KEYS.get(label, "spacy")
        app.settings.set("broll_keyword_method", key)

    # ── Wire commands ──────────────────────────────────────────────
    for _key_entry in (w["pixabay_key"], w["pexels_key"]):
        _key_entry.bind("<FocusOut>", lambda e: _persist_keys())
        _key_entry.bind("<Return>", lambda e: _persist_keys())

    w["browse_btn"].configure(command=on_browse)
    w["dl_folder_btn"].configure(command=on_pick_dl_folder)
    w["save_keys_btn"].configure(command=on_save_keys)
    w["provider"].configure(command=on_provider_change)
    w["top_n_slider"].configure(command=on_top_n_change)
    w["scan_btn"].configure(command=lambda: threading.Thread(
        target=scan_thread, args=(w, _state, set_status, _ui), daemon=True).start())
    w["analyze_btn"].configure(command=on_analyze)
    w["suggest_btn"].configure(command=lambda: threading.Thread(
        target=suggest_thread, args=(w, app, _state, set_status, set_suggestions, _ui),
        daemon=True).start())
    w["place_btn"].configure(command=on_place)
    w["search_online_btn"].configure(command=on_search_online)
    w["advanced_toggle"].configure(command=on_advanced_toggle)
    w["keyword_method"].configure(command=on_keyword_method_change)

    # Initial state for the search button (disabled until transcript + key)
    _refresh_search_button()
