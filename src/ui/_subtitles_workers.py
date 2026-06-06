"""Background thread workers for the Subtitles tab.

Each function is self-contained with explicit deps instead of closures,
so it can live outside setup() without any shared mutable state.
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
                api_key = w["api_key"].get().strip()
                if not api_key:
                    set_status("API key is empty. Enter your ElevenLabs key first.", "#ff6b6b")
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


def create_track_thread(
    w: dict,
    app: Any,
    state: dict,
    transcript_text: str,
    style_overrides: dict,
    preset_name: str,
    text_style: dict,
    set_status: Callable,
    set_btn: Callable,
) -> None:
    """Build and place subtitle clips on the timeline."""
    try:
        from src.subtitles.generator import import_srt_to_timeline, remap_words_to_timeline
        import tempfile as _tempfile

        set_btn("create_track_btn", False)

        if not state["words"]:
            set_status("Generate transcript first.", "#ff6b6b")
            return

        _placeholder = "Transcript will appear here after generation..."
        _orig_words = [wd for wd in state["words"] if wd.get("type", "word") == "word"]
        if transcript_text and transcript_text != _placeholder:
            _tokens = transcript_text.split()
            if len(_tokens) == len(_orig_words):
                _tok_iter = iter(_tokens)
                _words_src: list[Any] = [
                    {**wd, "word": next(_tok_iter)} if wd.get("type", "word") == "word" else wd
                    for wd in state["words"]
                ]
                log.info("Applied %d transcript edits to subtitle words", len(_tokens))
            else:
                if _orig_words:
                    t0   = _orig_words[0]["start_sec"]
                    t1   = _orig_words[-1]["end_sec"]
                    step = (t1 - t0) / max(len(_tokens), 1)
                    _words_src = [
                        {
                            "word": tok,
                            "start_sec": t0 + i * step,
                            "end_sec": t0 + (i + 1) * step,
                            "type": "word",
                        }
                        for i, tok in enumerate(_tokens)
                    ]
                    log.info(
                        "Word count changed (%d→%d) — using proportional timing fallback",
                        len(_orig_words), len(_tokens),
                    )
                    set_status(
                        f"Word count changed ({len(_orig_words)}→{len(_tokens)}) — timing approximated.",
                        "#ffa726",
                    )
                else:
                    _words_src = state["words"]
        else:
            _words_src = state["words"]

        _mode, _target_tl = state["timeline_choice"]
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

        if state.get("words_are_remapped"):
            remapped = [wd for wd in _words_src if wd.get("type", "word") == "word"]
            log.info("Words already timeline-relative (%d words)", len(remapped))
        elif app.timeline:
            try:
                clips = app.get_video_clips(1)
                tl_start = app.timeline.GetStartFrame()
                remapped = remap_words_to_timeline(_words_src, clips, app.fps, tl_start)
                log.info("Remapped %d words to current timeline", len(remapped))
            except Exception as _e:
                log.warning("Word remap failed, using original timestamps: %s", _e)
                remapped = [wd for wd in _words_src if wd.get("type", "word") == "word"]
        else:
            remapped = [wd for wd in _words_src if wd.get("type", "word") == "word"]

        from src.subtitles.generator import place_fusion_titles
        ok = place_fusion_titles(
            app.resolve, remapped, app.fps, app.timeline,
            text_style, preset_name, **style_overrides,
        )
        if not ok:
            log.info("Fusion titles failed; falling back to SRT subtitle track")
            from src.subtitles.generator import words_to_srt
            _srt_tmp = _tempfile.NamedTemporaryFile(
                suffix=".srt", delete=False, mode="w", encoding="utf-8",
                prefix="clutter_fallback_",
            )
            _srt_tmp.write(words_to_srt(remapped, preset_name, **style_overrides))
            _srt_tmp.close()
            ok = import_srt_to_timeline(app.resolve, _srt_tmp.name, app.timeline)

        if ok:
            set_status("Subtitle track created.", "#66bb6a")
        else:
            set_status(
                "Could not auto-import. Drag SRT from Media Pool to the subtitle track.",
                "#ffa726",
            )
    except Exception as e:
        log.error("Create track error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
    finally:
        set_btn("create_track_btn", True)
