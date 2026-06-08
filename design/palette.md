# Clutter Color Palette

## Brand Story

The primary accent is derived from the app icon — an orange-terracotta crab. The dark neutral backgrounds let the video content breathe; the warm orange accent directs attention to interactive controls and live data values. Status colors (success green, error red) remain semantically neutral so they read clearly regardless of context.

---

## Palette

### Brand / Accent

| Token | Hex | Usage |
|---|---|---|
| `brand_primary` | `#D97757` | Accent labels, stat card values, slider value readouts, progress bars, "Clutter" title, header text in result windows |
| `brand_hover` | `#E08A6A` | Hover state for brand-colored elements (future use) |
| `brand_dim` | `#A85A3E` | Secondary / muted accent — Pixabay source tag |
| `btn_primary_bg` | `#B85F3A` | Primary CTA buttons: Generate Transcript, Apply Cuts, Apply Pace, Continue |
| `btn_primary_hover` | `#C96A45` | Hover for primary CTA buttons |

### Status

| Token | Hex | Usage |
|---|---|---|
| `success` | `#66bb6a` | Success messages, "Done" states, green action buttons (B-Roll Run/Search) |
| `error` | `#ff6b6b` | Error messages, disconnected/failed states |
| `warning` | `#E8903A` | Warning notices, fallback messages, BETA banner text, Pexels source tag |

### Backgrounds

| Token | Hex | Usage |
|---|---|---|
| `bg_darkest` | `#141414` | Root window bg, modal window bg (settings, B-roll results) |
| `bg_dark` | `#1a1a1a` | Top bar |
| `bg_mid` | `#1e1e1e` | Tabview fg, card header bars, footer bars, option menus |
| `bg_card` | `#2a2a2a` | Card bodies, secondary/neutral buttons |
| `bg_hover` | `#3a3a3a` | Hover for secondary buttons |
| `bg_warm_banner` | `#1A0E00` | BETA banner bg, Graphics tab notice bg, future-feature card bg |

### Text

| Token | Hex | Usage |
|---|---|---|
| `text_primary` | `#ffffff` | Bold headings, key values |
| `text_secondary` | `#cccccc` | Body text, radio/checkbox labels |
| `text_muted` | `#aaaaaa` | Standard labels, card section headers, slider labels |
| `text_dim` | `#888888` | Sub-labels, stat card unit labels, section title chips |
| `text_subtle` | `#555555` | Hint text, fine print, disabled labels |

### Dividers

| Token | Hex | Usage |
|---|---|---|
| `separator` | `#444444` | Horizontal rule dividers between sections |
| `separator_dark` | `#333333` | Lighter dividers inside cards; top-bar pip |

### Special-purpose (semantic, not brand)

| Token | Hex | Usage |
|---|---|---|
| `green_action_bg` | `#1b5e20` | B-Roll Run / Search buttons (green = "go") |
| `green_action_hover` | `#2e7d32` | Hover for green action buttons |
| `purple_zoom_bg` | `#6a1b9a` | Auto Zooms "Apply Zooms" button |
| `purple_zoom_hover` | `#7b1fa2` | Hover for zoom button |
| `purple_stat` | `#ab47bc` | "Zoom Points Found" stat card value |

---

## Source-tag colors (B-Roll results window)

| Provider | Hex | Note |
|---|---|---|
| Pixabay | `#A85A3E` | Brand dim — distinct from Pexels |
| Pexels | `#E8903A` | Warning orange — distinct from Pixabay |

---

## Do's

- Use `brand_primary` (`#D97757`) for **any value the user is actively changing** (slider readouts, stat card numbers, progress bar fill).
- Use `btn_primary_bg` / `btn_primary_hover` for the **one primary CTA** per section. Never have two primary-orange buttons side-by-side.
- Use `warning` (`#E8903A`) for **non-blocking notices**: fallback to RMS, timing mismatch, BETA label. Reserve `error` (`#ff6b6b`) for failure states.
- Keep `success` (`#66bb6a`) for **completion and import** actions — these are semantically green regardless of brand.
- Keep `purple_zoom_bg` for Auto Zooms specifically — the distinct color makes it easy to identify which feature's button you're about to click.

## Don'ts

- Don't use `brand_primary` for body text or long-form labels — it's high-contrast and will cause visual fatigue.
- Don't use `warning` (`#E8903A`) as a generic accent; it reads as "attention needed." Use `brand_primary` for informational accents.
- Don't introduce new accent hues. The palette has three intentional accent families: orange (brand), green (action/success), purple (zooms). Adding a fourth creates visual noise.
- Don't change `bg_darkest` / `bg_dark` — Resolve's own UI is dark; these neutrals blend with the host environment.
