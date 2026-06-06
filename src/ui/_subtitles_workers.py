"""Background thread workers for the Subtitles tab.

Each function is self-contained with explicit deps instead of closures,
so it can live outside setup() without any shared mutable state.

generate_thread lives in _subtitles_generate.py.
"""

from __future__ import annotations
import tempfile
from typing import Any, Callable

from src.ui._subtitles_generate import generate_thread  # re-export for backwards compat
from src.utils.logger import get_logger

log = get_logger(__name__)

__all__ = ["generate_thread", "create_track_thread"]


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
