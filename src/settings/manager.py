"""JSON-backed settings persistence for Clutter — typed via Pydantic v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.constants import PATHS
from src.utils.logger import get_logger

log = get_logger(__name__)

_CONFIG_DIR = PATHS.CONFIG_DIR
_CONFIG_FILE = PATHS.CONFIG_FILE


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------

class SubtitleStylePreset(BaseModel):
    font_family: str = "Open Sans"
    font_style: str | None = None
    font_size: int = 32
    bold: bool = False
    italic: bool = False
    underline: bool = False
    primary_color: str = "#FFFFFF"
    outline_enabled: bool = False
    outline_color: str = "#000000"
    outline_width: int = 0
    shadow: int = 0
    vertical_align: int = 3
    horizontal_align: int = 3
    vertical_position: int = -90


class StatsModel(BaseModel):
    total_time_saved_sec: float = 0.0
    total_edits: int = 0
    total_zooms_applied: int = 0
    total_subtitles_generated: int = 0


_DEFAULT_STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "Open Sans Semibold": {"font_family": "Open Sans", "font_style": "Semibold", "font_size": 32, "bold": False, "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": False, "outline_color": "#000000", "outline_width": 0, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
    "YouTube":            {"font_family": "Open Sans", "font_style": None,       "font_size": 36, "bold": True,  "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": True,  "outline_color": "#000000", "outline_width": 3, "shadow": 1, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
    "TikTok Bold":        {"font_family": "Open Sans", "font_style": None,       "font_size": 48, "bold": True,  "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": True,  "outline_color": "#000000", "outline_width": 4, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
    "Minimal":            {"font_family": "Open Sans", "font_style": None,       "font_size": 28, "bold": False, "italic": False, "underline": False, "primary_color": "#FFFFFF", "outline_enabled": False, "outline_color": "#000000", "outline_width": 1, "shadow": 0, "vertical_align": 3, "horizontal_align": 3, "vertical_position": -90},
}


# ---------------------------------------------------------------------------
# Root settings model
# ---------------------------------------------------------------------------

class ClutterSettings(BaseModel):
    # API keys
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    minimax_api_key: str = ""
    nvidia_api_key: str = ""
    anthropic_api_key: str = ""
    pixabay_api_key: str = ""
    pexels_api_key: str = ""

    # Smart Cuts
    default_silence_threshold_db: float = -35.0
    default_min_silence_ms: int = 350
    default_padding_ms: int = 120
    smartcuts_silence_method: str = "RMS"
    smartcuts_retake_method: str = "None"

    # Pace
    default_pace: int = 5

    # Zooms
    default_zoom_amount: float = 1.15
    default_zoom_mode: str = "Standard"
    default_max_zooms_per_minute: int = 4

    # Subtitles
    subtitle_language: str = "en"
    subtitle_preset: str = "YouTube"
    stt_provider: str = "ElevenLabs"
    whisper_model: str = "base"
    active_subtitle_style: str = "Open Sans Semibold"
    subtitle_style_presets: dict[str, SubtitleStylePreset] = Field(
        default_factory=lambda: {
            name: SubtitleStylePreset(**data)
            for name, data in _DEFAULT_STYLE_PRESETS.items()
        }
    )

    # B-Roll
    last_broll_folder: str = ""
    broll_provider: str = "Both"
    broll_top_n: int = 10
    broll_use_mock: bool = False
    broll_mode: str = "Manual"
    broll_auto_use_local: bool = True
    broll_auto_use_online: bool = True
    broll_auto_cloud_rerank: bool = False
    broll_auto_clips_per_segment: int = 1
    broll_auto_max_clips: int = 10
    broll_auto_provider: str = "Both"
    broll_auto_dl_folder: str = ""
    broll_llm_mode: str = "Off"  # "Off" or a provider name (OpenAI/Gemini/Minimax/NVIDIA)
    broll_keyword_method: str = "YAKE"
    # Natural placement
    broll_natural_placement: bool = True
    broll_no_start_broll: bool = True
    broll_intro_skip_sec: float = 4.0
    broll_min_gap_sec: float = 5.0
    broll_max_broll_duration: float = 5.0
    # Fill frame
    broll_auto_fill_frame: bool = False

    # Music & SFX
    music_llm_provider: str = ""  # explicit Mood-Engine LLM provider, "" = auto

    # LLM model config
    llm_openai_model: str = "gpt-4o-mini"
    llm_gemini_model: str = "gemini-2.0-flash"
    llm_minimax_model: str = "MiniMax-Text-01"
    llm_nvidia_model: str = ""  # free-text NVIDIA model id (e.g. moonshotai/kimi-k2.6)
    llm_anthropic_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.1

    # Stats
    stats: StatsModel = Field(default_factory=StatsModel)

    @field_validator("subtitle_style_presets", mode="before")
    @classmethod
    def _coerce_style_presets(cls, v: Any) -> Any:
        if isinstance(v, dict):
            merged: dict[str, Any] = {}
            for name, data in _DEFAULT_STYLE_PRESETS.items():
                merged[name] = data
            for name, data in v.items():
                if isinstance(data, dict):
                    merged[name] = data
                elif isinstance(data, SubtitleStylePreset):
                    merged[name] = data.model_dump()
            return merged
        return v

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class SettingsManager:
    """Load and persist plugin settings as JSON, backed by ClutterSettings."""

    def __init__(self, path: Path = _CONFIG_FILE) -> None:
        self._path = path
        self._model: ClutterSettings = ClutterSettings()
        self.load()

    # ------------------------------------------------------------------
    # Public interface (unchanged shape — all callers work without edits)
    # ------------------------------------------------------------------

    def load(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    raw: dict[str, Any] = json.load(f)
                self._model = ClutterSettings.model_validate(raw)
                log.debug("Settings loaded from %s", self._path)
            except Exception as e:
                log.error("Failed to load settings (%s) — using defaults", e)
                self._model = ClutterSettings()
        else:
            self._model = ClutterSettings()
            self.save()

    def save(self) -> None:
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._model.model_dump(), f, indent=2)
        except Exception as e:
            log.error("Failed to save settings: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self._model.model_dump().get(key, default)

    def set(self, key: str, value: Any) -> None:
        # model_dump → merge → re-validate keeps validation intact
        data = self._model.model_dump()
        data[key] = value
        self._model = ClutterSettings.model_validate(data)
        self.save()

    def add_stat(self, stat_key: str, amount: float = 1.0) -> None:
        current = getattr(self._model.stats, stat_key, 0)
        setattr(self._model.stats, stat_key, current + amount)
        self.save()

    @property
    def stats(self) -> dict[str, Any]:
        return self._model.stats.model_dump()

    def get_style_presets(self) -> dict[str, Any]:
        return {
            name: (preset.model_dump() if isinstance(preset, SubtitleStylePreset) else preset)
            for name, preset in self._model.subtitle_style_presets.items()
        }

    @property
    def api_key(self) -> str:
        return self._model.elevenlabs_api_key

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.set("elevenlabs_api_key", value)
