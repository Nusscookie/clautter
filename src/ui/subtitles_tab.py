"""Subtitles tab — ElevenLabs STT transcript generation and subtitle track creation."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)

_LANGUAGES = [
    ("Auto-detect", ""), ("English", "en"), ("German", "de"), ("French", "fr"),
    ("Spanish", "es"), ("Italian", "it"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Dutch", "nl"), ("Swedish", "sv"),
    ("Norwegian", "no"), ("Danish", "da"), ("Mandarin (Simplified)", "zh"),
]
_LANG_LABELS = [l for l, _ in _LANGUAGES]
_LANG_CODES  = {l: c for l, c in _LANGUAGES}

_PRESETS = ["YouTube", "Standard", "TikTok", "Alex Hormozi Style"]


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SUBTITLES  —  Generate captions via ElevenLabs Speech-to-Text",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── API key ──
    api_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    api_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(api_card, text="ELEVENLABS API",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    key_row = ctk.CTkFrame(api_card, fg_color="transparent")
    key_row.pack(fill="x", padx=10, pady=(0, 4))
    key_row.grid_columnconfigure(0, weight=1)

    w["api_key"] = ctk.CTkEntry(key_row, placeholder_text="Enter ElevenLabs API key...",
                                 show="*")
    w["api_key"].grid(row=0, column=0, sticky="ew", padx=(0, 6))

    w["save_key_btn"] = ctk.CTkButton(key_row, text="Save", width=70)
    w["save_key_btn"].grid(row=0, column=1)

    w["key_status"] = ctk.CTkLabel(api_card, text="", font=ctk.CTkFont(size=10),
                                    text_color="#aaaaaa", anchor="w")
    w["key_status"].pack(fill="x", padx=10, pady=(0, 8))

    # ── Settings row ──
    settings_row = ctk.CTkFrame(parent, fg_color="transparent")
    settings_row.pack(fill="x", padx=10, pady=4)
    settings_row.grid_columnconfigure((0, 1), weight=1)

    lang_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    lang_frame.grid(row=0, column=0, padx=(0, 4), sticky="ew")
    ctk.CTkLabel(lang_frame, text="Language",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["language"] = ctk.CTkComboBox(lang_frame, values=_LANG_LABELS, state="readonly")
    w["language"].set("Auto-detect")
    w["language"].pack(fill="x")

    preset_frame = ctk.CTkFrame(settings_row, fg_color="transparent")
    preset_frame.grid(row=0, column=1, padx=(4, 0), sticky="ew")
    ctk.CTkLabel(preset_frame, text="Style Preset",
                 font=ctk.CTkFont(size=10), text_color="#aaaaaa").pack(anchor="w")
    w["preset"] = ctk.CTkComboBox(preset_frame, values=_PRESETS, state="readonly")
    w["preset"].set("YouTube")
    w["preset"].pack(fill="x")

    # ── Action buttons ──
    btn_row1 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row1.pack(fill="x", padx=10, pady=(6, 2))
    btn_row1.grid_columnconfigure((0, 1), weight=1)

    w["generate_btn"] = ctk.CTkButton(btn_row1, text="Generate Transcript",
                                       fg_color="#1565c0", hover_color="#1976d2",
                                       font=ctk.CTkFont(weight="bold"))
    w["generate_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["create_track_btn"] = ctk.CTkButton(btn_row1, text="Create Subtitle Track",
                                           fg_color="#2a2a2a", hover_color="#3a3a3a",
                                           state="disabled")
    w["create_track_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    btn_row2 = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row2.pack(fill="x", padx=10, pady=2)
    btn_row2.grid_columnconfigure((0, 1), weight=1)

    w["export_srt_btn"] = ctk.CTkButton(btn_row2, text="Export SRT",
                                         fg_color="#2a2a2a", hover_color="#3a3a3a",
                                         state="disabled")
    w["export_srt_btn"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

    w["export_txt_btn"] = ctk.CTkButton(btn_row2, text="Export TXT",
                                         fg_color="#2a2a2a", hover_color="#3a3a3a",
                                         state="disabled")
    w["export_txt_btn"].grid(row=0, column=1, padx=(4, 0), sticky="ew")

    # ── Progress ──
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(4, 0))

    w["status"] = ctk.CTkLabel(
        parent, text="Enter API key and click Generate Transcript.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    _divider(parent)

    # ── Transcript panel ──
    ctk.CTkLabel(parent, text="TRANSCRIPT  (editable)",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["transcript"] = ctk.CTkTextbox(parent, height=180,
                                      font=ctk.CTkFont(size=12))
    w["transcript"].pack(fill="x", padx=10, pady=(0, 12))
    w["transcript"].insert("0.0", "Transcript will appear here after generation...")

    parent._w = w


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


def _unique_name(project: Any, base: str) -> str:
    try:
        existing = {
            project.GetTimelineByIndex(i + 1).GetName()
            for i in range(project.GetTimelineCount())
        }
    except Exception:
        existing = set()
    name = base
    i = 2
    while name in existing:
        name = f"{base}_{i}"
        i += 1
    return name


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "words": [],
        "srt_content": "",
        "srt_path": "",
        "timeline_choice": ("new", None),
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(value: float, visible: bool = True) -> None:
        def _apply() -> None:
            if visible:
                w["progress"].pack(in_=w["progress_frame"], fill="x")
                w["progress"].set(value / 100.0)
            else:
                w["progress"].pack_forget()
        _ui(_apply)

    def set_btn(name: str, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        _ui(lambda: w[name].configure(state=state))

    # Load saved API key
    saved_key = app.settings.api_key
    if saved_key:
        w["api_key"].insert(0, saved_key)
        w["key_status"].configure(text="API key loaded from settings.")

    saved_preset = app.settings.get("subtitle_preset", "YouTube")
    if saved_preset in _PRESETS:
        w["preset"].set(saved_preset)

    def on_save_key() -> None:
        key = w["api_key"].get().strip()
        if key:
            app.settings.api_key = key
            w["key_status"].configure(text="API key saved.")
        else:
            w["key_status"].configure(text="Key is empty — not saved.")

    def _generate_thread() -> None:
        try:
            from src.subtitles.elevenlabs import ElevenLabsClient
            from src.utils.resolve_api import get_clip_file_path

            set_btn("generate_btn", False)
            set_progress(0, True)
            set_status("Checking configuration...")

            api_key = w["api_key"].get().strip()
            if not api_key:
                set_status("API key is empty. Enter your ElevenLabs key first.", "#ff6b6b")
                set_progress(0, False)
                return

            lang_label = w["language"].get()
            lang_code = _LANG_CODES.get(lang_label, "")

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                set_status("No clips found on Video Track 1.", "#ff6b6b")
                set_progress(0, False)
                return

            file_path = get_clip_file_path(clips[0])
            if not file_path:
                set_status("Could not get media file path from first clip.", "#ff6b6b")
                set_progress(0, False)
                return

            set_status(f"Sending to ElevenLabs STT: {file_path.split(chr(92))[-1]}")
            set_progress(20)

            client = ElevenLabsClient(api_key)
            words = client.transcribe(file_path, language=lang_code)
            set_progress(60)

            _state["words"] = words
            app.transcript = words

            preview = " ".join(w2["word"] for w2 in words if w2.get("type", "word") == "word")
            _ui(lambda: (
                w["transcript"].delete("0.0", "end"),
                w["transcript"].insert("0.0", preview),
            ))

            from src.subtitles.generator import words_to_srt
            preset_name = w["preset"].get()
            srt = words_to_srt(words, preset_name)
            _state["srt_content"] = srt

            set_progress(90)

            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                suffix=".srt", delete=False,
                mode="w", encoding="utf-8", prefix="clutter_"
            )
            tmp.write(srt)
            tmp.close()
            _state["srt_path"] = tmp.name

            set_progress(100)
            word_count = len([w2 for w2 in words if w2.get("type", "word") == "word"])
            set_status(
                f"Transcript ready: {word_count} words. "
                "Click 'Create Subtitle Track' to add to timeline.",
                "#66bb6a",
            )
            set_btn("create_track_btn", True)
            set_btn("export_srt_btn", True)
            set_btn("export_txt_btn", True)
            app.settings.add_stat("total_subtitles_generated", 1)
            set_progress(0, False)

        except Exception as e:
            log.error("Generate thread error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
            set_progress(0, False)
        finally:
            set_btn("generate_btn", True)

    def _create_track_thread() -> None:
        try:
            from src.subtitles.generator import import_srt_to_timeline

            set_btn("create_track_btn", False)

            if not _state["srt_path"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return

            _mode, _target_tl = _state["timeline_choice"]
            if _mode == "existing" and _target_tl is not None:
                app.project.SetCurrentTimeline(_target_tl)
                app.refresh_timeline()
                set_status(f"Adding subtitle track to '{_target_tl.GetName()}'...")
            elif _mode == "new":
                if not app.timeline:
                    set_status("No active timeline. Open a timeline in Resolve first.", "#ff6b6b")
                    return
                set_status(f"Adding subtitle track to '{app.timeline.GetName()}'...")
            else:
                set_status("Adding subtitle track to current timeline...")

            ok = import_srt_to_timeline(app.resolve, _state["srt_path"], app.timeline)
            if ok:
                set_status(
                    "Subtitle track created. If empty, drag SRT from Media Pool onto the track.",
                    "#66bb6a",
                )
            else:
                set_status(
                    f"Could not auto-import SRT. File saved at: {_state['srt_path']}",
                    "#ffa726",
                )
        except Exception as e:
            log.error("Create track error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            set_btn("create_track_btn", True)

    def on_export_srt() -> None:
        try:
            from src.subtitles.exporter import export_srt
            import os
            if not _state["srt_content"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return
            path = os.path.join(os.path.expanduser("~"), "Desktop", "subtitles.srt")
            export_srt(_state["srt_content"], path)
            set_status(f"SRT exported to: {path}", "#66bb6a")
        except Exception as e:
            set_status(f"Export error: {e}", "#ff6b6b")

    def on_export_txt() -> None:
        try:
            from src.subtitles.exporter import export_txt
            import os
            if not _state["words"]:
                set_status("Generate transcript first.", "#ff6b6b")
                return
            text = " ".join(w2["word"] for w2 in _state["words"] if w2.get("type") == "word")
            path = os.path.join(os.path.expanduser("~"), "Desktop", "transcript.txt")
            export_txt(text, path)
            set_status(f"TXT exported to: {path}", "#66bb6a")
        except Exception as e:
            set_status(f"Export error: {e}", "#ff6b6b")

    def on_generate() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_generate_thread, daemon=True).start()

    def on_create_track() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        try:
            from src.ui.timeline_dialog import show_timeline_dialog
            choice = show_timeline_dialog(frame, app.project)
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", "#ff6b6b")
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice
        threading.Thread(target=_create_track_thread, daemon=True).start()

    def on_preset_changed(value: str) -> None:
        app.settings.set("subtitle_preset", value)

    w["save_key_btn"].configure(command=on_save_key)
    w["generate_btn"].configure(command=on_generate)
    w["create_track_btn"].configure(command=on_create_track)
    w["export_srt_btn"].configure(command=on_export_srt)
    w["export_txt_btn"].configure(command=on_export_txt)
    w["preset"].configure(command=on_preset_changed)
