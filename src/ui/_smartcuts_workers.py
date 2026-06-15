"""Background thread workers for the Smart Cuts tab."""

from __future__ import annotations
from typing import Any, Callable

from src.constants import COLORS
from src.utils.logger import get_logger

log = get_logger(__name__)



def analyze_thread(
    w: dict,
    app: Any,
    state: dict,
    set_status: Callable,
    set_btn: Callable,
    set_progress: Callable,
    ui: Callable,
) -> None:
    """Detect silence regions in timeline clips."""
    try:
        from src.smartcuts.analyzer import detect_silences_auto
        from src.utils.resolve_api import get_clip_file_path

        set_btn("analyze_btn", False)
        set_btn("apply_btn", False)
        set_btn("preview_btn", False)
        set_progress(0, True)
        set_status("Refreshing timeline...")

        app.refresh_timeline()
        clips = app.get_video_clips(1)
        if not clips:
            set_status("No clips found on Video Track 1.", COLORS.ERROR)
            set_progress(0, False)
            set_btn("analyze_btn", True)
            return

        threshold     = float(w["threshold"].get())
        vad_threshold = float(w["vad_threshold"].get())
        min_dur       = float(w["min_dur"].get())
        padding       = float(w["padding"].get())
        silence_method = str(app.settings.get("smartcuts_silence_method", "vad"))

        state["clips"] = clips
        state["silence_regions"] = []
        state["silence_method"] = silence_method
        total_silences = 0
        total_ms = 0.0
        _vad_fallback_warned = False

        for i, clip in enumerate(clips):
            set_status(f"Analyzing clip {i + 1} / {len(clips)}...")
            set_progress(int((i / len(clips)) * 90))

            file_path = get_clip_file_path(clip)
            if not file_path:
                state["silence_regions"].append((clip, []))
                continue

            try:
                regions = detect_silences_auto(
                    file_path,
                    method=silence_method,
                    threshold_db=threshold,
                    min_duration_ms=min_dur,
                    padding_ms=padding,
                    vad_threshold=vad_threshold,
                )
            except RuntimeError as e:
                if silence_method == "vad" and not _vad_fallback_warned:
                    _vad_fallback_warned = True
                    set_status("Silero VAD unavailable — falling back to pydub RMS", COLORS.WARNING)
                    silence_method = "rms"
                    state["silence_method"] = "rms"
                try:
                    regions = detect_silences_auto(
                        file_path,
                        method="rms",
                        threshold_db=threshold,
                        min_duration_ms=min_dur,
                        padding_ms=padding,
                    )
                except Exception as e2:
                    log.error("Analysis error clip %d: %s", i, e2)
                    regions = []
            except Exception as e:
                log.error("Analysis error clip %d: %s", i, e)
                regions = []

            state["silence_regions"].append((clip, regions))
            total_silences += len(regions)
            total_ms += sum(r.duration_ms for r in regions)

        state["total_silences"]   = total_silences
        state["total_time_saved"] = total_ms / 1000.0

        ui(lambda: w["found_count"]._val.configure(text=str(total_silences)))
        ui(lambda: w["time_saved"]._val.configure(text=f"{state['total_time_saved']:.1f} s"))
        ui(lambda: w["clips_count"]._val.configure(text=str(len(clips))))

        set_progress(100)
        if total_silences > 0:
            set_status(
                f"Found {total_silences} silence(s) totaling "
                f"{state['total_time_saved']:.1f}s. Click Apply Cuts.",
                COLORS.SUCCESS,
            )
            set_btn("apply_btn", True)
            set_btn("preview_btn", True)
        else:
            set_status("No significant silences found. Try lowering the threshold.", COLORS.WARNING)
        set_progress(0, False)

    except Exception as e:
        log.error("Analyze thread error: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
        set_progress(0, False)
    finally:
        set_btn("analyze_btn", True)


def apply_thread(
    w: dict,
    app: Any,
    state: dict,
    set_status: Callable,
    set_btn: Callable,
    set_progress: Callable,
    ui: Callable,
) -> None:
    """Build a new timeline with silences removed."""
    try:
        from src.smartcuts.cutter import apply_cuts

        _mode, _target_tl = state["timeline_choice"]
        _existing_retake_track = state.get("retake_track_index")
        set_btn("apply_btn", False)
        set_btn("analyze_btn", False)
        set_progress(0, True)

        # Warn if source timeline has content on tracks above Video 1 that will stay
        # at original timecodes (cuts shift timing, so B-Roll/Subtitle will be out of sync).
        _source_tl = _target_tl if _target_tl is not None else app.timeline
        _other_track_warning = ""
        if _source_tl:
            try:
                _vcount = _source_tl.GetTrackCount("video")
                _has_other = any(
                    bool(_source_tl.GetItemListInTrack("video", _ti))
                    for _ti in range(2, _vcount + 1)
                )
                if _has_other:
                    _other_track_warning = (
                        "  Warning: B-Roll/Subtitle tracks kept as-is — "
                        "re-sync them manually after cuts."
                    )
            except Exception:
                pass

        if _target_tl is not None:
            set_status(f"Applying cuts to '{_target_tl.GetName()}'...")
        else:
            set_status("Creating new timeline with silence removed...")

        _detect_retakes  = bool(w["retake_cb"].get())
        _delete_retakes  = _detect_retakes and bool(w["delete_retakes_cb"].get())
        _silence_method  = str(app.settings.get("smartcuts_silence_method", "vad"))
        _retake_method   = str(app.settings.get("smartcuts_retake_method", "spacy"))
        _vad_threshold   = float(w["vad_threshold"].get())
        _threshold_db    = float(w["threshold"].get())

        def progress_cb(current: int, total: int, msg: str) -> None:
            set_progress(int((current / max(total, 1)) * 100))
            set_status(msg)

        result = apply_cuts(
            resolve=app.resolve,
            timeline=app.timeline,
            clips=state["clips"],
            threshold_db=_threshold_db,
            min_duration_ms=float(w["min_dur"].get()),
            padding_ms=float(w["padding"].get()),
            progress_callback=progress_cb,
            target_timeline=_target_tl,
            detect_retakes=_detect_retakes,
            delete_retakes=_delete_retakes,
            existing_retake_track=_existing_retake_track,
            silence_method=_silence_method,
            retake_method=_retake_method,
            vad_threshold=_vad_threshold,
        )

        app.refresh_timeline()
        if result.segment_records:
            app.smartcuts_segments = result.segment_records
        app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
        app.settings.add_stat("total_edits", 1)

        if _delete_retakes and result.retakes_found:
            retake_note = f", {result.retakes_found} retake(s) deleted"
        elif result.retakes_found:
            retake_note = f", {result.retakes_found} retake(s) isolated on track {result.retake_track_index}"
        else:
            retake_note = ""
        set_progress(100)
        set_status(
            f"Done! '{result.new_timeline_name}' "
            f"({result.time_saved_sec:.1f}s removed{retake_note}).{_other_track_warning}",
            COLORS.WARNING if _other_track_warning else COLORS.SUCCESS,
        )
        ui(lambda: w["new_timeline_lbl"].configure(
            text=f"Created: \"{result.new_timeline_name}\""))
        set_progress(0, False)

    except Exception as e:
        log.error("Apply thread error: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
        set_progress(0, False)
    finally:
        set_btn("apply_btn", True)
        set_btn("analyze_btn", True)


def preview_thread(
    app: Any,
    state: dict,
    set_status: Callable,
    set_btn: Callable,
) -> None:
    """Add red markers at detected silence positions."""
    try:
        set_btn("preview_btn", False)
        set_status("Adding markers at silence locations...")

        if not app.timeline:
            set_status("No active timeline.", COLORS.ERROR)
            return

        marker_count = 0
        for clip, regions in state["silence_regions"]:
            for region in regions:
                frame_offset = int((region.start_ms / 1000.0) * app.fps)
                try:
                    clip.AddMarker(
                        frame_offset, "Red", "Silence",
                        f"Silence: {region.duration_ms:.0f}ms",
                        int((region.duration_ms / 1000.0) * app.fps), "",
                    )
                    marker_count += 1
                except Exception as me:
                    log.debug("Marker add error: %s", me)

        set_status(f"Added {marker_count} marker(s). Red markers = silences.", COLORS.SUCCESS)
    except Exception as e:
        log.error("Preview thread error: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
    finally:
        set_btn("preview_btn", True)
