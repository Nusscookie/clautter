"""Motion Graphics tab — rule-based graphic suggestions (beta scaffold)."""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_STYLES = ["Minimal", "Bold", "Corporate", "Social Media", "Documentary"]


def build(ui: Any) -> Any:
    """Return the Motion Graphics tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "MOTION GRAPHICS  —  Suggestion engine (Beta)",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # Beta notice
        ui.Label({
            "Text": "⚠  BETA — V1 provides suggestions only. "
                    "Full AI-generated graphics coming in a future update.",
            "Weight": 0,
            "StyleSheet": "color: #ff8f00; background: #1a1200; border-radius: 4px; "
                          "padding: 6px; font-size: 11px;",
        }),

        # Settings
        ui.HGroup({"Spacing": 12, "Weight": 0}, [
            ui.VGroup({"Spacing": 4, "Weight": 1}, [
                ui.Label({"Text": "Graphic Style", "Weight": 0,
                          "StyleSheet": "color: #aaaaaa; font-size: 10px;"}),
                ui.ComboBox({"ID": "GfxStyle", "Weight": 1}),
            ]),
            ui.VGroup({"Spacing": 4, "Weight": 0}, [
                ui.Label({"Text": "", "Weight": 0}),
                ui.Button({
                    "ID": "GfxGenerateBtn",
                    "Text": "Generate Suggestions",
                    "Weight": 0,
                }),
            ]),
        ]),

        ui.Label({
            "ID": "GfxStatus",
            "Text": "Requires transcript from Subtitles tab.",
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
            ui.Label({"Text": "SUGGESTIONS",
                      "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.TextEdit({
                "ID": "GfxSuggestions",
                "PlaceholderText":
                    "Suggestions will appear here after clicking Generate Suggestions.\n\n"
                    "Example output:\n"
                    "  [0:12] Lower Third — Speaker name\n"
                    "  [0:45] Quote Card — 'Your key quote here'\n"
                    "  [1:23] Statistic — '3 cameras tested'\n"
                    "  [2:01] Process Diagram — 3-step workflow",
                "Weight": 1,
                "ReadOnly": True,
            }),
        ]),

        # Future integrations
        ui.VGroup({"Spacing": 4, "Weight": 0,
                   "StyleSheet": "background: #1a1a2e; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "FUTURE AI INTEGRATIONS  (not yet active)",
                      "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #555555; letter-spacing: 1px;"}),
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.CheckBox({"ID": "GfxUseMinimax", "Text": "Minimax",
                             "Checked": False, "Enabled": False, "Weight": 1}),
                ui.CheckBox({"ID": "GfxUseGemini", "Text": "Gemini",
                             "Checked": False, "Enabled": False, "Weight": 1}),
                ui.CheckBox({"ID": "GfxUseOpenAI", "Text": "OpenAI",
                             "Checked": False, "Enabled": False, "Weight": 1}),
            ]),
        ]),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect Motion Graphics event handlers."""
    from src.graphics.suggester import suggest_graphics

    # Populate style dropdown
    style_combo = win.Find("GfxStyle")
    for s in _STYLES:
        style_combo.AddItem(s)

    def on_generate(ev: Any) -> None:
        if not app.transcript:
            win.Find("GfxStatus").SetText(
                "No transcript available. Generate one in the Subtitles tab first."
            )
            return

        transcript_text = " ".join(
            w["word"] for w in app.transcript if w.get("type") == "word"
        )
        style = win.Find("GfxStyle").CurrentText

        try:
            suggestions = suggest_graphics(app.transcript, style)

            if not suggestions:
                win.Find("GfxSuggestions").SetPlainText(
                    "No graphic suggestions generated. "
                    "Try with more content in the transcript."
                )
                win.Find("GfxStatus").SetText("No suggestions found.")
                return

            lines = ["MOTION GRAPHIC SUGGESTIONS:\n"]
            for s in suggestions:
                ts = s.get("timestamp_sec", 0)
                minutes = int(ts) // 60
                seconds = int(ts) % 60
                lines.append(
                    f"[{minutes}:{seconds:02d}]  {s['type']}\n"
                    f"         {s['description']}\n"
                )

            win.Find("GfxSuggestions").SetPlainText("\n".join(lines))
            win.Find("GfxStatus").SetText(
                f"{len(suggestions)} graphic suggestion(s) generated."
            )
        except Exception as e:
            log.error("Graphics suggestion error: %s", e)
            win.Find("GfxStatus").SetText(f"Error: {e}")

    win.On.GfxGenerateBtn.Clicked = on_generate
