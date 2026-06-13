"""Centralized constants for Clutter — single source of truth for values
that are otherwise duplicated across many modules.

Change a value here and it updates everywhere. Scope is deliberately limited
to things that are *not* user-configurable: brand colors, on-disk paths,
Resolve track names, and the string keys used to read settings. Tunable
defaults (silence threshold, zoom amount, timeouts, …) live in
``src.settings.manager.ClutterSettings`` so there is exactly one source of
truth for each of those, too.

Conventions:
    from src.constants import COLORS, PATHS, TRACKS, SETTINGS_KEYS
    label.configure(text_color=COLORS.TEXT)
    settings.get(SETTINGS_KEYS.BROLL_MIN_GAP)
"""

from __future__ import annotations

from pathlib import Path


class COLORS:
    """Brand + UI palette. Mirrors ``design/palette.md`` — keep in sync.

    Token names match the palette doc so a designer can map them 1:1.
    """

    # ── Brand / accent ──
    BRAND_PRIMARY = "#D97757"   # accent labels, slider readouts, progress, title
    BRAND_HOVER = "#E08A6A"     # hover for brand-colored elements
    BRAND_DIM = "#A85A3E"       # muted accent / Pixabay source tag
    BTN_PRIMARY_BG = "#B85F3A"  # primary CTA button bg
    BTN_PRIMARY_HOVER = "#C96A45"

    # ── Status ──
    SUCCESS = "#66bb6a"         # success / done / import
    ERROR = "#ff6b6b"           # error / disconnected / failed
    WARNING = "#E8903A"         # non-blocking notices, BETA, Pexels source tag
    WARN_PARTIAL = "#ffa726"    # partial success (e.g. "placed 3/5") — amber, not red

    # ── Backgrounds ──
    BG_DARKEST = "#141414"      # root + modal window bg
    BG_CONSOLE = "#0d0d0d"      # console window text area (darker than darkest)
    BG_DARK = "#1a1a1a"         # top bar
    BG_MID = "#1e1e1e"          # tabview fg, card headers, footers, option menus
    BG_CARD = "#2a2a2a"         # card bodies, secondary buttons
    BG_HOVER = "#3a3a3a"        # hover for secondary buttons
    BG_WARM_BANNER = "#1A0E00"  # BETA banner, graphics notice, future-feature card

    # ── Text ──
    TEXT_PRIMARY = "#ffffff"    # bold headings, key values
    TEXT_SECONDARY = "#cccccc"  # body text, radio/checkbox labels
    TEXT_MUTED = "#aaaaaa"      # standard labels, section headers, slider labels
    TEXT_DIM = "#888888"        # sub-labels, unit labels, section title chips
    TEXT_SUBTLE = "#555555"     # hint text, fine print, disabled labels

    # ── Dividers ──
    SEPARATOR = "#444444"       # section dividers
    SEPARATOR_DARK = "#333333"  # lighter dividers inside cards; top-bar pip

    # ── Special-purpose (semantic, not brand) ──
    GREEN_ACTION_BG = "#1b5e20"   # B-Roll Run/Search buttons
    GREEN_ACTION_HOVER = "#2e7d32"
    PURPLE_ZOOM_BG = "#6a1b9a"    # Auto Zooms "Apply Zooms" button
    PURPLE_ZOOM_HOVER = "#7b1fa2"
    PURPLE_STAT = "#ab47bc"       # "Zoom Points Found" stat value

    # ── Source-tag colors (B-Roll results window) ──
    SRC_PIXABAY = "#A85A3E"     # = BRAND_DIM
    SRC_PEXELS = "#E8903A"      # = WARNING

    # ── Legacy / feature-specific accents (pre-rebrand cyan + info-card blues) ──
    LEGACY_CYAN = "#4fc3f7"     # old accent, retained where intentionally cyan
    INFO_CARD_BG = "#1b2838"    # pace info-card bg
    BLUE_BTN_BG = "#0d47a1"     # music info/action blue
    BLUE_BTN_HOVER = "#1565c0"
    INDIGO_BTN_BG = "#1a237e"   # music secondary blue
    INDIGO_BTN_HOVER = "#283593"


class PATHS:
    """On-disk locations under the user's ``~/.clutter`` config dir."""

    CONFIG_DIR = Path.home() / ".clutter"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    BRIDGE_FILE = CONFIG_DIR / "bridge.json"
    LOGS_DIR = CONFIG_DIR / "logs"
    BROLL_CACHE = CONFIG_DIR / "broll_cache"
    BROLL_EMBED_CACHE = CONFIG_DIR / "broll_embed_cache"
    AUDIO_CACHE = CONFIG_DIR / "audio_cache"


class TRACKS:
    """Resolve timeline track names Clutter creates / writes to."""

    MUSIC = "Music"
    SFX = "SFX"
    BROLL = "B-Roll"


class SETTINGS_KEYS:
    """String keys passed to ``app.settings.get(...)`` / ``.set(...)``.

    Must match field names on ``ClutterSettings`` in
    ``src.settings.manager``. Use these instead of inline string literals so a
    rename is a one-place change and typos surface at import-reference time.
    """

    # B-Roll natural placement
    BROLL_NATURAL_PLACEMENT = "broll_natural_placement"
    BROLL_NO_START = "broll_no_start_broll"
    BROLL_INTRO_SKIP = "broll_intro_skip_sec"
    BROLL_MIN_GAP = "broll_min_gap_sec"
    BROLL_MAX_DUR = "broll_max_broll_duration"
    BROLL_FILL_FRAME = "broll_auto_fill_frame"

    # LLM
    LLM_MAX_TOKENS = "llm_max_tokens"
    LLM_TEMPERATURE = "llm_temperature"
