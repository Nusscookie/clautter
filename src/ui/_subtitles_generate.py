"""Transcript generation worker for the Subtitles tab.

Extracted from _subtitles_workers.py so each worker file stays under 200 lines.
"""

from __future__ import annotations
import tempfile
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def generate_thread(
    w: dict,
    frame: Any,
    app: Any,
    state: dict,
    lang_codes: dict[str, str],
    whisper_model_map: dict[str, str],
    set_status: Callable,
    set_btn: Callable,
    set_progress: Callable,
    ui: Callable,
) -> None:
    """Transcribe timeline audio via ElevenLabs or local Whisper."""
    try:
        import shutil
        import tempfile as _tmpmod
        from src.utils.resolve_api import get_clip_file_path
        from src.utils.audio import extract_cut_audio

        set_btn("generate_btn", False)
        set_progress(0, True)
        set_status("Checking configuration...")

        provider = w["provider"].get()
        lang_label = w["language"].get()
        lang_code = lang_codes.get(lang_label, "")

        app.refresh_timeline()
        clips = app.get_video_clips(1)
        if not clips:
            set_status("No clips found on Video Track 1.", "#ff6b6b")
            set_progress(0, False)
            return

        _stt_tmp = _tmpmod.mkdtemp(prefix="clutter_stt_")
        try:
            set_status("Extracting timeline audio...")
            _cut = extract_cut_audio(clips, _stt_tmp, app.fps)
            if _cut:
                audio_for_stt = _cut
                state["words_are_remapped"] = True
                log.info("Using cut timeline audio (%d clips)", len(clips))
            else:
                audio_for_stt = get_clip_file_path(clips[0])
                state["words_are_remapped"] = False
                if not audio_for_stt:
                    set_status("Could not get media file path.", "#ff6b6b")
                    set_progress(0, False)
                    return
                log.info("Using full source file (cut extraction unavailable)")

            set_progress(20)

            if provider == "Local Whisper":
                from src.subtitles.whisper_client import WhisperClient
                model_label = w["whisper_model"].get()
                model_name = whisper_model_map.get(model_label, "base")
                set_status(
                    f"Loading Whisper {model_label} — first run downloads model automatically..."
                )
                client = WhisperClient(model_name)
                words = client.transcribe(audio_for_stt, language=lang_code)
            else:
                from src.subtitles.elevenlabs import ElevenLabsClient
                api_key = (app.settings.api_key or "").strip()
                if not api_key:
                    set_status("ElevenLabs API key not set. Open Settings (⚙) to add it.", "#ff6b6b")
                    set_progress(0, False)
                    return
                _name = audio_for_stt.replace("\\", "/").split("/")[-1]
                set_status(f"Sending to ElevenLabs STT: {_name}")
                client = ElevenLabsClient(api_key)
                words = client.transcribe(audio_for_stt, language=lang_code)
        finally:
            shutil.rmtree(_stt_tmp, ignore_errors=True)

        set_progress(60)

        state["words"] = words
        app.transcript = words

        preview = " ".join(w2["word"] for w2 in words if w2.get("type", "word") == "word")
        ui(lambda: (
            w["transcript"].delete("0.0", "end"),
            w["transcript"].insert("0.0", preview),
        ))

        from src.subtitles.generator import words_to_srt
        preset_name = w["preset"].get()
        srt = words_to_srt(words, preset_name,
                           words_per_line=int(w["wpl_slider"].get()),
                           lines_per_block=int(w["lpb_slider"].get()),
                           uppercase=w["caps_check"].get() == 1)
        state["srt_content"] = srt

        set_progress(90)

        tmp = tempfile.NamedTemporaryFile(
            suffix=".srt", delete=False,
            mode="w", encoding="utf-8", prefix="clutter_"
        )
        tmp.write(srt)
        tmp.close()
        state["srt_path"] = tmp.name

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
