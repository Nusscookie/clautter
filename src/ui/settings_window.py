"""Settings window — gear-icon dialog for API keys and advanced method settings."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.ui.icon_helper import apply_clutter_icon
from src.utils.logger import get_logger

log = get_logger(__name__)

_WIN_W = 560
_WIN_H = 860

_OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
_GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-pro"]
_MINIMAX_MODELS = ["MiniMax-Text-01", "MiniMax-M2.5", "abab6.5s-chat", "abab6.5g-chat", "abab5.5s-chat"]

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
        apply_clutter_icon(self)
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

        self._el_entry,  self._el_status  = _key_row(api_card, "ElevenLabs")
        self._px_entry,  self._px_status  = _key_row(api_card, "Pixabay")
        self._pex_entry, self._pex_status = _key_row(api_card, "Pexels")
        self._fs_entry,  self._fs_status  = _key_row(api_card, "Freesound")
        self._jam_entry, self._jam_status = _key_row(api_card, "Jamendo Client ID",
                                                      placeholder="Jamendo app client_id")

        ctk.CTkLabel(
            api_card,
            text="Freesound (freesound.org/apiv2): SFX placement.  "
                 "Jamendo (devportal.jamendo.com): background music.  Both free accounts.",
            font=ctk.CTkFont(size=10), text_color="#555555",
            anchor="w", wraplength=500,
        ).pack(fill="x", padx=12, pady=(0, 8))

        # Pre-fill from settings
        _prefill(self._el_entry,  str(app.settings.get("elevenlabs_api_key",  "") or ""))
        _prefill(self._px_entry,  str(app.settings.get("pixabay_api_key",     "") or ""))
        _prefill(self._pex_entry, str(app.settings.get("pexels_api_key",      "") or ""))
        _prefill(self._fs_entry,  str(app.settings.get("freesound_api_key",   "") or ""))
        _prefill(self._jam_entry, str(app.settings.get("jamendo_client_id",   "") or ""))

        # ── CLOUD LLM RE-RANK ─────────────────────────────────────────
        llm_card = ctk.CTkFrame(scroll, fg_color="#2a2a2a", corner_radius=6)
        llm_card.pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(llm_card, text="CLOUD LLM RE-RANK",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(10, 6))

        ctk.CTkLabel(
            llm_card,
            text="Optional: used by Autonomous B-Roll to pick the best clip per segment. "
                 "Leave blank to use semantic ranking only.",
            font=ctk.CTkFont(size=10), text_color="#555555",
            anchor="w", wraplength=500,
        ).pack(fill="x", padx=12, pady=(0, 6))

        self._oai_entry, self._oai_status = _key_row(llm_card, "OpenAI")
        self._gem_entry, self._gem_status = _key_row(llm_card, "Gemini")
        self._mmx_entry, self._mmx_status = _key_row(llm_card, "Minimax")


        _prefill(self._oai_entry, str(app.settings.get("openai_api_key", "") or ""))
        _prefill(self._gem_entry, str(app.settings.get("gemini_api_key", "") or ""))
        _prefill(self._mmx_entry, str(app.settings.get("minimax_api_key", "") or ""))

        # ── LLM MODEL CONFIG ──────────────────────────────────────────
        mc_card = ctk.CTkFrame(scroll, fg_color="#2a2a2a", corner_radius=6)
        mc_card.pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(mc_card, text="LLM MODEL CONFIG",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            mc_card,
            text="Model and generation settings used by Full Director mode. "
                 "Applied to whichever provider has an API key.",
            font=ctk.CTkFont(size=10), text_color="#555555",
            anchor="w", wraplength=500,
        ).pack(fill="x", padx=12, pady=(0, 6))

        self._oai_model = _option_row(mc_card, "OpenAI model:", _OPENAI_MODELS)
        self._gem_model = _option_row(mc_card, "Gemini model:", _GEMINI_MODELS)
        self._mmx_model = _option_row(mc_card, "Minimax model:", _MINIMAX_MODELS)

        self._llm_max_tokens_entry = _numeric_row(
            mc_card, "Max tokens:", 200, 8000,
            str(int(app.settings.get("llm_max_tokens", 1500) or 1500)),
            hint="Tokens LLM may generate. Higher = longer but slower.",
        )
        self._llm_temp_entry = _numeric_row(
            mc_card, "Temperature:", 0.0, 2.0,
            f"{float(app.settings.get('llm_temperature', 0.1) or 0.1):.2f}",
            hint="0 = deterministic, higher = more creative.",
        )


        self._oai_model.set(str(app.settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini"))
        self._gem_model.set(str(app.settings.get("llm_gemini_model", "gemini-2.0-flash") or "gemini-2.0-flash"))
        self._mmx_model.set(str(app.settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01"))

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
        ).pack(fill="x", padx=12, pady=(2, 8))

        ctk.CTkLabel(br_card, text="NATURAL PLACEMENT",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#888888").pack(anchor="w", padx=12, pady=(4, 4))

        self._intro_skip_entry = _numeric_row(
            br_card, "Intro skip (s):", 0.0, 60.0,
            f"{float(app.settings.get('broll_intro_skip_sec', 8.0)):.1f}",
            hint="No B-roll before this time. Default: 8s.",
        )
        self._min_gap_entry = _numeric_row(
            br_card, "Min gap (s):", 0.0, 30.0,
            f"{float(app.settings.get('broll_min_gap_sec', 5.0)):.1f}",
            hint="Minimum face time between clips. Default: 5s.",
        )
        self._max_clip_entry = _numeric_row(
            br_card, "Max clip (s):", 1.0, 30.0,
            f"{float(app.settings.get('broll_max_broll_duration', 5.0)):.1f}",
            hint="Maximum B-roll clip duration. Default: 5s.",
        )


        saved_kw = str(app.settings.get("broll_keyword_method", "keybert"))
        self._keyword_menu.set(
            _KEYWORD_METHOD_LABELS.get(saved_kw, _KEYWORD_METHOD_LABELS["keybert"])
        )
        self._keyword_menu.configure(command=self._on_keyword_method)

        # ── Bottom bar ────────────────────────────────────────────────
        bottom = ctk.CTkFrame(scroll, fg_color="transparent")
        bottom.pack(anchor="e", padx=12, pady=(8, 12))

        ctk.CTkButton(
            bottom, text="Apply",
            fg_color="#B85F3A", hover_color="#C96A45",
            text_color="#ffffff", width=100,
            command=self._on_apply,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bottom, text="Done",
            fg_color="#2a2a2a", hover_color="#3a3a3a",
            text_color="#aaaaaa", width=100,
            command=self.destroy,
        ).pack(side="left")

    # ── Handlers ──────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        self._on_save_keys()
        self._on_save_llm_keys()
        self._on_save_model_config()
        self._on_save_placement()

    def _on_save_keys(self) -> None:
        app = self._app
        el  = self._el_entry.get().strip()
        px  = self._px_entry.get().strip()
        pex = self._pex_entry.get().strip()
        fs  = self._fs_entry.get().strip()
        jam = self._jam_entry.get().strip()

        if el:
            app.settings.set("elevenlabs_api_key", el)
        if px:
            app.settings.set("pixabay_api_key", px)
        if pex:
            app.settings.set("pexels_api_key", pex)
        if fs:
            app.settings.set("freesound_api_key", fs)
        if jam:
            app.settings.set("jamendo_client_id", jam)

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
        if fs:
            saved.append("Freesound")
            self._fs_status.configure(text="Saved.", text_color="#66bb6a")
        if jam:
            saved.append("Jamendo")
            self._jam_status.configure(text="Saved.", text_color="#66bb6a")

        log.info("Settings: saved keys: %s", ", ".join(saved) if saved else "none")

    def _on_save_llm_keys(self) -> None:
        app = self._app
        oai = self._oai_entry.get().strip()
        gem = self._gem_entry.get().strip()
        mmx = self._mmx_entry.get().strip()

        saved: list[str] = []
        if oai:
            app.settings.set("openai_api_key", oai)
            saved.append("OpenAI")
            self._oai_status.configure(text="Saved.", text_color="#66bb6a")
        if gem:
            app.settings.set("gemini_api_key", gem)
            saved.append("Gemini")
            self._gem_status.configure(text="Saved.", text_color="#66bb6a")
        if mmx:
            app.settings.set("minimax_api_key", mmx)
            saved.append("Minimax")
            self._mmx_status.configure(text="Saved.", text_color="#66bb6a")

        log.info("Settings: saved LLM keys: %s", ", ".join(saved) if saved else "none")

    def _on_save_model_config(self) -> None:
        app = self._app
        app.settings.set("llm_openai_model", self._oai_model.get())
        app.settings.set("llm_gemini_model", self._gem_model.get())
        app.settings.set("llm_minimax_model", self._mmx_model.get())
        try:
            app.settings.set("llm_max_tokens", int(self._llm_max_tokens_entry.get().strip()))
        except ValueError:
            pass
        try:
            app.settings.set("llm_temperature", float(self._llm_temp_entry.get().strip()))
        except ValueError:
            pass
        log.info("Settings: saved LLM model config")

    def _on_save_placement(self) -> None:
        app = self._app
        try:
            app.settings.set("broll_intro_skip_sec", float(self._intro_skip_entry.get().strip()))
        except ValueError:
            pass
        try:
            app.settings.set("broll_min_gap_sec", float(self._min_gap_entry.get().strip()))
        except ValueError:
            pass
        try:
            app.settings.set("broll_max_broll_duration", float(self._max_clip_entry.get().strip()))
        except ValueError:
            pass
        log.info("Settings: saved natural placement config")

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

def _key_row(
    parent: Any, label: str, placeholder: str | None = None
) -> tuple[ctk.CTkEntry, ctk.CTkLabel]:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 4))
    row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(row, text=f"{label}:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=130, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, show="*",
                         placeholder_text=placeholder or f"Paste {label} API key")
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


def _numeric_row(
    parent: Any,
    label: str,
    min_val: float,
    max_val: float,
    default: str,
    hint: str = "",
) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=(0, 4))
    row.grid_columnconfigure(2, weight=1)

    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=130, anchor="w").grid(row=0, column=0, sticky="w")

    entry = ctk.CTkEntry(row, width=80, placeholder_text=default)
    entry.grid(row=0, column=1, padx=(6, 8))
    entry.insert(0, default)

    if hint:
        ctk.CTkLabel(row, text=hint, font=ctk.CTkFont(size=10),
                     text_color="#555555", anchor="w").grid(row=0, column=2, sticky="w")

    return entry


def _prefill(entry: ctk.CTkEntry, value: str) -> None:
    if value:
        entry.delete(0, "end")
        entry.insert(0, value)
