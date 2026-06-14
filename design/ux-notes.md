# Clautter UX Notes

Running log of UX observations and deferred proposals. The terracotta rebrand +
icon-fix pass (see `palette.md`) shipped the items under **Done**; the rest are
proposals to pick up later.

---

## Done (this pass)

- **Unified terracotta palette** — killed competing accents (cyan/blue/indigo/feature-
  green/feature-purple). One accent family + status hues. See `palette.md`.
- **Custom CTk theme** (`assets/clautter_theme.json`) — all built-in widgets default
  terracotta instead of CTk's blue.
- **Window icons on every popup** — `icon_helper.apply_clautter_icon` now defers for
  Toplevels (so the icon actually sticks on Windows) and caches the generated `.ico`.
  Added the missing call to the **console window**. Settings / timeline / B-Roll-results
  windows all branded.
- **Connection status pill** — top-bar status is now a pill with a green/red dot, so
  connected vs disconnected reads at a glance instead of from text alone.
- **Primary-CTA weighting** — in action rows (Analyze · Preview · Apply), only the
  primary action is terracotta; secondary buttons opt out to `BG_CARD`.
- **Disabled legibility** — disabled-button text bumped to `TEXT_DIM` (`#888888`) via
  the theme, up from CTk's near-invisible gray.

---

## Proposals (not yet built)

### 1. Restructure crowded tabs (B-Roll, Music & SFX)
Both tabs stack many sections + conditional rows in one scroll. Propose collapsible
sections (CTk has no native collapsible; build a header-button + `pack_forget` toggle)
or a sub-step wizard. Highest-value UX change; deferred because it's a real layout
rewrite with behavior to re-test.

### 2. Settings: unsaved-changes indicator
Settings window has Apply/Done but no signal that edits are pending. Propose a dirty
flag → asterisk on the active nav item + a subtle "unsaved changes" hint by the Apply
button; warn on close-with-unsaved.

### 3. Progress step / ETA indicators
Long operations (transcription, B-roll search, music download) show only an
indeterminate-ish bar + status text. Propose discrete step labels ("2/4: matching
clips…") where the worker already knows its stages.

### 4. Slider readout consistency
Readouts are now all `BRAND_PRIMARY`. Minor: standardize placement (right of slider,
fixed width) and always include the unit (%, s, dB) across every tab.

---

## Asset flag

`assets/icon.png` is only ~509 bytes — almost certainly a very low-res source. The icon
works, but scaling it to 256×256 for the Windows taskbar `.ico` will look soft. A
higher-res `icon.png` (≥256×256) would sharpen both the title-bar and taskbar icons.
`assets/icon.svg` exists and can be rasterized to produce a crisp PNG.
