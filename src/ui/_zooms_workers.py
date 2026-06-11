"""Background thread workers for the Auto Zooms tab."""

from __future__ import annotations
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def _clip_for_frame(clips: list, timeline_frame: int) -> Any:
    """Return the clip whose timeline span contains ``timeline_frame``, or None."""
    for clip in clips:
        try:
            if clip.GetStart() <= timeline_frame < clip.GetEnd():
                return clip
        except Exception:
            continue
    return None


def _broll_zoom_points(app: Any, zoom_pct: float, zoom_dur_frames: int) -> list:
    """Build ZoomPoints at B-roll insertion timecodes (empty if no B-roll run)."""
    from src.zooms.analyzer import ZoomPoint

    results = getattr(app, "broll_placer_results", None) or []
    if not results:
        return []
    try:
        tl_start = int(app.timeline.GetStartFrame())
    except Exception:
        tl_start = 0

    points = []
    for r in results:
        if not getattr(r, "placed", False):
            continue
        sec = getattr(r, "segment_start_sec", None)
        if sec is None:
            continue
        frame = tl_start + round(sec * app.fps)
        points.append(ZoomPoint(
            timeline_frame=int(frame),
            duration_frames=zoom_dur_frames,
            zoom_amount=zoom_pct,
        ))
    return points


def _apply_face_centering(zoom_points: list, clips: list, app: Any, set_progress: Callable) -> None:
    """Fill pan/tilt on each ZoomPoint by sampling the speaker's face in-place.

    Maps each point's timeline_frame back to its owning clip and source frame, then
    asks face_offset_at for a normalized offset. No face / no clip → leave at 0
    (plain center zoom for that point). Raises ImportError if OpenCV is missing.
    """
    from src.zooms.face_analyzer import face_offset_at
    from src.utils.resolve_api import get_clip_file_path

    total = max(len(zoom_points), 1)
    for i, zp in enumerate(zoom_points):
        set_progress(50 + int((i / total) * 45))
        clip = _clip_for_frame(clips, zp.timeline_frame)
        if clip is None:
            continue
        file_path = get_clip_file_path(clip)
        if not file_path:
            continue
        try:
            src_frame = clip.GetSourceStartFrame() + (zp.timeline_frame - clip.GetStart())
            offset = face_offset_at(file_path, int(src_frame), fps=app.fps)
        except FileNotFoundError:
            continue
        if offset is not None:
            zp.pan, zp.tilt = offset


def analyze_thread(
    w: dict,
    app: Any,
    state: dict,
    set_status: Callable,
    set_btn: Callable,
    set_progress: Callable,
    ui: Callable,
) -> None:
    """Detect zoom points at cut points (+ B-roll), optionally centered on the face."""
    try:
        from src.zooms.analyzer import (
            detect_zoom_points_from_cuts, enforce_spacing, _ZOOM_DURATION_MS,
        )

        set_btn("analyze_btn", False)
        set_btn("apply_btn", False)
        set_btn("preview_btn", False)
        set_progress(0, True)
        set_status("Reading cut points from the timeline...")

        app.refresh_timeline()
        clips = app.get_video_clips(1)
        if not clips:
            set_status("No clips found on Video Track 1.", "#ff6b6b")
            set_progress(0, False)
            return

        try:
            min_take = float(w["min_take"].get())
        except ValueError:
            min_take = 2.0
        try:
            max_per_min = int(w["max_per_min"].get())
        except ValueError:
            max_per_min = 4
        zoom_pct = w["zoom_slider"].get() / 100.0
        track_face = bool(w["track_face"].get())

        state["clips"] = clips
        set_progress(20)

        points = detect_zoom_points_from_cuts(
            clips, fps=app.fps, min_take_sec=min_take,
            max_per_minute=max_per_min, zoom_amount=zoom_pct,
        )

        # Merge B-roll placements (bonus triggers), then re-space the union.
        zoom_dur_frames = max(1, int((_ZOOM_DURATION_MS / 1000.0) * app.fps))
        points += _broll_zoom_points(app, zoom_pct, zoom_dur_frames)
        points = enforce_spacing(points, app.fps, max_per_min)

        if not points:
            set_status(
                "No cut points found. Run Smart Cuts first, or lower Min Take Length "
                "(the timeline has no takes long enough).",
                "#ff6b6b",
            )
            set_progress(0, False)
            return

        if track_face:
            set_status("Centering zooms on the speaker...")
            try:
                _apply_face_centering(points, clips, app, set_progress)
            except ImportError:
                set_status(
                    "opencv-python not installed — applying plain center zooms. "
                    "Run: pip install opencv-python",
                    "#E8903A",
                )

        state["zoom_points"] = points
        app.zoom_points = points
        _n = len(points)
        ui(lambda: w["found_count"]._val.configure(text=str(_n)))

        set_progress(100)
        set_status(
            f"Found {_n} zoom point(s) at your cut points. "
            "Click Apply Zooms to create a new timeline.",
            "#66bb6a",
        )
        set_btn("apply_btn", True)
        set_btn("preview_btn", True)
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

        fade     = w["zoom_style"].get().startswith("Smooth")
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
