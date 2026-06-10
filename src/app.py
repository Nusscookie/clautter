"""Central application coordinator for Clutter."""

from __future__ import annotations
from typing import Any, Callable, Optional

from src.settings.manager import SettingsManager
from src.utils.logger import get_logger

log = get_logger(__name__)


class ClutterApp:
    """Wires all modules together and holds shared state."""

    def __init__(self) -> None:
        self.settings = SettingsManager()

        # DaVinci Resolve objects (set after connect())
        self.resolve: Optional[Any] = None
        self.project_manager: Optional[Any] = None
        self.project: Optional[Any] = None
        self.media_pool: Optional[Any] = None
        self.timeline: Optional[Any] = None
        self.fps: float = 25.0

        self._connected = False

        # Settings-change listeners — tabs register refresh callbacks so UI can
        # update live when Settings → Apply is pressed (no app restart needed).
        self._settings_listeners: list[Callable[[], None]] = []

        # Shared transcript — populated by Subtitles tab, consumed by Zooms + B-Roll
        self.transcript: list[dict] = []  # list of {word, start_sec, end_sec}

        # Shared analysis results — written by feature workers, read by Music & SFX tab
        self.smartcuts_segments: list = []   # list[SegmentRecord] — set after SmartCuts apply
        self.zoom_points: list = []          # list[ZoomPoint] — set after Auto Zooms analyze
        self.broll_placer_results: list = [] # list[PlacerResult] — set after B-Roll autonomous run

    # ------------------------------------------------------------------
    # Settings-change notification
    # ------------------------------------------------------------------

    def on_settings_changed(self, cb: Callable[[], None]) -> None:
        """Register a callback fired after Settings → Apply.

        Callbacks run on the Tk main thread (Apply is a main-thread handler),
        so they may touch widgets directly.
        """
        self._settings_listeners.append(cb)

    def notify_settings_changed(self) -> None:
        """Notify all registered listeners that settings changed."""
        for cb in list(self._settings_listeners):
            try:
                cb()
            except Exception as e:
                log.error("settings listener failed: %s", e)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, resolve_obj=None) -> bool:
        """Connect to a running DaVinci Resolve instance.

        Returns True on success, False on failure.
        """
        from src.utils.resolve_api import connect, get_fps

        try:
            (
                self.resolve,
                self.project_manager,
                self.project,
                self.media_pool,
                self.timeline,
            ) = connect(resolve_obj=resolve_obj)
            self.fps = get_fps(self.project)
            self._connected = True
            log.info("App connected | FPS: %.2f", self.fps)
            return True
        except Exception as e:
            log.error("Connection failed: %s", e)
            self._connected = False
            return False

    def reconnect(self) -> bool:
        """Re-attempt connection (useful after initial failure)."""
        self._connected = False
        return self.connect()

    def refresh_timeline(self) -> bool:
        """Refresh timeline reference — call after switching or creating timelines."""
        if not self._connected or self.project is None:
            return False
        try:
            self.timeline = self.project.GetCurrentTimeline()
            if self.timeline:
                log.debug("Timeline refreshed: %s", self.timeline.GetName())
            return self.timeline is not None
        except Exception as e:
            log.error("refresh_timeline error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def status_text(self) -> str:
        """Human-readable connection / project status for UI display."""
        if not self._connected:
            return "Not connected to DaVinci Resolve"
        try:
            proj = self.project.GetName() if self.project else "?"
            tl = self.timeline.GetName() if self.timeline else "No timeline"
            return f"Connected  |  Project: {proj}  |  Timeline: {tl}"
        except Exception:
            return "Connected (could not read project info)"

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_video_clips(self, track: int = 1) -> list[Any]:
        """Return all clips from the specified video track."""
        from src.utils.resolve_api import get_all_video_clips

        if not self._connected or self.timeline is None:
            return []
        return get_all_video_clips(self.timeline, track)
