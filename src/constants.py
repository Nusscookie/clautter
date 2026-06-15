"""Centralized constants for Clautter — single source of truth for values
that are otherwise duplicated across many modules.

Change a value here and it updates everywhere. Scope is deliberately limited
to things that are *not* user-configurable: brand colors, on-disk paths,
Resolve track names, and the string keys used to read settings. Tunable
defaults (silence threshold, zoom amount, timeouts, …) live in
``src.settings.manager.ClautterSettings`` so there is exactly one source of
truth for each of those, too.

Conventions:
    from src.constants import COLORS, PATHS, TRACKS, SETTINGS_KEYS
    label.configure(text_color=COLORS.TEXT)
    settings.get(SETTINGS_KEYS.BROLL_MIN_GAP)
"""

from __future__ import annotations

from pathlib import Path

APP_VERSION = "v0.1.1"


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

    # ── Source-tag colors (B-Roll results window — data, two distinct hues) ──
    SRC_PIXABAY = "#A85A3E"     # = BRAND_DIM
    SRC_PEXELS = "#E8903A"      # = WARNING


class PATHS:
    """On-disk locations under the user's ``~/.clautter`` config dir."""

    CONFIG_DIR = Path.home() / ".clautter"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    BRIDGE_FILE = CONFIG_DIR / "bridge.json"
    LOGS_DIR = CONFIG_DIR / "logs"
    BROLL_CACHE = CONFIG_DIR / "broll_cache"
    BROLL_EMBED_CACHE = CONFIG_DIR / "broll_embed_cache"
    AUDIO_CACHE = CONFIG_DIR / "audio_cache"
    GRAPHICS_CACHE = CONFIG_DIR / "graphics"


class TRACKS:
    """Resolve timeline track names Clautter creates / writes to."""

    MUSIC = "Music"
    SFX = "SFX"
    BROLL = "B-Roll"


class SETTINGS_KEYS:
    """String keys passed to ``app.settings.get(...)`` / ``.set(...)``.

    Must match field names on ``ClautterSettings`` in
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

    # SFX
    SFX_SOURCE = "sfx_source"
    SFX_MOOD_MODE = "sfx_mood_mode"
    SFX_LLM_PROVIDER = "sfx_llm_provider"
