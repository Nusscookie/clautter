"""Background thread workers for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
Each function receives all captured state as explicit parameters.
"""

from __future__ import annotations
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def scan_thread(
    w: dict,
    _state: dict,
    set_status: Callable,
    _ui: Callable,
) -> None:
    """Scan a folder for B-roll clips and populate the suggestions textbox."""
    try:
        from src.broll.scanner import scan_folder
        from src.ui._broll_build import _set_textbox

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

        _ui(lambda: _set_textbox(w["suggestions"], f"Found {len(clips)} clip(s):\n\n{summary}"))
        set_status(f"Scanned {len(clips)} clip(s). Click Analyze Transcript next.", "#66bb6a")
        _ui(lambda: w["analyze_btn"].configure(state="normal"))
    except Exception as e:
        log.error("B-roll scan error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
    finally:
        _ui(lambda: w["scan_btn"].configure(state="normal"))


def suggest_thread(
    w: dict,
    app: Any,
    _state: dict,
    set_status: Callable,
    set_suggestions: Callable,
    _ui: Callable,
) -> None:
    """Match transcript keywords to B-roll clips and display suggestions."""
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
