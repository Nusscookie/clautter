"""B-Roll Assistant tab — folder scan + transcript keyword matching (scaffold)."""

from __future__ import annotations
import threading
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def build(ui: Any) -> Any:
    """Return the B-Roll Assistant tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "B-ROLL ASSISTANT  —  Smart B-roll suggestions from transcript",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # Folder selection
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "B-ROLL FOLDER", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.LineEdit({
                    "ID": "BrollFolder",
                    "PlaceholderText": "Select folder containing B-roll clips...",
                    "Weight": 1,
                    "ReadOnly": True,
                }),
                ui.Button({"ID": "BrollBrowseBtn", "Text": "Browse", "Weight": 0}),
            ]),
        ]),

        # Action buttons
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({"ID": "BrollScanBtn", "Text": "Scan Folder", "Weight": 1,
                       "Enabled": False}),
            ui.Button({"ID": "BrollAnalyzeBtn", "Text": "Analyze Transcript", "Weight": 1,
                       "Enabled": False}),
        ]),
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({
                "ID": "BrollSuggestBtn",
                "Text": "Suggest B-Roll",
                "Weight": 1,
                "Enabled": False,
                "StyleSheet": "background: #1b5e20; color: white; font-weight: bold;",
            }),
            ui.Button({"ID": "BrollPlaceBtn", "Text": "Auto Place on V2",
                       "Weight": 1, "Enabled": False}),
        ]),

        ui.Label({
            "ID": "BrollStatus",
            "Text": "Browse a folder of B-roll clips to start.",
            "Weight": 0,
            "StyleSheet": "color: #aaaaaa; font-size: 11px;",
        }),

        ui.Label({
            "Text": "",
            "Weight": 0,
            "MinimumSize": [1, 1],
            "MaximumSize": [9999, 1],
            "StyleSheet": "background: #444444;",
        }),

        # Suggestions
        ui.VGroup({"Spacing": 4, "Weight": 1}, [
            ui.Label({"Text": "CLIP LIBRARY  /  SUGGESTIONS",
                      "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.TextEdit({
                "ID": "BrollSuggestions",
                "PlaceholderText": "Scan a folder, then generate suggestions...",
                "Weight": 1,
                "ReadOnly": True,
            }),
        ]),

        # Beta notice
        ui.Label({
            "Text": "Note: Requires transcript from the Subtitles tab. "
                    "Auto-place places suggestions on V2, never overwrites existing clips.",
            "Weight": 0,
            "StyleSheet": "color: #555555; font-size: 10px;",
        }),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect B-Roll event handlers."""

    _state: dict[str, Any] = {
        "folder": "",
        "clips": [],
        "suggestions": [],
    }

    def _set_status(msg: str, color: str = "#aaaaaa") -> None:
        try:
            win.Find("BrollStatus").SetText(msg)
        except Exception:
            pass

    def on_browse(ev: Any) -> None:
        # DaVinci's UIManager doesn't have a native folder dialog.
        # Guide user to paste path manually.
        win.Find("BrollFolder").ReadOnly = False
        _set_status("Type or paste the folder path into the text box, then click Scan Folder.", "#4fc3f7")
        win.Find("BrollScanBtn").Enabled = True

    def on_scan_thread() -> None:
        try:
            from src.broll.scanner import scan_folder

            win.Find("BrollScanBtn").Enabled = False
            folder = win.Find("BrollFolder").Text.strip()
            if not folder:
                _set_status("Enter a folder path first.", "#ff6b6b")
                return

            _state["folder"] = folder
            _set_status(f"Scanning: {folder}", "#aaaaaa")

            clips = scan_folder(folder)
            _state["clips"] = clips

            summary = "\n".join(
                f"[{i+1}] {c['name']} — {c['duration_sec']:.1f}s"
                for i, c in enumerate(clips[:50])
            )
            if len(clips) > 50:
                summary += f"\n... and {len(clips) - 50} more"

            win.Find("BrollSuggestions").SetPlainText(
                f"Found {len(clips)} clip(s):\n\n{summary}"
            )
            _set_status(f"Scanned {len(clips)} clip(s). Click Analyze Transcript next.", "#66bb6a")
            win.Find("BrollAnalyzeBtn").Enabled = True
        except Exception as e:
            log.error("B-roll scan error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
        finally:
            win.Find("BrollScanBtn").Enabled = True

    def on_analyze(ev: Any) -> None:
        if not app.transcript:
            _set_status(
                "No transcript found. Generate one in the Subtitles tab first.", "#ff6b6b"
            )
            return
        _set_status(
            f"Transcript has {len(app.transcript)} words. Ready to suggest B-roll.", "#66bb6a"
        )
        win.Find("BrollSuggestBtn").Enabled = True

    def on_suggest_thread() -> None:
        try:
            from src.broll.matcher import suggest_broll

            win.Find("BrollSuggestBtn").Enabled = False
            _set_status("Matching transcript keywords to B-roll clips...", "#aaaaaa")

            transcript_text = " ".join(
                w["word"] for w in app.transcript if w.get("type") == "word"
            )
            suggestions = suggest_broll(_state["clips"], transcript_text)
            _state["suggestions"] = suggestions

            if not suggestions:
                win.Find("BrollSuggestions").SetPlainText(
                    "No strong keyword matches found. "
                    "Try clips with more descriptive filenames."
                )
                _set_status("No matches. Rename clips with descriptive keywords.", "#ffa726")
                return

            lines = ["B-ROLL SUGGESTIONS:\n"]
            for s in suggestions:
                lines.append(
                    f"  [{s['confidence']:.0%} match] {s['clip_name']}\n"
                    f"    Keywords: {', '.join(s['matched_keywords'])}\n"
                    f"    Suggested at: {s['suggested_time']:.1f}s\n"
                )
            win.Find("BrollSuggestions").SetPlainText("\n".join(lines))
            _set_status(
                f"{len(suggestions)} suggestion(s) generated. "
                "Review above, then click Auto Place B-Roll.",
                "#66bb6a",
            )
            win.Find("BrollPlaceBtn").Enabled = True
        except Exception as e:
            log.error("B-roll suggest error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
        finally:
            win.Find("BrollSuggestBtn").Enabled = True

    def on_place(ev: Any) -> None:
        # TODO: Implement auto-placement on V2 in a future version.
        _set_status(
            "Auto Place is coming in a future update. "
            "For now, use the suggestions above to manually place B-roll.",
            "#ffa726",
        )

    def on_scan(ev: Any) -> None:
        threading.Thread(target=on_scan_thread, daemon=True).start()

    def on_suggest(ev: Any) -> None:
        threading.Thread(target=on_suggest_thread, daemon=True).start()

    win.On.BrollBrowseBtn.Clicked = on_browse
    win.On.BrollScanBtn.Clicked = on_scan
    win.On.BrollAnalyzeBtn.Clicked = on_analyze
    win.On.BrollSuggestBtn.Clicked = on_suggest
    win.On.BrollPlaceBtn.Clicked = on_place
