"""Main window — assembles all tabs using DaVinci Resolve's UIManager."""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger
from src.ui import (
    dashboard_tab,
    smartcuts_tab,
    pace_tab,
    subtitles_tab,
    zooms_tab,
    broll_tab,
    graphics_tab,
)

log = get_logger(__name__)

_WIN_W = 900
_WIN_H = 680
_TABS = [
    "Dashboard",
    "Smart Cuts",
    "Pace Control",
    "Subtitles",
    "Auto Zooms",
    "B-Roll",
    "Motion Graphics",
]

# Builders indexed by tab position
_TAB_BUILDERS = [
    dashboard_tab.build,
    smartcuts_tab.build,
    pace_tab.build,
    subtitles_tab.build,
    zooms_tab.build,
    broll_tab.build,
    graphics_tab.build,
]

_TAB_SETUP = [
    dashboard_tab.setup,
    smartcuts_tab.setup,
    pace_tab.setup,
    subtitles_tab.setup,
    zooms_tab.setup,
    broll_tab.setup,
    graphics_tab.setup,
]


class MainWindow:
    """DaVinci Resolve UIManager-based main window."""

    def __init__(self, app: Any, fusion: Any, bmd_module: Any) -> None:
        self._app = app
        self._fusion = fusion
        self._bmd = bmd_module
        self._ui = fusion.UIManager
        self._disp = bmd_module.UIDispatcher(self._ui)
        self._win: Any = None

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_window(self) -> Any:
        ui = self._ui

        # Build each tab's content page
        tab_pages = [builder(ui) for builder in _TAB_BUILDERS]

        win = self._disp.AddWindow(
            {
                "WindowTitle": "Clutter",
                "ID": "ClutterWin",
                "Geometry": [80, 80, _WIN_W, _WIN_H],
            },
            [
                ui.VGroup({"Spacing": 0, "Weight": 1}, [

                    # ── Top bar ──
                    ui.HGroup({
                        "Spacing": 8,
                        "Weight": 0,
                        "StyleSheet": "background: #1a1a1a; padding: 6px 10px;",
                    }, [
                        ui.Label({
                            "Text": "Clutter",
                            "Weight": 0,
                            "StyleSheet": "font-weight: bold; font-size: 13px; color: #4fc3f7;",
                        }),
                        ui.Label({
                            "ID": "ConnStatusLabel",
                            "Text": self._app.status_text(),
                            "Weight": 1,
                            "StyleSheet": "color: #aaaaaa; font-size: 11px;",
                        }),
                    ]),

                    # ── Tab bar ──
                    ui.TabBar({
                        "ID": "MainTabBar",
                        "Weight": 0,
                    }),

                    # ── Content stack ──
                    ui.Stack(
                        {"ID": "MainStack", "Weight": 1},
                        tab_pages,
                    ),

                    # ── Bottom padding ──
                    ui.HGroup({"Weight": 0, "MinimumSize": [1, 4]}, []),
                ]),
            ],
        )
        return win

    # ------------------------------------------------------------------
    # Setup events
    # ------------------------------------------------------------------

    def _setup_events(self) -> None:
        win = self._win
        disp = self._disp
        app = self._app

        # Add tabs to the TabBar
        tab_bar = win.Find("MainTabBar")
        for name in _TABS:
            tab_bar.AddTab(name)

        # Tab switching
        def on_tab_changed(ev: Any) -> None:
            idx = ev.get("Index", 0)
            win.Find("MainStack").CurrentIndex = idx
            log.debug("Switched to tab %d (%s)", idx, _TABS[idx] if idx < len(_TABS) else "?")

        win.On.MainTabBar.CurrentChanged = on_tab_changed

        # Window close
        def on_close(ev: Any) -> None:
            log.info("Window closed by user")
            disp.ExitLoop()

        win.On.ClutterWin.Close = on_close

        # Let each tab wire up its own events
        for setup_fn in _TAB_SETUP:
            try:
                setup_fn(win, app, disp)
            except Exception as e:
                log.error("Tab setup error (%s): %s", setup_fn.__module__, e)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build window, show it, and run the event loop."""
        try:
            self._win = self._build_window()
            self._setup_events()
            self._win.Show()
            log.info("Window open — entering event loop")
            self._disp.RunLoop()
            self._win.Hide()
        except Exception as e:
            log.error("MainWindow.run() error: %s", e)
            raise
