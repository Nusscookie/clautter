"""Background thread workers for the Smart Cuts tab."""

from __future__ import annotations
from typing import Any, Callable

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
        from src.smartcuts.analyzer import detect_silences
        from src.utils.resolve_api import get_clip_file_path

        set_btn("analyze_btn", False)
        set_btn("apply_btn", False)
        set_btn("preview_btn", False)
        set_progress(0, True)
        set_status("Refreshing timeline...")

        app.refresh_timeline()
        clips = app.get_video_clips(1)
        if not clips:
            set_status("No clips found on Video Track 1.", "#ff6b6b")
            set_progress(0, False)
            set_btn("analyze_btn", True)
            return

        threshold = float(w["threshold"].get())
        min_dur   = float(w["min_dur"].get())
        padding   = float(w["padding"].get())

        state["clips"] = clips
        state["silence_regions"] = []
        total_silences = 0
        total_ms = 0.0

        for i, clip in enumerate(clips):
            set_status(f"Analyzing clip {i + 1} / {len(clips)}...")
            set_progress(int((i / len(clips)) * 90))

            file_path = get_clip_file_path(clip)
            if not file_path:
                state["silence_regions"].append((clip, []))
                continue

            try:
                regions = detect_silences(
                    file_path,
                    threshold_db=threshold,
                    min_duration_ms=min_dur,
                    padding_ms=padding,
                )
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
                "#66bb6a",
            )
            set_btn("apply_btn", True)
            set_btn("preview_btn", True)
        else:
            set_status("No significant silences found. Try lowering the threshold.", "#ffa726")
        set_progress(0, False)

    except Exception as e:
        log.error("Analyze thread error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
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
        set_btn("apply_btn", False)
        set_btn("analyze_btn", False)
        set_progress(0, True)
        if _target_tl is not None:
            set_status(f"Appending cuts to '{_target_tl.GetName()}'...")
        else:
            set_status("Creating new timeline with silence removed...")

        def progress_cb(current: int, total: int, msg: str) -> None:
            set_progress(int((current / max(total, 1)) * 100))
            set_status(msg)

        result = apply_cuts(
            resolve=app.resolve,
            timeline=app.timeline,
            clips=state["clips"],
            threshold_db=float(w["threshold"].get()),
            min_duration_ms=float(w["min_dur"].get()),
            padding_ms=float(w["padding"].get()),
            progress_callback=progress_cb,
            target_timeline=_target_tl,
        )

        app.refresh_timeline()
        app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
        app.settings.add_stat("total_edits", 1)

        set_progress(100)
        set_status(
            f"Done! New timeline: '{result.new_timeline_name}' "
            f"({result.time_saved_sec:.1f}s removed)",
            "#66bb6a",
        )
        ui(lambda: w["new_timeline_lbl"].configure(
            text=f"Created: \"{result.new_timeline_name}\""))
        set_progress(0, False)

    except Exception as e:
        log.error("Apply thread error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
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
            set_status("No active timeline.", "#ff6b6b")
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

        set_status(f"Added {marker_count} marker(s). Red markers = silences.", "#66bb6a")
    except Exception as e:
        log.error("Preview thread error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
    finally:
        set_btn("preview_btn", True)
