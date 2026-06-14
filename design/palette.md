# Clutter Color Palette

## Brand Story

The single accent is **terracotta** (`#D97757`), derived from the app icon. Dark
neutral backgrounds let the video content breathe; the warm terracotta accent directs
attention to interactive controls and live data values. Status colors (success green,
error red, warning amber) are the **only** non-brand hues — they read clearly regardless
of context.

> **Terracotta-only.** There is one accent family. Earlier builds carried competing
> accents (cyan, blue/indigo buttons, feature-green, feature-purple). Those are gone —
> every primary action, slider readout, progress fill, and stat value is now terracotta.
> The only other colors are the three status hues and the two B-Roll source-data tags.

---

## Palette

### Brand / Accent (terracotta — the only accent family)

| Token | Hex | Usage |
|---|---|---|
| `BRAND_PRIMARY` | `#D97757` | Accent labels, stat card values, slider value readouts, progress bars, "Clutter" title, segmented-button selected state, settings nav highlight |
| `BRAND_HOVER` | `#E08A6A` | Hover for brand-colored elements (e.g. segmented-button selected hover) |
| `BRAND_DIM` | `#A85A3E` | Muted accent — online B-Roll source tag (vs `BRAND_PRIMARY` for local) |
| `BTN_PRIMARY_BG` | `#B85F3A` | Primary CTA button bg: Generate Transcript, Apply Cuts, Apply Zooms, Apply Pace, Add Music, Run B-Roll, Place |
| `BTN_PRIMARY_HOVER` | `#C96A45` | Hover for primary CTA buttons |

### Status (the only non-brand hues)

| Token | Hex | Usage |
|---|---|---|
| `SUCCESS` | `#66bb6a` | Success / "Done" / import states, connected status dot |
| `ERROR` | `#ff6b6b` | Error / failed / disconnected status dot |
| `WARNING` | `#E8903A` | Non-blocking notices, fallbacks, BETA banner text |
| `WARN_PARTIAL` | `#ffa726` | Partial success ("placed 3/5") — amber, not red |

### Backgrounds

| Token | Hex | Usage |
|---|---|---|
| `BG_DARKEST` | `#141414` | Root + modal window bg |
| `BG_CONSOLE` | `#0d0d0d` | Console window text area |
| `BG_DARK` | `#1a1a1a` | Top bar |
| `BG_MID` | `#1e1e1e` | Tabview fg, card headers, footers, option menus |
| `BG_CARD` | `#2a2a2a` | Card bodies, **secondary/neutral buttons** (Analyze, Preview, Export), status pill bg |
| `BG_HOVER` | `#3a3a3a` | Hover for secondary buttons |
| `BG_WARM_BANNER` | `#1A0E00` | BETA banner, Graphics notice, future-feature card |

### Text

| Token | Hex | Usage |
|---|---|---|
| `TEXT_PRIMARY` | `#ffffff` | Bold headings, key values |
| `TEXT_SECONDARY` | `#cccccc` | Body text, radio/checkbox labels, connected status text |
| `TEXT_MUTED` | `#aaaaaa` | Standard labels, card section headers, slider labels |
| `TEXT_DIM` | `#888888` | Sub-labels, unit labels, section chips, **disabled-button text** |
| `TEXT_SUBTLE` | `#555555` | Hint text, fine print |

### Dividers

| Token | Hex | Usage |
|---|---|---|
| `SEPARATOR` | `#444444` | Horizontal rule dividers between sections |
| `SEPARATOR_DARK` | `#333333` | Lighter dividers inside cards; top-bar pip |

### Data tags (not theme accents)

| Token | Hex | Note |
|---|---|---|
| `SRC_PIXABAY` | `#A85A3E` | B-Roll results source tag (= `BRAND_DIM`) |
| `SRC_PEXELS` | `#E8903A` | B-Roll results source tag (= `WARNING`) — two distinct hues so providers are distinguishable |

> Subtitle render colors (`#FFFFFF`/`#000000`/`#FFFF00`/`#FF0000`) are **data** that flows
> into ASS/Fusion output — they live in `src/subtitles/*` and the subtitle style preview,
> not here. Do not theme them.

---

## CTk theme — widget-level source of truth

`assets/clutter_theme.json` is a custom customtkinter theme loaded at startup
(`src/ui/main_window.py:_apply_theme`, with a `"blue"` fallback if the file is missing).
It makes **every built-in widget default to terracotta** — sliders, segmented buttons,
checkmarks, radio buttons, progress bars, option menus, scrollbars, entry focus borders.

Each value in the JSON is `[light, dark]`; the app forces dark mode, so the **second**
element renders. The dark slots mirror `COLORS`:

| CTk widget key | maps to |
|---|---|
| `CTkButton.fg_color` / `hover_color` | `BTN_PRIMARY_BG` / `BTN_PRIMARY_HOVER` |
| `CTkSlider.button_color` / `progress_color` | `BRAND_PRIMARY` |
| `CTkSegmentedButton.selected_color` | `BTN_PRIMARY_BG` |
| `CTkCheckBox` / `CTkRadioButton.fg_color` | `BTN_PRIMARY_BG` |
| `CTkProgressBar.progress_color` | `BRAND_PRIMARY` |
| `CTk*.text_color_disabled` (dark) | `TEXT_DIM` (`#888888`) — legible disabled state |

Because the theme already paints buttons terracotta, **neutral buttons must opt out**
explicitly with `fg_color=BG_CARD, hover_color=BG_HOVER`. Keep the theme JSON and
`COLORS` in sync — if you change a brand hex in `constants.py`, update the matching dark
slot here.

---

## Do's

- Use `BRAND_PRIMARY` for **any value the user is actively changing** (slider readouts,
  stat numbers, progress fill).
- Use `BTN_PRIMARY_BG` for the **one primary CTA per action row**. In a row of buttons
  (e.g. Analyze · Preview · Apply), only the final/primary action is terracotta; the
  others opt out to `BG_CARD`. Never two terracotta CTAs side-by-side.
- Use `WARNING` for **non-blocking notices**; reserve `ERROR` for failures.
- Keep `SUCCESS` for completion/import and the connected status dot.

## Don'ts

- **Don't introduce a new accent hue.** Terracotta is the only accent family; status
  green/red/amber are the only other colors. Adding a fourth (cyan, blue, purple…)
  re-creates the dilution this palette was cleaned up to remove.
- Don't use `BRAND_PRIMARY` for body text or long labels — high-contrast, causes fatigue.
- Don't paint two primary buttons in the same row terracotta — neutralize the secondary
  ones with `BG_CARD`.
- Don't change `BG_DARKEST` / `BG_DARK` — Resolve's own UI is dark; these neutrals blend
  with the host environment.
