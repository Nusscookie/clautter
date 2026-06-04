"""Pace Control tab — adjust editing intensity via a single slider (scaffold)."""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# Pace level → SmartCuts parameter mappings
_PACE_PRESETS = {
    1:  {"threshold_db": -55, "min_silence_ms": 1500, "label": "Very Slow",
         "desc": "Documentary / cinematic — only remove very long pauses"},
    2:  {"threshold_db": -50, "min_silence_ms": 1200, "label": "Slow",
         "desc": "Long-form podcast / interview style"},
    3:  {"threshold_db": -45, "min_silence_ms": 900,  "label": "Relaxed",
         "desc": "Calm YouTube tutorial"},
    4:  {"threshold_db": -40, "min_silence_ms": 600,  "label": "Moderate",
         "desc": "Standard talking-head"},
    5:  {"threshold_db": -35, "min_silence_ms": 350,  "label": "YouTube",
         "desc": "Standard YouTube pacing — best all-round starting point"},
    6:  {"threshold_db": -33, "min_silence_ms": 280,  "label": "Crisp",
         "desc": "Tight YouTube / educational content"},
    7:  {"threshold_db": -30, "min_silence_ms": 220,  "label": "Snappy",
         "desc": "High-energy YouTube / commentary"},
    8:  {"threshold_db": -28, "min_silence_ms": 160,  "label": "Fast",
         "desc": "Instagram Reels / short-form"},
    9:  {"threshold_db": -25, "min_silence_ms": 120,  "label": "Very Fast",
         "desc": "TikTok-style aggressive cuts"},
    10: {"threshold_db": -22, "min_silence_ms": 80,   "label": "TikTok / Reels",
         "desc": "Maximum energy — every breath removed"},
}

# WPM and retention estimates per pace level (simplified linear models)
_WPM_ESTIMATE   = {1: 100, 2: 115, 3: 125, 4: 135, 5: 145, 6: 155, 7: 165, 8: 175, 9: 185, 10: 200}
_RETENTION_EST  = {1: 62, 2: 65, 3: 68, 4: 72, 5: 77, 6: 80, 7: 83, 8: 85, 9: 87, 10: 89}


def build(ui: Any) -> Any:
    """Return the Pace Control tab VGroup layout."""
    return ui.VGroup({"Spacing": 10, "Weight": 1}, [

        ui.Label({
            "Text": "PACE CONTROL  —  One slider for editing intensity",
            "Weight": 0,
            "StyleSheet": "font-weight: bold; color: #aaaaaa; font-size: 11px; "
                          "letter-spacing: 1px;",
        }),

        # Slider
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 10px;"}, [
            ui.HGroup({"Spacing": 12, "Weight": 0}, [
                ui.Label({"Text": "Slow", "Weight": 0,
                          "StyleSheet": "color: #888888;"}),
                ui.Slider({
                    "ID": "PaceSlider",
                    "Minimum": 1,
                    "Maximum": 10,
                    "Value": 5,
                    "Orientation": "Horizontal",
                    "Weight": 1,
                }),
                ui.Label({"Text": "Fast", "Weight": 0,
                          "StyleSheet": "color: #888888;"}),
            ]),

            ui.HGroup({"Spacing": 0, "Weight": 0}, [
                ui.Label({"ID": "PaceLevel",
                          "Text": "5",
                          "Weight": 0,
                          "StyleSheet": "font-size: 36px; font-weight: bold; color: #4fc3f7;",
                          "Alignment": {"AlignHCenter": True},
                          "MinimumSize": [60, 0]}),
                ui.VGroup({"Spacing": 4, "Weight": 1}, [
                    ui.Label({"ID": "PaceLabel",
                              "Text": "YouTube",
                              "Weight": 0,
                              "StyleSheet": "font-size: 16px; font-weight: bold; color: #ffffff;"}),
                    ui.Label({"ID": "PaceDesc",
                              "Text": "Standard YouTube pacing — best all-round starting point",
                              "Weight": 0,
                              "StyleSheet": "color: #aaaaaa; font-size: 11px;"}),
                ]),
            ]),
        ]),

        # Auto-adjusted parameters
        ui.VGroup({"Spacing": 6, "Weight": 0,
                   "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;"}, [
            ui.Label({"Text": "AUTO-ADJUSTED PARAMETERS", "Weight": 0,
                      "StyleSheet": "font-size: 10px; color: #888888; letter-spacing: 1px;"}),
            ui.HGroup({"Spacing": 20, "Weight": 0}, [
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": "PaceThreshText",
                              "Text": "-35 dB",
                              "Weight": 0,
                              "StyleSheet": "font-size: 20px; font-weight: bold; color: #4fc3f7;",
                              "Alignment": {"AlignHCenter": True}}),
                    ui.Label({"Text": "Threshold", "Weight": 0,
                              "Alignment": {"AlignHCenter": True},
                              "StyleSheet": "color: #888888; font-size: 10px;"}),
                ]),
                ui.VGroup({"Spacing": 2, "Weight": 1}, [
                    ui.Label({"ID": "PaceDurText",
                              "Text": "350 ms",
                              "Weight": 0,
                              "StyleSheet": "font-size: 20px; font-weight: bold; color: #ffa726;",
                              "Alignment": {"AlignHCenter": True}}),
                    ui.Label({"Text": "Min Silence", "Weight": 0,
                              "Alignment": {"AlignHCenter": True},
                              "StyleSheet": "color: #888888; font-size: 10px;"}),
                ]),
            ]),
        ]),

        # Estimates
        ui.HGroup({"Spacing": 12, "Weight": 0}, [
            ui.VGroup({"Spacing": 2, "Weight": 1,
                       "StyleSheet": "background: #1b2838; border-radius: 4px; padding: 8px;"}, [
                ui.Label({"ID": "PaceWPM",
                          "Text": "~145 WPM",
                          "Weight": 0,
                          "StyleSheet": "font-size: 18px; font-weight: bold; color: #66bb6a;",
                          "Alignment": {"AlignHCenter": True}}),
                ui.Label({"Text": "Est. Words Per Minute", "Weight": 0,
                          "Alignment": {"AlignHCenter": True},
                          "StyleSheet": "color: #888888; font-size: 10px;"}),
            ]),
            ui.VGroup({"Spacing": 2, "Weight": 1,
                       "StyleSheet": "background: #1b2838; border-radius: 4px; padding: 8px;"}, [
                ui.Label({"ID": "PaceRetention",
                          "Text": "~77%",
                          "Weight": 0,
                          "StyleSheet": "font-size: 18px; font-weight: bold; color: #ab47bc;",
                          "Alignment": {"AlignHCenter": True}}),
                ui.Label({"Text": "Est. Viewer Retention", "Weight": 0,
                          "Alignment": {"AlignHCenter": True},
                          "StyleSheet": "color: #888888; font-size: 10px;"}),
            ]),
        ]),

        ui.VGroup({"Weight": 1}, []),  # spacer

        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({
                "ID": "PaceApplyBtn",
                "Text": "Apply Pace (runs Smart Cuts with these settings)",
                "Weight": 1,
                "StyleSheet": "background: #1565c0; color: white; font-weight: bold;",
            }),
        ]),

        ui.Label({
            "ID": "PaceStatus",
            "Text": "Adjust slider, then click Apply Pace.",
            "Weight": 0,
            "StyleSheet": "color: #aaaaaa; font-size: 11px;",
        }),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect Pace Control event handlers."""
    import threading

    def _update_display(level: int) -> None:
        preset = _PACE_PRESETS.get(level, _PACE_PRESETS[5])
        win.Find("PaceLevel").SetText(str(level))
        win.Find("PaceLabel").SetText(preset["label"])
        win.Find("PaceDesc").SetText(preset["desc"])
        win.Find("PaceThreshText").SetText(f"{preset['threshold_db']} dB")
        win.Find("PaceDurText").SetText(f"{preset['min_silence_ms']} ms")
        win.Find("PaceWPM").SetText(f"~{_WPM_ESTIMATE[level]} WPM")
        win.Find("PaceRetention").SetText(f"~{_RETENTION_EST[level]}%")

    def on_slider_changed(ev: Any) -> None:
        level = win.Find("PaceSlider").Value
        _update_display(level)

    def _apply_thread() -> None:
        from src.smartcuts.cutter import apply_cuts
        from src.utils.resolve_api import get_all_video_clips

        win.Find("PaceApplyBtn").Enabled = False
        try:
            level = win.Find("PaceSlider").Value
            preset = _PACE_PRESETS.get(level, _PACE_PRESETS[5])

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                win.Find("PaceStatus").SetText("No clips found on Video Track 1.")
                return

            def progress_cb(cur: int, total: int, msg: str) -> None:
                win.Find("PaceStatus").SetText(msg)

            result = apply_cuts(
                resolve=app.resolve,
                timeline=app.timeline,
                clips=clips,
                threshold_db=float(preset["threshold_db"]),
                min_duration_ms=float(preset["min_silence_ms"]),
                padding_ms=120.0,
                progress_callback=progress_cb,
            )
            app.refresh_timeline()
            app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
            app.settings.add_stat("total_edits", 1)
            win.Find("PaceStatus").SetText(
                f"Done! Timeline '{result.new_timeline_name}' created. "
                f"{result.time_saved_sec:.1f}s removed."
            )
        except Exception as e:
            log.error("Pace apply error: %s", e)
            win.Find("PaceStatus").SetText(f"Error: {e}")
        finally:
            win.Find("PaceApplyBtn").Enabled = True

    def on_apply(ev: Any) -> None:
        if not app.connected:
            win.Find("PaceStatus").SetText("Not connected to DaVinci Resolve.")
            return
        threading.Thread(target=_apply_thread, daemon=True).start()

    win.On.PaceSlider.ValueChanged = on_slider_changed
    win.On.PaceApplyBtn.Clicked = on_apply

    # Init display for default value
    _update_display(app.settings.get("default_pace", 5))
