"""Pace control — maps a 1–10 pace level to SmartCuts parameters.

The UI delegates to SmartCuts with these derived settings.
Full implementation lives in src/ui/pace_tab.py which references this module.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PaceConfig:
    level: int
    label: str
    threshold_db: float
    min_silence_ms: float
    padding_ms: float = 120.0

    # Rough estimates used for UI display only
    estimated_wpm: int = 145
    estimated_retention_pct: int = 77


_CONFIGS: dict[int, PaceConfig] = {
    1:  PaceConfig(1,  "Very Slow",       -55.0, 1500, estimated_wpm=100, estimated_retention_pct=62),
    2:  PaceConfig(2,  "Slow",            -50.0, 1200, estimated_wpm=115, estimated_retention_pct=65),
    3:  PaceConfig(3,  "Relaxed",         -45.0, 900,  estimated_wpm=125, estimated_retention_pct=68),
    4:  PaceConfig(4,  "Moderate",        -40.0, 600,  estimated_wpm=135, estimated_retention_pct=72),
    5:  PaceConfig(5,  "YouTube",         -35.0, 350,  estimated_wpm=145, estimated_retention_pct=77),
    6:  PaceConfig(6,  "Crisp",           -33.0, 280,  estimated_wpm=155, estimated_retention_pct=80),
    7:  PaceConfig(7,  "Snappy",          -30.0, 220,  estimated_wpm=165, estimated_retention_pct=83),
    8:  PaceConfig(8,  "Fast",            -28.0, 160,  estimated_wpm=175, estimated_retention_pct=85),
    9:  PaceConfig(9,  "Very Fast",       -25.0, 120,  estimated_wpm=185, estimated_retention_pct=87),
    10: PaceConfig(10, "TikTok / Reels",  -22.0,  80,  estimated_wpm=200, estimated_retention_pct=89),
}


def get_config(level: int) -> PaceConfig:
    """Return PaceConfig for a given pace level (1–10). Clamps to valid range."""
    return _CONFIGS[max(1, min(10, level))]
