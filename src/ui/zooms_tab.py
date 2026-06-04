"""Auto Zooms tab — volume-peak-based intelligent zoom cuts."""

from __future__ import annotations
import threading
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_MODES = ["Conservative", "Standard", "High Energy"]
_MODE_SIGMA = {"Conservative": 2.0, "Standard": 1.0, "High Energy": 0.5}


def build(ui: Any) -> Any:
    """Return the Auto Zooms tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "AUTO ZOOMS  —  Apply dynamic zoom cuts based on audio energy",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # Settings
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "ZOOM SETTINGS", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Energy Mode", "Weight": 1}),
                ui.ComboBox({"ID": "ZoomMode", "Weight": 1}),
            ]),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Zoom Amount", "Weight": 1}),
                ui.Slider({
                    "ID": "ZoomAmount",
                    "Minimum": 105,
                    "Maximum": 150,
                    "Value": 115,
                    "Weight": 1,
                }),
                ui.Label({"ID": "ZoomAmountLabel", "Text": "115%",
                          "Weight": 0, "MinimumSize": [40, 0],
                          "StyleSheet": "color: #4fc3f7;"}),
            ]),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Max Zooms Per Minute", "Weight": 1}),
                ui.SpinBox({
                    "ID": "ZoomMaxPerMin",
                    "Minimum": 1,
                    "Maximum": 20,
                    "Value": 4,
                    "Weight": 0,
                    "MinimumSize": [60, 0],
                }),
            ]),

            ui.HGroup({"Spacing": 12, "Weight": 0}, [
                ui.CheckBox({"ID": "ZoomFade", "Text": "Fade Zooms (Dynamic Zoom Ease)",
                             "Checked": True, "Weight": 1}),
                ui.CheckBox({"ID": "ZoomHardCut", "Text": "Hard Cut Zooms",
                             "Checked": False, "Weight": 1}),
            ]),
        ]),

        # Buttons
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({"ID": "ZoomAnalyzeBtn", "Text": "Analyze Audio", "Weight": 1}),
            ui.Button({"ID": "ZoomPreviewBtn", "Text": "Preview (Add Markers)",
                       "Weight": 1, "Enabled": False}),
            ui.Button({
                "ID": "ZoomApplyBtn",
                "Text": "Apply Zooms (New Timeline)",
                "Weight": 1,
                "Enabled": False,
                "StyleSheet": "background: #6a1b9a; color: white; font-weight: bold;",
            }),
        ]),

        # Progress
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.ProgressBar({
                "ID": "ZoomProgress",
                "Minimum": 0,
                "Maximum": 100,
                "Value": 0,
                "Visible": False,
            }),
            ui.Label({
                "ID": "ZoomStatus",
                "Text": "Click Analyze to detect high-energy moments for zooms.",
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

        # Results
        ui.HGroup({"Spacing": 12, "Weight": 0}, [
            ui.VGroup({"Spacing": 2, "Weight": 1,
                       "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
                ui.Label({"ID": "ZoomFoundCount",
                          "Text": "0",
                          "Weight": 0,
                          "StyleSheet": "font-size: 28px; font-weight: bold; color: #ab47bc;",
                          "Alignment": {"AlignHCenter": True}}),
                ui.Label({"Text": "Zoom Points Found", "Weight": 0,
                          "Alignment": {"AlignHCenter": True},
                          "StyleSheet": "color: #888888; font-size: 10px;"}),
            ]),
            ui.VGroup({"Spacing": 2, "Weight": 1,
                       "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
                ui.Label({"ID": "ZoomAppliedCount",
                          "Text": "0",
                          "Weight": 0,
                          "StyleSheet": "font-size: 28px; font-weight: bold; color: #66bb6a;",
                          "Alignment": {"AlignHCenter": True}}),
                ui.Label({"Text": "Zooms Applied", "Weight": 0,
                          "Alignment": {"AlignHCenter": True},
                          "StyleSheet": "color: #888888; font-size: 10px;"}),
            ]),
        ]),

        ui.VGroup({"Weight": 1}, []),  # spacer

        ui.Label({
            "ID": "ZoomNewTimelineName",
            "Text": "",
            "Weight": 0,
            "StyleSheet": "color: #66bb6a; font-size: 11px;",
        }),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect Auto Zooms event handlers."""

    # Populate mode dropdown
    mode_combo = win.Find("ZoomMode")
    for m in _MODES:
        mode_combo.AddItem(m)
    mode_combo.CurrentIndex = 1  # Standard

    _state: dict[str, Any] = {
        "zoom_points": [],  # list of ZoomPoint
        "clips": [],
    }

    def _set_status(msg: str, color: str = "#aaaaaa") -> None:
        try:
            lbl = win.Find("ZoomStatus")
            lbl.SetText(msg)
            lbl.StyleSheet = f"color: {color}; font-size: 11px;"
        except Exception:
            pass

    def _set_progress(value: int, visible: bool = True) -> None:
        try:
            pb = win.Find("ZoomProgress")
            pb.Visible = visible
            pb.Value = value
        except Exception:
            pass

    def on_zoom_slider(ev: Any) -> None:
        val = win.Find("ZoomAmount").Value
        win.Find("ZoomAmountLabel").SetText(f"{val}%")

    def _analyze_thread() -> None:
        try:
            from src.zooms.analyzer import detect_zoom_points
            from src.utils.resolve_api import get_clip_file_path

            win.Find("ZoomAnalyzeBtn").Enabled = False
            win.Find("ZoomApplyBtn").Enabled = False
            win.Find("ZoomPreviewBtn").Enabled = False
            _set_progress(0, True)
            _set_status("Analyzing audio for high-energy moments...", "#aaaaaa")

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                _set_status("No clips found on Video Track 1.", "#ff6b6b")
                _set_progress(0, False)
                return

            mode_name = win.Find("ZoomMode").CurrentText
            sigma = _MODE_SIGMA.get(mode_name, 1.0)
            max_per_min = win.Find("ZoomMaxPerMin").Value
            zoom_pct = win.Find("ZoomAmount").Value / 100.0

            all_zoom_points = []
            _state["clips"] = clips

            for i, clip in enumerate(clips):
                _set_progress(int((i / len(clips)) * 90))
                file_path = get_clip_file_path(clip)
                if not file_path:
                    continue
                try:
                    clip_start_frame = clip.GetStart()
                    pts = detect_zoom_points(
                        file_path=file_path,
                        clip_start_frame=clip_start_frame,
                        fps=app.fps,
                        max_per_minute=max_per_min,
                        sigma_multiplier=sigma,
                        zoom_amount=zoom_pct,
                    )
                    all_zoom_points.extend(pts)
                except Exception as e:
                    log.error("Zoom analysis error clip %d: %s", i, e)

            _state["zoom_points"] = all_zoom_points
            win.Find("ZoomFoundCount").SetText(str(len(all_zoom_points)))

            _set_progress(100)
            if all_zoom_points:
                _set_status(
                    f"Found {len(all_zoom_points)} zoom point(s). "
                    "Click Apply Zooms to create a new timeline.",
                    "#66bb6a",
                )
                win.Find("ZoomApplyBtn").Enabled = True
                win.Find("ZoomPreviewBtn").Enabled = True
            else:
                _set_status("No zoom points detected. Try 'High Energy' mode.", "#ffa726")

            _set_progress(0, False)
        except Exception as e:
            log.error("Zoom analyze thread error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
            _set_progress(0, False)
        finally:
            win.Find("ZoomAnalyzeBtn").Enabled = True

    def _apply_thread() -> None:
        try:
            from src.zooms.applier import apply_zooms

            win.Find("ZoomApplyBtn").Enabled = False
            win.Find("ZoomAnalyzeBtn").Enabled = False
            _set_progress(0, True)
            _set_status("Applying zooms to new timeline...", "#aaaaaa")

            fade = win.Find("ZoomFade").Checked
            zoom_pct = win.Find("ZoomAmount").Value / 100.0

            def progress_cb(cur: int, total: int, msg: str) -> None:
                _set_progress(int((cur / max(total, 1)) * 100))
                _set_status(msg, "#aaaaaa")

            result = apply_zooms(
                resolve=app.resolve,
                timeline=app.timeline,
                clips=_state["clips"],
                zoom_points=_state["zoom_points"],
                fade=fade,
                zoom_amount=zoom_pct,
                progress_callback=progress_cb,
            )

            app.refresh_timeline()
            app.settings.add_stat("total_zooms_applied", result.zooms_applied)
            app.settings.add_stat("total_edits", 1)

            win.Find("ZoomAppliedCount").SetText(str(result.zooms_applied))
            _set_progress(100)
            _set_status(
                f"Done! {result.zooms_applied} zoom(s) applied. "
                f"New timeline: '{result.new_timeline_name}'",
                "#66bb6a",
            )
            win.Find("ZoomNewTimelineName").SetText(
                f"Created: \"{result.new_timeline_name}\""
            )
            _set_progress(0, False)
        except Exception as e:
            log.error("Zoom apply error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
            _set_progress(0, False)
        finally:
            win.Find("ZoomApplyBtn").Enabled = True
            win.Find("ZoomAnalyzeBtn").Enabled = True

    def _preview_thread() -> None:
        try:
            win.Find("ZoomPreviewBtn").Enabled = False
            _set_status("Adding zoom markers to timeline...", "#aaaaaa")

            if not _state["zoom_points"] or not app.timeline:
                _set_status("Analyze first.", "#ff6b6b")
                return

            for zp in _state["zoom_points"]:
                try:
                    app.timeline.AddMarker(
                        int(zp.timeline_frame),
                        "Purple",
                        "Zoom",
                        f"Zoom {int(zp.zoom_amount * 100)}%",
                        int(zp.duration_frames),
                        "",
                    )
                except Exception as me:
                    log.debug("Marker add error: %s", me)

            _set_status(
                f"Added {len(_state['zoom_points'])} purple markers for zoom points.",
                "#66bb6a",
            )
        except Exception as e:
            log.error("Preview error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
        finally:
            win.Find("ZoomPreviewBtn").Enabled = True

    def on_analyze(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_analyze_thread, daemon=True).start()

    def on_apply(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_apply_thread, daemon=True).start()

    def on_preview(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_preview_thread, daemon=True).start()

    win.On.ZoomAmount.ValueChanged = on_zoom_slider
    win.On.ZoomAnalyzeBtn.Clicked = on_analyze
    win.On.ZoomApplyBtn.Clicked = on_apply
    win.On.ZoomPreviewBtn.Clicked = on_preview
