"""Motion Graphics tab — rule-based graphic suggestions (beta scaffold)."""

from __future__ import annotations
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)

_STYLES = ["Minimal", "Bold", "Corporate", "Social Media", "Documentary"]


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="MOTION GRAPHICS  —  Suggestion engine (Beta)",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Beta notice ──
    ctk.CTkLabel(
        parent,
        text="⚠  BETA — V1 provides suggestions only. "
             "Full AI-generated graphics coming in a future update.",
        font=ctk.CTkFont(size=11),
        text_color="#ff8f00",
        fg_color="#1a1200",
        corner_radius=4,
        anchor="w",
    ).pack(fill="x", padx=10, pady=4, ipady=6, ipadx=8)

    # ── Settings ──
    settings_row = ctk.CTkFrame(parent, fg_color="transparent")
    settings_row.pack(fill="x", padx=10, pady=4)
    settings_row.grid_columnconfigure(0, weight=1)

    style_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    style_frame.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ctk.CTkLabel(style_frame, text="Graphic Style",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["style"] = ctk.CTkComboBox(style_frame, values=_STYLES, state="readonly")
    w["style"].set("Minimal")
    w["style"].pack(fill="x")

    w["generate_btn"] = ctk.CTkButton(settings_row, text="Generate Suggestions", width=160)
    w["generate_btn"].grid(row=0, column=1, sticky="s")

    w["status"] = ctk.CTkLabel(
        parent, text="Requires transcript from Subtitles tab.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w")
    w["status"].pack(fill="x", padx=12, pady=(4, 4))

    _divider(parent)

    # ── Suggestions ──
    ctk.CTkLabel(parent, text="SUGGESTIONS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["suggestions"] = ctk.CTkTextbox(parent, height=220, state="disabled",
                                       font=ctk.CTkFont(size=12))
    w["suggestions"].pack(fill="x", padx=10, pady=(0, 8))
    _set_textbox(
        w["suggestions"],
        "Suggestions will appear here after clicking Generate Suggestions.\n\n"
        "Example output:\n"
        "  [0:12] Lower Third — Speaker name\n"
        "  [0:45] Quote Card — 'Your key quote here'\n"
        "  [1:23] Statistic — '3 cameras tested'\n"
        "  [2:01] Process Diagram — 3-step workflow",
    )

    # ── Future integrations ──
    future_card = ctk.CTkFrame(parent, fg_color="#1a1a2e", corner_radius=6)
    future_card.pack(fill="x", padx=10, pady=(0, 12))

    ctk.CTkLabel(future_card, text="FUTURE AI INTEGRATIONS  (not yet active)",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#555555").pack(anchor="w", padx=10, pady=(8, 4))

    check_row = ctk.CTkFrame(future_card, fg_color="transparent")
    check_row.pack(fill="x", padx=10, pady=(0, 8))

    for name in ("Minimax", "Gemini", "OpenAI"):
        cb = ctk.CTkCheckBox(check_row, text=name, state="disabled")
        cb.pack(side="left", padx=8)

    parent._w = w


def _set_textbox(tb: ctk.CTkTextbox, text: str) -> None:
    tb.configure(state="normal")
    tb.delete("0.0", "end")
    tb.insert("0.0", text)
    tb.configure(state="disabled")


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    def on_generate() -> None:
        if not app.transcript:
            w["status"].configure(
                text="No transcript available. Generate one in the Subtitles tab first.",
                text_color="#ff6b6b",
            )
            return

        from src.graphics.suggester import suggest_graphics

        transcript_text = " ".join(
            ww["word"] for ww in app.transcript if ww.get("type") == "word"
        )
        style = w["style"].get()

        try:
            suggestions = suggest_graphics(app.transcript, style)

            if not suggestions:
                _set_textbox(w["suggestions"],
                             "No graphic suggestions generated. "
                             "Try with more content in the transcript.")
                w["status"].configure(text="No suggestions found.", text_color="#aaaaaa")
                return

            lines = ["MOTION GRAPHIC SUGGESTIONS:\n"]
            for s in suggestions:
                ts = s.get("timestamp_sec", 0)
                minutes = int(ts) // 60
                seconds = int(ts) % 60
                lines.append(f"[{minutes}:{seconds:02d}]  {s['type']}\n"
                              f"         {s['description']}\n")

            _set_textbox(w["suggestions"], "\n".join(lines))
            w["status"].configure(
                text=f"{len(suggestions)} graphic suggestion(s) generated.",
                text_color="#66bb6a",
            )
        except Exception as e:
            log.error("Graphics suggestion error: %s", e)
            w["status"].configure(text=f"Error: {e}", text_color="#ff6b6b")

    w["generate_btn"].configure(command=on_generate)
