"""Settings window — gear-icon dialog for API keys and advanced method settings."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)

_WIN_W = 560
_WIN_H = 520

_SILENCE_METHOD_LABELS: dict[str, str] = {
    "vad": "Silero VAD (recommended)",
    "rms": "pydub RMS (legacy)",
}
_RETAKE_METHOD_LABELS: dict[str, str] = {
    "spacy":   "spaCy filler normalization (recommended)",
    "difflib": "difflib only (legacy)",
}
_KEYWORD_METHOD_LABELS: dict[str, str] = {
    "spacy":     "spaCy (en_core_web_sm)",
    "yake":      "YAKE",
    "keybert":   "KeyBERT",
    "frequency": "Frequency (no deps)",
}

_open_window: ctk.CTkToplevel | None = None


def open_settings(app: Any) -> None:
    global _open_window
    if _open_window is not None and _open_window.winfo_exists():
        _open_window.lift()
        _open_window.focus_force()
        return
    _open_window = _SettingsWindow(app)


class _SettingsWindow(ctk.CTkToplevel):
    def __init__(self, app: Any) -> None:
        super().__init__()
        self._app = app
        self.title("Clutter — Settings")
        self.geometry(f"{_WIN_W}x{_WIN_H}")
        self.resizable(False, False)
        self.configure(fg_color="#141414")
        self.grab_set()
        self._build()

    def _build(self) -> None:
        app = self._app

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)

        # ── API KEYS ──────────────────────────────────────────────────
        api_card = ctk.CTkFrame(scroll, fg_color="#2a2a2a", corner_radius=6)
        api_card.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkLabel(api_card, text="API KEYS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(10, 6))

        self._el_entry, self._el_status = _key_row(api_card, "ElevenLabs")
        self._px_entry, self._px_status = _key_row(api_card, "Pixabay")
        self._pex_entry, self._pex_status = _key_row(api_card, "Pexels")

        save_btn = ctk.CTkButton(
            api_card, text="Save All Keys",
            fg_color="#1f6aa5", hover_color="#144870",
            text_color="#ffffff", width=130,
            command=self._on_save_keys,
        )
        save_btn.pack(anchor="w", padx=12, pady=(4, 10))

        # Pre-fill from settings
        _prefill(self._el_entry, str(app.settings.get("elevenlabs_api_key", "") or ""))
        _prefill(self._px_entry, str(app.settings.get("pixabay_api_key", "") or ""))
        _prefill(self._pex_entry, str(app.settings.get("pexels_api_key", "") or ""))

        # ── SMART CUTS ────────────────────────────────────────────────
        sc_card = ctk.CTkFrame(scroll, fg_color="#2a2a2a", corner_radius=6)
        sc_card.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(sc_card, text="SMART CUTS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(10, 6))

        self._silence_menu = _option_row(
            sc_card, "Silence detection:",
            list(_SILENCE_METHOD_LABELS.values()),
        )
        self._retake_menu = _option_row(
            sc_card, "Retake detection:",
            list(_RETAKE_METHOD_LABELS.values()),
        )

        ctk.CTkLabel(
            sc_card,
            text="Silero VAD downloads ~5 MB model on first run. "
                 "spaCy uses en_core_web_sm (already installed).",
            font=ctk.CTkFont(size=10), text_color="#555555",
            anchor="w", wraplength=500,
        ).pack(fill="x", padx=12, pady=(2, 10))

        saved_silence = str(app.settings.get("smartcuts_silence_method", "vad"))
        self._silence_menu.set(
            _SILENCE_METHOD_LABELS.get(saved_silence, _SILENCE_METHOD_LABELS["vad"])
        )
        saved_retake = str(app.settings.get("smartcuts_retake_method", "spacy"))
        self._retake_menu.set(
            _RETAKE_METHOD_LABELS.get(saved_retake, _RETAKE_METHOD_LABELS["spacy"])
        )

        self._silence_menu.configure(command=self._on_silence_method)
        self._retake_menu.configure(command=self._on_retake_method)

        # ── B-ROLL ────────────────────────────────────────────────────
        br_card = ctk.CTkFrame(scroll, fg_color="#2a2a2a", corner_radius=6)
        br_card.pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(br_card, text="B-ROLL",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(10, 6))

        self._keyword_menu = _option_row(
            br_card, "Keyword method:",
            list(_KEYWORD_METHOD_LABELS.values()),
        )

        ctk.CTkLabel(
            br_card,
            text="KeyBERT and spaCy download a model (~80 MB) on first use.",
            font=ctk.CTkFont(size=10), text_color="#555555",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 10))

        saved_kw = str(app.settings.get("broll_keyword_method", "keybert"))
        self._keyword_menu.set(
            _KEYWORD_METHOD_LABELS.get(saved_kw, _KEYWORD_METHOD_LABELS["keybert"])
        )
        self._keyword_menu.configure(command=self._on_keyword_method)

        # ── Done button ───────────────────────────────────────────────
        ctk.CTkButton(
            scroll, text="Done",
            fg_color="#2a2a2a", hover_color="#3a3a3a",
            text_color="#aaaaaa", width=100,
            command=self.destroy,
        ).pack(anchor="e", padx=12, pady=(8, 12))

    # ── Handlers ──────────────────────────────────────────────────────

    def _on_save_keys(self) -> None:
        app = self._app
        el = self._el_entry.get().strip()
        px = self._px_entry.get().strip()
        pex = self._pex_entry.get().strip()

        if el:
            app.settings.set("elevenlabs_api_key", el)
        if px:
            app.settings.set("pixabay_api_key", px)
        if pex:
            app.settings.set("pexels_api_key", pex)

        saved: list[str] = []
        if el:
            saved.append("ElevenLabs")
            self._el_status.configure(text="Saved.", text_color="#66bb6a")
        if px:
            saved.append("Pixabay")
            self._px_status.configure(text="Saved.", text_color="#66bb6a")
        if pex:
            saved.append("Pexels")
            self._pex_status.configure(text="Saved.", text_color="#66bb6a")

        log.info("Settings: saved keys: %s", ", ".join(saved) if saved else "none")

    def _on_silence_method(self, label: str) -> None:
        key = next((k for k, v in _SILENCE_METHOD_LABELS.items() if v == label), "vad")
        self._app.settings.set("smartcuts_silence_method", key)

    def _on_retake_method(self, label: str) -> None:
        key = next((k for k, v in _RETAKE_METHOD_LABELS.items() if v == label), "spacy")
        self._app.settings.set("smartcuts_retake_method", key)

    def _on_keyword_method(self, label: str) -> None:
        key = next((k for k, v in _KEYWORD_METHOD_LABELS.items() if v == label), "keybert")
        self._app.settings.set("broll_keyword_method", key)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _key_row(parent: Any, label: str) -> tuple[ctk.CTkEntry, ctk.CTkLabel]:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 4))
    row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(row, text=f"{label}:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=90, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, show="*", placeholder_text=f"Paste {label} API key")
    entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    status = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=10),
                          text_color="#aaaaaa", anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 2))

    return entry, status


def _option_row(parent: Any, label: str, values: list[str]) -> ctk.CTkOptionMenu:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 6))

    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=150, anchor="w").pack(side="left")

    menu = ctk.CTkOptionMenu(
        row, values=values, width=240,
        fg_color="#1e1e1e", button_color="#1e1e1e", button_hover_color="#3a3a3a",
    )
    menu.pack(side="left", padx=(6, 0))
    return menu


def _prefill(entry: ctk.CTkEntry, value: str) -> None:
    if value:
        entry.delete(0, "end")
        entry.insert(0, value)
