"""B-Roll Assistant tab — folder scan + transcript keyword matching."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="B-ROLL ASSISTANT  —  Smart B-roll suggestions from transcript",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    ctk.CTkLabel(
        parent,
        text="⚠  BETA — B-Roll matching is experimental. Auto Place coming in a future update.",
        font=ctk.CTkFont(size=11),
        text_color="#ff8f00",
        fg_color="#1a1200",
        corner_radius=4,
        anchor="w",
    ).pack(fill="x", padx=10, pady=4, ipady=6, ipadx=8)

    # ── Folder selection ──
    folder_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    folder_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(folder_card, text="B-ROLL FOLDER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    folder_row = ctk.CTkFrame(folder_card, fg_color="transparent")
    folder_row.pack(fill="x", padx=10, pady=(0, 8))
    folder_row.grid_columnconfigure(0, weight=1)

    w["folder"] = ctk.CTkEntry(folder_row,
                                placeholder_text="Select folder containing B-roll clips...")
    w["folder"].grid(row=0, column=0, sticky="ew", padx=(0, 6))

    w["browse_btn"] = ctk.CTkButton(folder_row, text="Browse", width=80)
    w["browse_btn"].grid(row=0, column=1)

    # ── Action buttons ──
    btn_row1 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row1.pack(fill="x", padx=10, pady=(4, 2))
    btn_row1.grid_columnconfigure((0, 1), weight=1)

    w["scan_btn"] = ctk.CTkButton(btn_row1, text="Scan Folder",
                                   fg_color="#2a2a2a", hover_color="#3a3a3a",
                                   state="disabled")
    w["scan_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["analyze_btn"] = ctk.CTkButton(btn_row1, text="Analyze Transcript",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["analyze_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    btn_row2 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row2.pack(fill="x", padx=10, pady=2)
    btn_row2.grid_columnconfigure((0, 1), weight=1)

    w["suggest_btn"] = ctk.CTkButton(btn_row2, text="Suggest B-Roll",
                                      fg_color="#1b5e20", hover_color="#2e7d32",
                                      state="disabled")
    w["suggest_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["place_btn"] = ctk.CTkButton(btn_row2, text="Auto Place on V2",
                                    fg_color="#2a2a2a", hover_color="#3a3a3a",
                                    state="disabled")
    w["place_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    w["status"] = ctk.CTkLabel(
        parent, text="Browse a folder of B-roll clips to start.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(4, 4))

    _divider(parent)

    # ── Suggestions ──
    ctk.CTkLabel(parent, text="CLIP LIBRARY  /  SUGGESTIONS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["suggestions"] = ctk.CTkTextbox(parent, height=200, state="disabled",
                                       font=ctk.CTkFont(size=12))
    w["suggestions"].pack(fill="x", padx=10, pady=(0, 4))
    _set_textbox(w["suggestions"], "Scan a folder, then generate suggestions...")

    ctk.CTkLabel(
        parent,
        text="Note: Requires transcript from the Subtitles tab. "
             "Auto-place places suggestions on V2, never overwrites existing clips.",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        wraplength=800,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(0, 12))

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

    def _scan_thread() -> None:
        try:
            from src.broll.scanner import scan_folder

            _ui(lambda: w["scan_btn"].configure(state="disabled"))
            folder = w["folder"].get().strip()
            if not folder:
                set_status("Enter a folder path first.", "#ff6b6b")
                return

            _state["folder"] = folder
            set_status(f"Scanning: {folder}")

            clips = scan_folder(folder)
            _state["clips"] = clips

            summary = "\n".join(
                f"[{i+1}] {c['name']} — {c['duration_sec']:.1f}s"
                for i, c in enumerate(clips[:50])
            )
            if len(clips) > 50:
                summary += f"\n... and {len(clips) - 50} more"

            set_suggestions(f"Found {len(clips)} clip(s):\n\n{summary}")
            set_status(f"Scanned {len(clips)} clip(s). Click Analyze Transcript next.", "#66bb6a")
            _ui(lambda: w["analyze_btn"].configure(state="normal"))
        except Exception as e:
            log.error("B-roll scan error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            _ui(lambda: w["scan_btn"].configure(state="normal"))

    def on_analyze() -> None:
        if not app.transcript:
            set_status("No transcript found. Generate one in the Subtitles tab first.", "#ff6b6b")
            return
        set_status(f"Transcript has {len(app.transcript)} words. Ready to suggest B-roll.", "#66bb6a")
        w["suggest_btn"].configure(state="normal")

    def _suggest_thread() -> None:
        try:
            from src.broll.matcher import suggest_broll

            _ui(lambda: w["suggest_btn"].configure(state="disabled"))
            set_status("Matching transcript keywords to B-roll clips...")

            transcript_text = " ".join(
                ww["word"] for ww in app.transcript if ww.get("type") == "word"
            )
            suggestions = suggest_broll(_state["clips"], transcript_text)
            _state["suggestions"] = suggestions

            if not suggestions:
                set_suggestions("No strong keyword matches found. "
                                "Try clips with more descriptive filenames.")
                set_status("No matches. Rename clips with descriptive keywords.", "#ffa726")
                return

            lines = ["B-ROLL SUGGESTIONS:\n"]
            for s in suggestions:
                lines.append(
                    f"  [{s['confidence']:.0%} match] {s['clip_name']}\n"
                    f"    Keywords: {', '.join(s['matched_keywords'])}\n"
                    f"    Suggested at: {s['suggested_time']:.1f}s\n"
                )
            set_suggestions("\n".join(lines))
            set_status(
                f"{len(suggestions)} suggestion(s) generated. Review above, then Auto Place.",
                "#66bb6a",
            )
            _ui(lambda: w["place_btn"].configure(state="normal"))
        except Exception as e:
            log.error("B-roll suggest error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            _ui(lambda: w["suggest_btn"].configure(state="normal"))

    def on_place() -> None:
        set_status(
            "Auto Place is coming in a future update. "
            "Use the suggestions above to manually place B-roll.",
            "#ffa726",
        )

    w["browse_btn"].configure(command=on_browse)
    w["scan_btn"].configure(command=lambda: threading.Thread(
        target=_scan_thread, daemon=True).start())
    w["analyze_btn"].configure(command=on_analyze)
    w["suggest_btn"].configure(command=lambda: threading.Thread(
        target=_suggest_thread, daemon=True).start())
    w["place_btn"].configure(command=on_place)
