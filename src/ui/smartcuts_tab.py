"""Smart Cuts tab — silence detection and removal."""

from __future__ import annotations
import threading
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def build(ui: Any) -> Any:
    """Return the Smart Cuts tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "SMART CUTS  —  Remove silences from selected clips",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # Settings
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "DETECTION SETTINGS", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Silence Threshold", "Weight": 1}),
                ui.SpinBox({
                    "ID": "SCThreshold",
                    "Minimum": -80,
                    "Maximum": 0,
                    "Value": -35,
                    "SingleStep": 1,
                    "Weight": 0,
                    "MinimumSize": [80, 0],
                }),
                ui.Label({"Text": "dB", "Weight": 0}),
            ]),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Min Silence Duration", "Weight": 1}),
                ui.SpinBox({
                    "ID": "SCMinDuration",
                    "Minimum": 50,
                    "Maximum": 5000,
                    "Value": 350,
                    "SingleStep": 50,
                    "Weight": 0,
                    "MinimumSize": [80, 0],
                }),
                ui.Label({"Text": "ms", "Weight": 0}),
            ]),

            ui.HGroup({"Spacing": 8, "Weight": 0}, [
                ui.Label({"Text": "Breathing Room (padding)", "Weight": 1}),
                ui.SpinBox({
                    "ID": "SCPadding",
                    "Minimum": 0,
                    "Maximum": 1000,
                    "Value": 120,
                    "SingleStep": 10,
                    "Weight": 0,
                    "MinimumSize": [80, 0],
                }),
                ui.Label({"Text": "ms each side", "Weight": 0}),
            ]),
        ]),

        # Action buttons
        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({"ID": "SCAnalyzeBtn", "Text": "Analyze Audio", "Weight": 1}),
            ui.Button({"ID": "SCPreviewBtn", "Text": "Preview (Add Markers)", "Weight": 1,
                       "Enabled": False}),
            ui.Button({
                "ID": "SCApplyBtn",
                "Text": "Apply Cuts (New Timeline)",
                "Weight": 1,
                "Enabled": False,
                "StyleSheet": "background: #1565c0; color: white; font-weight: bold;",
            }),
        ]),

        # Progress
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.ProgressBar({
                "ID": "SCProgress",
                "Minimum": 0,
                "Maximum": 100,
                "Value": 0,
                "Weight": 0,
                "Visible": False,
            }),
            ui.Label({
                "ID": "SCStatus",
                "Text": "Ready. Select clips in the Edit page timeline, then click Analyze.",
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
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "ANALYSIS RESULTS", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.HGroup({"Spacing": 20, "Weight": 0}, [
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": "SCFoundCount",
                              "Text": "0",
                              "Weight": 0,
                              "StyleSheet": "font-size: 28px; font-weight: bold; color: #4fc3f7;",
                              "Alignment": {"AlignHCenter": True}}),
                    ui.Label({"Text": "Silences Found", "Weight": 0,
                              "Alignment": {"AlignHCenter": True},
                              "StyleSheet": "color: #888888; font-size: 10px;"}),
                ]),
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": "SCTimeSaved",
                              "Text": "0.0 s",
                              "Weight": 0,
                              "StyleSheet": "font-size: 28px; font-weight: bold; color: #66bb6a;",
                              "Alignment": {"AlignHCenter": True}}),
                    ui.Label({"Text": "Estimated Time Saved", "Weight": 0,
                              "Alignment": {"AlignHCenter": True},
                              "StyleSheet": "color: #888888; font-size: 10px;"}),
                ]),
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": "SCClipsCount",
                              "Text": "0",
                              "Weight": 0,
                              "StyleSheet": "font-size: 28px; font-weight: bold; color: #ffa726;",
                              "Alignment": {"AlignHCenter": True}}),
                    ui.Label({"Text": "Clips Analyzed", "Weight": 0,
                              "Alignment": {"AlignHCenter": True},
                              "StyleSheet": "color: #888888; font-size: 10px;"}),
                ]),
            ]),
        ]),

        ui.VGroup({"Weight": 1}, []),  # spacer

        ui.Label({
            "ID": "SCNewTimelineName",
            "Text": "",
            "Weight": 0,
            "StyleSheet": "color: #66bb6a; font-size: 11px;",
        }),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect Smart Cuts event handlers."""

    # Cached analysis results for Apply step
    _state: dict[str, Any] = {
        "silence_regions": [],  # list of (clip, [SilenceRegion])
        "total_silences": 0,
        "total_time_saved": 0.0,
        "clips": [],
    }

    def _set_status(msg: str, color: str = "#aaaaaa") -> None:
        try:
            lbl = win.Find("SCStatus")
            lbl.SetText(msg)
            lbl.StyleSheet = f"color: {color}; font-size: 11px;"
        except Exception:
            pass

    def _set_progress(value: int, visible: bool = True) -> None:
        try:
            pb = win.Find("SCProgress")
            pb.Visible = visible
            pb.Value = value
        except Exception:
            pass

    def _on_analyze_thread() -> None:
        try:
            from src.smartcuts.analyzer import detect_silences, SilenceRegion
            from src.utils.resolve_api import get_clip_file_path

            win.Find("SCAnalyzeBtn").Enabled = False
            win.Find("SCApplyBtn").Enabled = False
            win.Find("SCPreviewBtn").Enabled = False
            _set_progress(0, True)
            _set_status("Refreshing timeline...", "#aaaaaa")

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                _set_status("No clips found on Video Track 1.", "#ff6b6b")
                _set_progress(0, False)
                win.Find("SCAnalyzeBtn").Enabled = True
                return

            threshold = win.Find("SCThreshold").Value
            min_dur = win.Find("SCMinDuration").Value
            padding = win.Find("SCPadding").Value

            _state["clips"] = clips
            _state["silence_regions"] = []
            total_silences = 0
            total_ms = 0.0

            for i, clip in enumerate(clips):
                _set_status(f"Analyzing clip {i + 1} / {len(clips)}...", "#aaaaaa")
                _set_progress(int((i / len(clips)) * 90))

                file_path = get_clip_file_path(clip)
                if not file_path:
                    log.warning("Clip %d: no file path, skipping", i)
                    _state["silence_regions"].append((clip, []))
                    continue

                try:
                    regions = detect_silences(
                        file_path,
                        threshold_db=float(threshold),
                        min_duration_ms=float(min_dur),
                        padding_ms=float(padding),
                    )
                except Exception as e:
                    log.error("Analysis error for clip %d: %s", i, e)
                    regions = []

                _state["silence_regions"].append((clip, regions))
                total_silences += len(regions)
                total_ms += sum(r.duration_ms for r in regions)

            _state["total_silences"] = total_silences
            _state["total_time_saved"] = total_ms / 1000.0

            win.Find("SCFoundCount").SetText(str(total_silences))
            win.Find("SCTimeSaved").SetText(f"{_state['total_time_saved']:.1f} s")
            win.Find("SCClipsCount").SetText(str(len(clips)))

            _set_progress(100)
            if total_silences > 0:
                _set_status(
                    f"Found {total_silences} silence(s) totaling "
                    f"{_state['total_time_saved']:.1f}s across {len(clips)} clip(s). "
                    "Click Apply Cuts to create a new trimmed timeline.",
                    "#66bb6a",
                )
                win.Find("SCApplyBtn").Enabled = True
                win.Find("SCPreviewBtn").Enabled = True
            else:
                _set_status("No significant silences found. Try lowering the threshold.", "#ffa726")

            _set_progress(0, False)

        except Exception as e:
            log.error("Analyze thread error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
            _set_progress(0, False)
        finally:
            win.Find("SCAnalyzeBtn").Enabled = True

    def _on_apply_thread() -> None:
        try:
            from src.smartcuts.cutter import apply_cuts

            win.Find("SCApplyBtn").Enabled = False
            win.Find("SCAnalyzeBtn").Enabled = False
            _set_progress(0, True)
            _set_status("Creating new timeline with silence removed...", "#aaaaaa")

            def progress_cb(current: int, total: int, msg: str) -> None:
                pct = int((current / max(total, 1)) * 100)
                _set_progress(pct)
                _set_status(msg, "#aaaaaa")

            # Flatten: pass all clips (not per-clip silence data — cutter re-analyzes)
            clips = _state["clips"]
            threshold = win.Find("SCThreshold").Value
            min_dur = win.Find("SCMinDuration").Value
            padding = win.Find("SCPadding").Value

            result = apply_cuts(
                resolve=app.resolve,
                timeline=app.timeline,
                clips=clips,
                threshold_db=float(threshold),
                min_duration_ms=float(min_dur),
                padding_ms=float(padding),
                progress_callback=progress_cb,
            )

            app.refresh_timeline()
            app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
            app.settings.add_stat("total_edits", 1)

            _set_progress(100)
            _set_status(
                f"Done! New timeline: '{result.new_timeline_name}' "
                f"({result.time_saved_sec:.1f}s removed)",
                "#66bb6a",
            )
            win.Find("SCNewTimelineName").SetText(
                f"Created: \"{result.new_timeline_name}\""
            )
            _set_progress(0, False)

        except Exception as e:
            log.error("Apply thread error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
            _set_progress(0, False)
        finally:
            win.Find("SCApplyBtn").Enabled = True
            win.Find("SCAnalyzeBtn").Enabled = True

    def _on_preview_thread() -> None:
        try:
            win.Find("SCPreviewBtn").Enabled = False
            _set_status("Adding markers at silence locations...", "#aaaaaa")

            if not app.timeline:
                _set_status("No active timeline.", "#ff6b6b")
                return

            marker_count = 0
            for clip, regions in _state["silence_regions"]:
                for region in regions:
                    frame_offset = int((region.start_ms / 1000.0) * app.fps)
                    try:
                        clip.AddMarker(
                            frame_offset,
                            "Red",
                            "Silence",
                            f"Silence: {region.duration_ms:.0f}ms",
                            int((region.duration_ms / 1000.0) * app.fps),
                            "",
                        )
                        marker_count += 1
                    except Exception as me:
                        log.debug("Marker add error: %s", me)

            _set_status(
                f"Added {marker_count} marker(s) on timeline. Red markers = silences.",
                "#66bb6a",
            )
        except Exception as e:
            log.error("Preview thread error: %s", e)
            _set_status(f"Error: {e}", "#ff6b6b")
        finally:
            win.Find("SCPreviewBtn").Enabled = True

    def on_analyze(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_on_analyze_thread, daemon=True).start()

    def on_apply(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_on_apply_thread, daemon=True).start()

    def on_preview(ev: Any) -> None:
        if not app.connected:
            _set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_on_preview_thread, daemon=True).start()

    win.On.SCAnalyzeBtn.Clicked = on_analyze
    win.On.SCApplyBtn.Clicked = on_apply
    win.On.SCPreviewBtn.Clicked = on_preview
