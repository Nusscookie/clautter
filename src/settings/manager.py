"""JSON-backed settings persistence for Clutter."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_CONFIG_DIR = Path.home() / ".clutter"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS: dict[str, Any] = {
    "elevenlabs_api_key": "",
    "default_silence_threshold_db": -35,
    "default_min_silence_ms": 350,
    "default_padding_ms": 120,
    "default_zoom_amount": 1.15,
    "default_zoom_mode": "Standard",
    "default_max_zooms_per_minute": 4,
    "default_pace": 5,
    "subtitle_language": "en",
    "subtitle_preset": "YouTube",
    "last_broll_folder": "",
    "pixabay_api_key": "",
    "pexels_api_key": "",
    "broll_provider": "Both",
    "broll_top_n": 10,
    "broll_use_mock": False,
    "broll_mode": "Manual",
    "broll_auto_use_local": True,
    "broll_auto_use_online": True,
    "broll_auto_cloud_rerank": False,
    "broll_auto_clips_per_segment": 1,
    "broll_auto_max_clips": 10,
    "broll_auto_provider": "Both",
    "broll_auto_dl_folder": "",
    "openai_api_key": "",
    "gemini_api_key": "",
    "minimax_api_key": "",
    "active_subtitle_style": "Open Sans Semibold",
    "subtitle_style_presets": {
        "Open Sans Semibold": {"font_family": "Open Sans", "font_style": "Semibold", "font_size": 32, "bold": False, "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": False, "outline_color": "#000000", "outline_width": 0, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
        "YouTube":            {"font_family": "Open Sans", "font_style": None,       "font_size": 36, "bold": True,  "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": True,  "outline_color": "#000000", "outline_width": 3, "shadow": 1, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
        "TikTok Bold":        {"font_family": "Open Sans", "font_style": None,       "font_size": 48, "bold": True,  "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": True,  "outline_color": "#000000", "outline_width": 4, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
        "Minimal":            {"font_family": "Open Sans", "font_style": None,       "font_size": 28, "bold": False, "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": False, "outline_color": "#000000", "outline_width": 1, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
    },
    "stats": {
        "total_time_saved_sec": 0.0,
        "total_edits": 0,
        "total_zooms_applied": 0,
        "total_subtitles_generated": 0,
    },
}


class SettingsManager:
    """Load and persist plugin settings as JSON."""

    def __init__(self, path: Path = _CONFIG_FILE) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load settings from disk, filling in defaults for missing keys."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded: dict[str, Any] = json.load(f)
                self._data = {**_DEFAULTS, **loaded}
                # Deep merge nested dicts so built-in entries survive config updates
                self._data["stats"] = {**_DEFAULTS["stats"], **loaded.get("stats", {})}
                self._data["subtitle_style_presets"] = {
                    **_DEFAULTS["subtitle_style_presets"],
                    **loaded.get("subtitle_style_presets", {}),
                }
                log.debug("Settings loaded from %s", self._path)
            except Exception as e:
                log.error("Failed to load settings (%s) — using defaults", e)
                self._data = dict(_DEFAULTS)
        else:
            self._data = dict(_DEFAULTS)
            self.save()  # create file with defaults

    def save(self) -> None:
        """Persist current settings to disk."""
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            log.error("Failed to save settings: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def add_stat(self, stat_key: str, amount: float = 1.0) -> None:
        """Increment a stats counter and persist."""
        stats = self._data.setdefault("stats", {})
        stats[stat_key] = stats.get(stat_key, 0) + amount
        self.save()

    @property
    def stats(self) -> dict[str, Any]:
        return self._data.get("stats", {})

    def get_style_presets(self) -> dict[str, Any]:
        """Return a shallow copy of all subtitle style presets."""
        return dict(self._data.get("subtitle_style_presets", {}))

    @property
    def api_key(self) -> str:
        return self._data.get("elevenlabs_api_key", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.set("elevenlabs_api_key", value)
