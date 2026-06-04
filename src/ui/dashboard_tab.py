"""Dashboard tab — session stats and connection status."""

from __future__ import annotations
from typing import Any


def build(ui: Any) -> Any:
    """Return the Dashboard tab VGroup layout."""
    return ui.VGroup({"Spacing": 12, "Weight": 1}, [

        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.Label({
                "Text": "AI EDITOR ASSISTANT",
                "Weight": 0,
                "Alignment": {"AlignHCenter": True},
                "StyleSheet": "font-size: 18px; font-weight: bold; color: #ffffff;",
            }),
            ui.Label({
                "Text": "DaVinci Resolve Plugin  •  v1.0.0",
                "Weight": 0,
                "Alignment": {"AlignHCenter": True},
                "StyleSheet": "color: #888888; font-size: 11px;",
            }),
        ]),

        ui.Label({
            "Text": "",
            "Weight": 0,
            "MinimumSize": [1, 1],
            "MaximumSize": [9999, 1],
            "StyleSheet": "background: #444444;",
        }),

        # Stats grid
        ui.VGroup({"Spacing": 6, "Weight": 0}, [
            ui.Label({
                "Text": "SESSION STATS",
                "Weight": 0,
                "StyleSheet": "font-size: 11px; font-weight: bold; color: #aaaaaa; "
                              "letter-spacing: 1px;",
            }),

            ui.HGroup({"Spacing": 12, "Weight": 0}, [
                _stat_card(ui, "DashTimeSaved", "Time Saved", "0.0 s"),
                _stat_card(ui, "DashTotalEdits", "Total Edits", "0"),
            ]),

            ui.HGroup({"Spacing": 12, "Weight": 0}, [
                _stat_card(ui, "DashZooms", "Zooms Applied", "0"),
                _stat_card(ui, "DashSubs", "Subtitles Generated", "0"),
            ]),
        ]),

        ui.Label({
            "Text": "",
            "Weight": 0,
            "MinimumSize": [1, 1],
            "MaximumSize": [9999, 1],
            "StyleSheet": "background: #444444;",
        }),

        # Quick tips
        ui.VGroup({"Spacing": 4, "Weight": 0}, [
            ui.Label({
                "Text": "QUICK START",
                "Weight": 0,
                "StyleSheet": "font-size: 11px; font-weight: bold; color: #aaaaaa; "
                              "letter-spacing: 1px;",
            }),
            ui.Label({
                "Text": "1. Smart Cuts  —  Select clips on timeline, then Analyze + Apply Cuts",
                "Weight": 0,
                "StyleSheet": "color: #cccccc;",
            }),
            ui.Label({
                "Text": "2. Subtitles  —  Enter ElevenLabs API key, then Generate Transcript",
                "Weight": 0,
                "StyleSheet": "color: #cccccc;",
            }),
            ui.Label({
                "Text": "3. Auto Zooms  —  After generating transcript, Analyze + Apply Zooms",
                "Weight": 0,
                "StyleSheet": "color: #cccccc;",
            }),
        ]),

        ui.VGroup({"Weight": 1}, []),  # spacer

        ui.HGroup({"Spacing": 8, "Weight": 0}, [
            ui.Button({
                "ID": "DashRefreshBtn",
                "Text": "Refresh Stats",
                "Weight": 1,
            }),
            ui.Button({
                "ID": "DashReconnectBtn",
                "Text": "Reconnect to Resolve",
                "Weight": 1,
            }),
        ]),
    ])


def _stat_card(ui: Any, value_id: str, label: str, default: str) -> Any:
    return ui.VGroup({
        "Spacing": 2,
        "Weight": 1,
        "StyleSheet": "background: #2a2a2a; border-radius: 4px; padding: 8px;",
    }, [
        ui.Label({
            "ID": value_id,
            "Text": default,
            "Weight": 0,
            "Alignment": {"AlignHCenter": True},
            "StyleSheet": "font-size: 22px; font-weight: bold; color: #4fc3f7;",
        }),
        ui.Label({
            "Text": label,
            "Weight": 0,
            "Alignment": {"AlignHCenter": True},
            "StyleSheet": "font-size: 10px; color: #888888;",
        }),
    ])


def setup(win: Any, app: Any, disp: Any) -> None:
    """Connect dashboard event handlers."""

    def _refresh_stats() -> None:
        stats = app.settings.stats
        time_s = stats.get("total_time_saved_sec", 0.0)
        win.Find("DashTimeSaved").SetText(f"{time_s:.1f} s")
        win.Find("DashTotalEdits").SetText(str(int(stats.get("total_edits", 0))))
        win.Find("DashZooms").SetText(str(int(stats.get("total_zooms_applied", 0))))
        win.Find("DashSubs").SetText(str(int(stats.get("total_subtitles_generated", 0))))

    def on_refresh(ev: Any) -> None:
        _refresh_stats()

    def on_reconnect(ev: Any) -> None:
        win.Find("DashReconnectBtn").Enabled = False
        ok = app.reconnect()
        status = app.status_text()
        win.Find("ConnStatusLabel").SetText(status)
        win.Find("DashReconnectBtn").Enabled = True

    win.On.DashRefreshBtn.Clicked = on_refresh
    win.On.DashReconnectBtn.Clicked = on_reconnect

    # Populate stats on first show
    _refresh_stats()
