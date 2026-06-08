"""Background thread workers for the Auto Zooms tab."""

from __future__ import annotations
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)

_MODE_SIGMA: dict[str, float] = {"Conservative": 2.0, "Standard": 1.0, "High Energy": 0.5}


def analyze_thread(
    w: dict,
    app: Any,
    state: dict,
    set_status: Callable,
    set_btn: Callable,
    set_progress: Callable,
    ui: Callable,
) -> None:
    """Detect zoom points via face detection or RMS audio peaks."""
    try:
        from src.zooms.analyzer import detect_zoom_points_auto
        from src.utils.resolve_api import get_clip_file_path

        set_btn("analyze_btn", False)
        set_btn("apply_btn", False)
        set_btn("preview_btn", False)
        set_progress(0, True)

        detect_method = w["detect_method"].get()
        use_face = detect_method == "Face Detection"

        if use_face:
            set_status("Analyzing video for faces...")
        else:
            set_status("Analyzing audio for high-energy moments...")

        app.refresh_timeline()
        clips = app.get_video_clips(1)
        if not clips:
            set_status("No clips found on Video Track 1.", "#ff6b6b")
            set_progress(0, False)
            return

        mode_name   = w["mode"].get()
        sigma       = _MODE_SIGMA.get(mode_name, 1.0)
        max_per_min = int(w["max_per_min"].get())
        zoom_pct    = w["zoom_slider"].get() / 100.0

        all_zoom_points = []
        state["clips"] = clips
        fallback_used = False

        for i, clip in enumerate(clips):
            set_progress(int((i / len(clips)) * 90))
            file_path = get_clip_file_path(clip)
            if not file_path:
                continue
            try:
                common_kwargs = dict(
                    file_path=file_path,
                    clip_start_frame=clip.GetStart(),
                    src_start_frame=clip.GetSourceStartFrame(),
                    src_end_frame=clip.GetSourceEndFrame(),
                    fps=app.fps,
                    max_per_minute=max_per_min,
                    zoom_amount=zoom_pct,
                )
                if use_face:
                    pts = detect_zoom_points_auto(
                        method="face",
                        sample_interval_sec=1.0,
                        **common_kwargs,
                    )
                    if not fallback_used and pts == [] and detect_method == "Face Detection":
                        pass  # empty is valid — face just not found in this clip
                else:
                    pts = detect_zoom_points_auto(
                        method="rms",
                        sigma_multiplier=sigma,
                        **common_kwargs,
                    )
                all_zoom_points.extend(pts)
            except Exception as e:
                log.error("Zoom analysis error clip %d: %s", i, e)
                if use_face and "opencv" in str(e).lower():
                    set_status(
                        "opencv-python not installed. "
                        "Run: pip install opencv-python",
                        "#ff6b6b",
                    )
                    set_progress(0, False)
                    return

        state["zoom_points"] = all_zoom_points
        app.zoom_points = all_zoom_points
        _n = len(all_zoom_points)
        ui(lambda: w["found_count"]._val.configure(text=str(_n)))

        set_progress(100)
        method_label = "face" if use_face else "audio"
        if all_zoom_points:
            set_status(
                f"Found {_n} zoom point(s) via {method_label} detection. "
                "Click Apply Zooms to create a new timeline.",
                "#66bb6a",
            )
            set_btn("apply_btn", True)
            set_btn("preview_btn", True)
        else:
            hint = "Check that faces are visible in the clip." if use_face else "Try 'High Energy' mode."
            set_status(f"No zoom points detected. {hint}", "#E8903A")
        set_progress(0, False)

    except Exception as e:
        log.error("Zoom analyze error: %s", e)
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
    """Build a timeline with zoom effects at the detected points."""
    try:
        from src.zooms.applier import apply_zooms

        _mode, _target_tl = state["timeline_choice"]["timeline"]
        set_btn("apply_btn", False)
        set_btn("analyze_btn", False)
        set_progress(0, True)
        if _target_tl is not None:
            set_status(f"Appending zooms to '{_target_tl.GetName()}'...")
        else:
            set_status("Applying zooms to new timeline...")

        fade     = w["fade_zoom"].get() == 1
        zoom_pct = w["zoom_slider"].get() / 100.0

        def progress_cb(cur: int, total: int, msg: str) -> None:
            set_progress(int((cur / max(total, 1)) * 100))
            set_status(msg)

        result = apply_zooms(
            resolve=app.resolve,
            timeline=app.timeline,
            clips=state["clips"],
            zoom_points=state["zoom_points"],
            fade=fade,
            zoom_amount=zoom_pct,
            progress_callback=progress_cb,
            target_timeline=_target_tl,
        )

        app.refresh_timeline()
        app.settings.add_stat("total_zooms_applied", result.zooms_applied)
        app.settings.add_stat("total_edits", 1)

        ui(lambda: w["applied_count"]._val.configure(text=str(result.zooms_applied)))

        if result.zooms_applied == 0:
            set_status(
                f"Timeline '{result.new_timeline_name}' built but no zooms applied. "
                "Check that zoom points were detected.",
                "#E8903A",
            )
            set_progress(0, False)
            return

        set_progress(100)
        set_status(
            f"Done! {result.zooms_applied} zoom(s) applied. "
            f"New timeline: '{result.new_timeline_name}'",
            "#66bb6a",
        )
        ui(lambda: w["new_timeline_lbl"].configure(
            text=f"Created: \"{result.new_timeline_name}\""))
        set_progress(0, False)

    except Exception as e:
        log.error("Zoom apply error: %s", e)
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
    """Add purple markers at detected zoom positions."""
    try:
        set_btn("preview_btn", False)
        set_status("Adding zoom markers to timeline...")

        if not state["zoom_points"] or not app.timeline:
            set_status("Analyze first.", "#ff6b6b")
            return

        for zp in state["zoom_points"]:
            try:
                app.timeline.AddMarker(
                    int(zp.timeline_frame), "Purple", "Zoom",
                    f"Zoom {int(zp.zoom_amount * 100)}%",
                    int(zp.duration_frames), "",
                )
            except Exception as me:
                log.debug("Marker add error: %s", me)

        set_status(
            f"Added {len(state['zoom_points'])} purple markers for zoom points.",
            "#66bb6a",
        )
    except Exception as e:
        log.error("Preview error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
    finally:
        set_btn("preview_btn", True)
