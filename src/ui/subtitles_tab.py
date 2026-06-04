"""Subtitles tab — ElevenLabs STT transcript generation and subtitle track creation."""

from __future__ import annotations
import threading
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_LANGUAGES = [
    ("Auto-detect", ""),
    ("English", "en"),
    ("German", "de"),
    ("French", "fr"),
    ("Spanish", "es"),
    ("Italian", "it"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Portuguese", "pt"),
    ("Russian", "ru"),
    ("Dutch", "nl"),
    ("Swedish", "sv"),
    ("Norwegian", "no"),
    ("Danish", "da"),
    ("Mandarin (Simplified)", "zh"),
]

_PRESETS = ["YouTube", "Standard", "TikTok", "Alex Hormozi Style"]


def build(ui: Any) -> Any:
    """Return the Subtitles tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "SUBTITLES  —  Generate captions via ElevenLabs Speech-to-Text",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # API key
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "ELEVENLABS API", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.LineEdit({
                    "ID": "SubsApiKey",
                    "PlaceholderText": "Enter ElevenLabs API key...",
                    "EchoMode": "Password",
                    "Weight": 1,
                }),
                ui.Button({"ID": "SubsSaveKey", "Text": "Save", "Weight": 0}),
            ]),
            ui.Label({
                "ID": "SubsKeyStatus",
                "Text": "",
                "Weight": 0,
                "StyleSheet": "color: #aaaaaa; font-size: 10px;",
            }),
        ]),

        # Settings row
        ui.HGroup({"Spacing": 12, "Weight": 0}, [
            ui.VGroup({"Spacing": 4, "Weight": 1}, [
                ui.Label({"Text": "Language", "Weight": 0,
                          "StyleSheet": "color: #aaaaaa; font-size: 10px;"}),
                ui.ComboBox({"ID": "SubsLanguage", "Weight": 1}),
            ]),
            ui.VGroup({"Spacing": 4, "Weight": 1}, [
                ui.Label({"Text": "Style Preset", "Weight": 0,
                          "StyleSheet": "color: #aaaaaa; font-size: 10px;"}),
                ui.ComboBox({"ID": "SubsPreset", "Weight": 1}),
            ]),
        ]),

        # Action buttons
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({
                "ID": "SubsGenerateBtn",
                "Text": "Generate Transcript",
                "Weight": 1,
                "StyleSheet": "background: #1565c0; color: white; font-weight: bold;",
            }),
            ui.Button({"ID": "SubsCreateTrackBtn", "Text": "Create Subtitle Track",
                       "Weight": 1, "Enabled": False}),
        ]),
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({"ID": "SubsExportSrtBtn", "Text": "Export SRT",
                       "Weight": 1, "Enabled": False}),
            ui.Button({"ID": "SubsExportTxtBtn", "Text": "Export TXT",
                       "Weight": 1, "Enabled": False}),
            ui.CheckBox({"ID": "SubsBurnIn", "Text": "Burn-in subtitles",
                         "Checked": False, "Weight": 1}),
        ]),

        # Progress
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.ProgressBar({
                "ID": "SubsProgress",
                "Minimum": 0,
                "Maximum": 100,
                "Value": 0,
                "Visible": False,
            }),
            ui.Label({
                "ID": "SubsStatus",
                "Text": "Enter API key and click Generate Transcript.",
                "Weight": 0,
                "StyleSheet": "color: #aaaaaa; font-size: 11px;",
            }),
        ]),

        ui.Label({
            "Text": "",
            "Weight": 0,
            "MinimumSize": [1, 1],
            "MaximumSize": [9999, 1],
            "StyleSheet": "background: #444444;",
        }),

        # Transcript panel
        ui.VGroup({"Spacing": 4, "Weight": 1}, [
            ui.Label({"Text": "TRANSCRIPT  (editable — click to jump to position)",
                      "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.TextEdit({
                "ID": "SubsTranscript",
                "PlaceholderText": "Transcript will appear here after generation...",
                "Weight": 1,
                "ReadOnly": False,
            }),
        ]),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect Subtitles event handlers."""

    # State
    _state: dict[str, Any] = {
        "words": [],       # list of dicts: {word, start_sec, end_sec}
        "srt_content": "",
        "srt_path": "",
    }

    # Populate dropdowns
    lang_combo = win.Find("SubsLanguage")
    for label, _ in _LANGUAGES:
        lang_combo.AddItem(label)

    preset_combo = win.Find("SubsPreset")
    for p in _PRESETS:
        preset_combo.AddItem(p)

    # Load saved API key (masked)
    saved_key = app.settings.api_key
    if saved_key:
        win.Find("SubsApiKey").SetText(saved_key)
        win.Find("SubsKeyStatus").SetText("API key loaded from settings.")

    # Restore saved presets
    saved_preset = app.settings.get("subtitle_preset", "YouTube")
    try:
        idx = _PRESETS.index(saved_preset)
        win.Find("SubsPreset").CurrentIndex = idx
    except ValueError:
        pass

    def _set_status(msg: str, color: str = "#aaaaaa") -> None:
        try:
            lbl = win.Find("SubsStatus")
            lbl.SetText(msg)
            lbl.StyleSheet = f"color: {color}; font-size: 11px;"
        except Exception:
            pass

    def _set_progress(value: int, visible: bool = True) -> None:
        try:
            pb = win.Find("SubsProgress")
            pb.Visible = visible
            pb.Value = value
        except Exception:
            pass

    def on_save_key(ev: Any) -> None:
        key = win.Find("SubsApiKey").Text.strip()
        if key:
            app.settings.api_key = key
            win.Find("SubsKeyStatus").SetText("API key saved.")
        else:
            win.Find("SubsKeyStatus").SetText("Key is empty — not saved.")

    def _generate_thread() -> None:
        try:
            from src.subtitles.elevenlabs import ElevenLabsClient
            from src.utils.resolve_api import get_clip_file_path

            win.Find("SubsGenerateBtn").Enabled = False
            _set_progress(0, True)
            _set_status("Checking configuration...", "#aaaaaa")

            api_key = win.Find("SubsApiKey").Text.strip()
            if not api_key:
                _set_status("API key is empty. Enter your ElevenLabs key first.", "#ff6b6b")
                _set_progress(0, False)
                return

            lang_idx = win.Find("SubsLanguage").CurrentIndex
            lang_code = _LANGUAGES[lang_idx][1]

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                _set_status("No clips found on Video Track 1.", "#ff6b6b")
                _set_progress(0, False)
                return

            # Use the first clip's media file for transcription
            # For multi-clip workflows, transcription covers the primary clip
            clip = clips[0]
            file_path = get_clip_file_path(clip)
            if not file_path:
                _set_status("Could not get media file path from first clip.", "#ff6b6b")
                _set_progress(0, False)
                return

            _set_status(f"Sending to ElevenLabs STT: {file_path.split('\\')[-1]}", "#aaaaaa")
            _set_progress(20)

            client = ElevenLabsClient(api_key)
            words = client.transcribe(file_path, language=lang_code)

            _set_progress(60)
            _state["words"] = words
            app.transcript = words  # share with other tabs

            # Build preview text for transcript panel
            preview = " ".join(w["word"] for w in words if w.get("type", "word") == "word")
            win.Find("SubsTranscript").SetPlainText(preview)

            # Generate SRT
            from src.subtitles.generator import words_to_srt
            preset_name = win.Find("SubsPreset").CurrentText
            srt = words_to_srt(words, preset_name)
            _state["srt_content"] = srt

            _set_progress(90)

            # Save SRT to temp location
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(
                suffix=".srt", delete=False,
                mode="w", encoding="utf-8", prefix="clutter_"
            )
            tmp.write(srt)
            tmp.close()
            _state["srt_path"] = tmp.name

            _set_progress(100)

            word_count = len([w for w in words if w.get("type", "word") == "word"])
            _set_status(
                f"Transcript ready: {word_count} words. "
                "Click 'Create Subtitle Track' to add to timeline.",
                "#66bb6a",
            )

            win.Find("SubsCreateTrackBtn").Enabled = True
            win.Find("SubsExportSrtBtn").Enabled = True
            win.Find("SubsExportTxtBtn").Enabled = True
            app.settings.add_stat("total_subtitles_generated", 1)
            _set_progress(0, False)

        except Exception as e:
            log.error("Generate thread error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
            _set_progress(0, False)
        finally:
            win.Find("SubsGenerateBtn").Enabled = True

    def _create_track_thread() -> None:
        try:
            from src.subtitles.generator import import_srt_to_timeline

            win.Find("SubsCreateTrackBtn").Enabled = False
            _set_status("Adding subtitle track to timeline...", "#aaaaaa")

            if not _state["srt_path"]:
                _set_status("Generate transcript first.", "#ff6b6b")
                return

            ok = import_srt_to_timeline(
                app.resolve, _state["srt_path"], app.timeline
            )
            if ok:
                _set_status("Subtitle track created in timeline.", "#66bb6a")
            else:
                _set_status(
                    "Could not auto-import SRT. "
                    f"File saved at: {_state['srt_path']} — import manually via Media Pool.",
                    "#ffa726",
                )
        except Exception as e:
            log.error("Create track error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
        finally:
            win.Find("SubsCreateTrackBtn").Enabled = True

    def _export_srt(ev: Any) -> None:
        try:
            from src.subtitles.exporter import export_srt
            import os

            if not _state["srt_content"]:
                _set_status("Generate transcript first.", "#ff6b6b")
                return

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            path = os.path.join(desktop, "subtitles.srt")
            export_srt(_state["srt_content"], path)
            _set_status(f"SRT exported to: {path}", "#66bb6a")
        except Exception as e:
            _set_status(f"Export error: {e}", "#ff6b6b")

    def _export_txt(ev: Any) -> None:
        try:
            from src.subtitles.exporter import export_txt
            import os

            if not _state["words"]:
                _set_status("Generate transcript first.", "#ff6b6b")
                return

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            path = os.path.join(desktop, "transcript.txt")
            text = " ".join(w["word"] for w in _state["words"] if w.get("type") == "word")
            export_txt(text, path)
            _set_status(f"TXT exported to: {path}", "#66bb6a")
        except Exception as e:
            _set_status(f"Export error: {e}", "#ff6b6b")

    def on_generate(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_generate_thread, daemon=True).start()

    def on_create_track(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_create_track_thread, daemon=True).start()

    def on_preset_changed(ev: Any) -> None:
        app.settings.set("subtitle_preset", win.Find("SubsPreset").CurrentText)

    win.On.SubsSaveKey.Clicked = on_save_key
    win.On.SubsGenerateBtn.Clicked = on_generate
    win.On.SubsCreateTrackBtn.Clicked = on_create_track
    win.On.SubsExportSrtBtn.Clicked = _export_srt
    win.On.SubsExportTxtBtn.Clicked = _export_txt
    win.On.SubsPreset.CurrentIndexChanged = on_preset_changed
