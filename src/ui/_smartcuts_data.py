"""Constants for the Smart Cuts tab."""

from __future__ import annotations

PACE_PRESETS: dict[int, dict] = {
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
