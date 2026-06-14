# DaVinci Resolve Scripting API — Clautter Reference

Practical reference for the Resolve Python scripting API as used in this project.
Covers free-edition behavior, known failures, and correct usage patterns derived
from working code. Updated as we discover new things.

**Free edition** = DaVinci Resolve 19.x free. **Studio** = paid license.
Differences are flagged explicitly. When no flag: behavior is the same on both.

---

## Table of Contents

1. [Connection & Acquisition](#1-connection--acquisition)
2. [Object Chain](#2-object-chain)
3. [Project](#3-project)
4. [MediaPool](#4-mediapool)
5. [Timeline](#5-timeline)
6. [TimelineItem](#6-timelineitem)
7. [MediaPoolItem](#7-mediapoolitem)
8. [MediaPoolFolder](#8-mediapoolfolder)
9. [Fusion Composition](#9-fusion-composition)
10. [Fusion Tool (TextPlus)](#10-fusion-tool-textplus)
11. [Free Edition Restrictions Summary](#11-free-edition-restrictions-summary)
12. [Known Bugs / Unresolved Issues](#12-known-bugs--unresolved-issues)

---

## 1. Connection & Acquisition

### How Resolve injects `resolve`

When a script runs via **Scripts → Utility menu**, Resolve injects `resolve`
into the script's **module globals**, NOT into `builtins`.

```python
# CORRECT — works in free edition
resolve = globals().get("resolve")

# WRONG — always returns None in free edition
import builtins
resolve = getattr(builtins, "resolve", None)
```

### Clautter's connection strategy (4-step fallback)

Implemented in `src/utils/resolve_api.py:54`.

| Step | Method | Edition |
|------|--------|---------|
| 0 | Caller-supplied `resolve_obj` | Both |
| 1 | HTTP bridge (`~/.clautter/bridge.json`) | Free (primary path) |
| 2 | `DaVinciResolveScript.scriptapp("Resolve")` | Studio only |
| 3 | `builtins.resolve` | In-Resolve console only |

The bridge exists because **external scripting is disabled on free**:
`scriptapp("Resolve")` returns `None` from any process outside Resolve.
The bridge server runs inside Resolve's process and proxies calls over localhost.
See [Architecture in CLAUDE.md](../CLAUDE.md).

---

## 2. Object Chain

```
resolve
  └── GetProjectManager()          → ProjectManager (never None if connected)
        └── GetCurrentProject()    → Project (None if no project open)
              ├── GetMediaPool()   → MediaPool (None if project invalid)
              └── GetCurrentTimeline() → Timeline (None if no timeline open)
```

Always re-fetch project and media_pool fresh from `resolve` each operation —
do NOT cache them across user actions. Resolve can replace the internal object
after timeline switches.

```python
# Correct pattern (from src/broll/placer.py:115)
project   = resolve.GetProjectManager().GetCurrentProject()
media_pool = project.GetMediaPool()
timeline   = project.GetCurrentTimeline()
```

---

## 3. Project

### `project.GetName() → str`
Always works. No known failures.

### `project.GetCurrentTimeline() → Timeline | None`
Returns `None` if no timeline is open. Guard every call:
```python
timeline = project.GetCurrentTimeline()
if timeline is None:
    raise RuntimeError("No timeline open — open one in Resolve first")
```

### `project.GetMediaPool() → MediaPool | None`
Returns `None` only if project is in a broken state. Treat as always available
when `GetCurrentProject()` returned non-None.

### `project.GetSetting(key: str) → str`
Returns a string, not a typed value. Always wrap in `try/except` and cast:

```python
# src/utils/resolve_utils.py:16
try:
    fps = float(project.GetSetting("timelineFrameRate"))
except (TypeError, ValueError):
    fps = 25.0
```

Known working keys:
| Key | Returns | Fallback |
|-----|---------|---------|
| `"timelineFrameRate"` | `"25"` / `"29.97"` / etc. | `25.0` |
| `"timelineResolutionWidth"` | `"1920"` | `1920` |
| `"timelineResolutionHeight"` | `"1080"` | `1080` |

### `project.GetTimelineCount() → int`
Safe, returns 0 if no timelines.

### `project.GetTimelineByIndex(i: int) → Timeline | None`
**1-based indexing.** Range: `range(1, count + 1)`.

```python
# src/utils/resolve_utils.py:67
count = project.GetTimelineCount()
for i in range(1, count + 1):
    tl = project.GetTimelineByIndex(i)
```

### `project.SetCurrentTimeline(timeline) → bool`
Switches the active timeline in Resolve's UI. Can fail if timeline is from a
different project. Return value is reliable.

---

## 4. MediaPool

### `media_pool.AppendToTimeline(clip_infos: list[dict]) → list[TimelineItem] | None | []`

Most important and most treacherous method.

**Return value:** can be `None`, `[]`, or a list of `TimelineItem`. Check:
```python
placed = media_pool.AppendToTimeline([clip_info])
if not placed:
    # failed — free edition restriction or bad clip_info
```

**Full clip_info dict** (all keys from `src/broll/placer.py:152`):
```python
clip_info = {
    "mediaPoolItem": mpi,        # MediaPoolItem — required
    "mediaType":     1,          # 1=video+audio, 2=video only, 3=audio only
    "startFrame":    0,          # source in-point (frame number in source file)
    "endFrame":      300,        # source out-point — OMIT KEY entirely if full clip
    "recordFrame":   1001,       # timeline frame to place at — see warning below
    "trackIndex":    2,          # 1-based video track index
}
```

**Omit `endFrame` entirely** (not set to None) when using full clip duration:
```python
# None confuses the API — delete the key instead
if clip_info["endFrame"] is None:
    del clip_info["endFrame"]
```

**`recordFrame` is IGNORED for subtitle clips.** Resolve places subtitle clips at
frame 0 regardless. Known Resolve bug, no workaround via scripting — user must
drag manually. Logged warning in `src/subtitles/srt_importer.py:88`.

**Free edition:** `AppendToTimeline` may silently return `[]` even on valid clips.
This is a free-edition restriction, not a bug in the clip_info dict.
(`src/broll/placer.py:178`)

### `media_pool.ImportMedia(paths: list[str]) → list[MediaPoolItem] | []`

```python
items = media_pool.ImportMedia(["/abs/path/to/clip.mp4"])
if not items:
    # unsupported format, bad path, or free edition restriction
    return
mpi = items[0]
```

Returns `[]` on unsupported format. Supports: `.mp4`, `.mov`, `.srt`, common
video/audio. Does NOT support relative paths.

### `media_pool.CreateEmptyTimeline(name: str) → Timeline | None`
Returns `None` if name is empty, duplicate (behavior varies), or project unavailable.
Check return:
```python
tl = media_pool.CreateEmptyTimeline("My Timeline")
if tl is None:
    raise RuntimeError("CreateEmptyTimeline failed — duplicate name?")
```

### `media_pool.ImportFolderFromFile(path: str, folder_name: str = "") → bool`
Imports a `.drb` template bundle. Used for Fusion title templates.
`src/subtitles/fusion_template.py:50`.

### `media_pool.GetRootFolder() → MediaPoolFolder`
Always returns the root folder. See [MediaPoolFolder](#8-mediapoolfolder).

---

## 5. Timeline

### `timeline.GetName() → str`
Always works.

### `timeline.GetStartFrame() → int`
Returns the timeline's first frame number (may be 0, 1, or 1001 depending on
project settings). Required for computing `recordFrame`:
```python
tl_start   = timeline.GetStartFrame()
record_frame = tl_start + int(round(seconds * fps))
```

### `timeline.GetTrackCount(track_type: str) → int`
`track_type`: `"video"`, `"audio"`, `"subtitle"`.
Returns 0 if no tracks of that type. Safe.

### `timeline.GetTrackName(track_type: str, track_index: int) → str | None`
1-based index. Returns `None` on out-of-range or error. Always guard:
```python
name = timeline.GetTrackName("video", i) or ""
```

### `timeline.SetTrackName(track_type: str, track_index: int, name: str)`
**Free edition: silently fails.** Track still exists and is usable — just unnamed.
Always wrap in try/except and treat failure as non-fatal:
```python
# src/broll/placer.py:57
try:
    timeline.SetTrackName("video", new_index, "B-Roll")
except Exception as e:
    log.debug("SetTrackName failed (non-fatal): %s", e)
```

### `timeline.AddTrack(track_type: str) → bool | None`
Return value is **unreliable** — don't trust it. Check count before/after:
```python
before = timeline.GetTrackCount("video")
timeline.AddTrack("video")
after  = timeline.GetTrackCount("video")
new_index = after  # 1-based, so new track = count after
```

### `timeline.GetItemListInTrack(track_type: str, track_index: int) → list[TimelineItem] | None`
Returns `None` (not `[]`) when track is empty or index is invalid.
**Always guard:**
```python
items = timeline.GetItemListInTrack("video", 1) or []
```

### `timeline.DeleteClips(items: list[TimelineItem])`
Deletes clips from timeline. Pass the list returned by `GetItemListInTrack`.
No return value. Can raise on empty list — guard if needed.

### `timeline.InsertFusionTitleIntoTimeline(title_type: str) → TimelineItem | None`
**Side effect:** creates a persistent `MediaPoolItem` in the Media Pool. The item
stays even if the timeline item is deleted. This is intentional behavior used by
the subtitles pipeline to bootstrap Fusion templates.
Known title types: `"Text+"`, `"Solid Color"`, and others from the Effects panel.

### `timeline.GetCurrentVideoItem() → TimelineItem | None`
Returns the clip under the playhead on the current video track.
**Free edition: unreliable**, can return `None` even when a clip exists.
Fallback: scan track 1 for clips that contain the playhead frame.
(`src/ui/_subtitles_import.py:25`)

### `timeline.AddMarker(frame, color, name, note, duration, custom_data) → bool`
All positional args required. `color` is a string: `"Blue"`, `"Red"`, `"Green"`,
`"Yellow"`, `"Purple"`, `"Cyan"`, `"Fuchsia"`, `"Rose"`, `"Lavender"`,
`"Sky"`, `"Mint"`, `"Lemon"`, `"Sand"`, `"Cocoa"`, `"Cream"`.

---

## 6. TimelineItem

A clip placed on the timeline. Obtained via `GetItemListInTrack` or `AppendToTimeline`.

### `item.GetStart() → int`
Timeline frame number where the clip starts. This is the **timeline** position,
not the source file frame.

### `item.GetEnd() → int`
Timeline frame number where the clip ends (exclusive).

### `item.GetSourceStartFrame() → int`
Frame number in the source media file where this clip's in-point is.

### `item.GetSourceEndFrame() → int`
Frame number in the source media file where this clip's out-point is.

### `item.GetMediaPoolItem() → MediaPoolItem | None`
Returns `None` for clips generated by Resolve (Fusion titles, solids) and for
Studio-generated clips when running on Free edition.
Always guard:
```python
mpi = item.GetMediaPoolItem()
if mpi is None:
    return None  # generated clip or free edition limitation
```

### `item.SetProperty(name: str, value) → bool`
**There is NO keyframe/animation API on TimelineItem.** SetProperty only sets
static per-clip values. This was confirmed by API probe (`scripts/zoom_probe.py`).
Fusion `SetInput("Size", …)` on a scripted Transform tool is also a silent no-op
because it's not wired into the comp's render graph.

Working properties:
| Property | Type | Notes |
|----------|------|-------|
| `"ZoomX"` | float | 1.0 = 100% |
| `"ZoomY"` | float | 1.0 = 100% |
| `"ZoomGang"` | int | 1 = gang X/Y |
| `"Pan"` | float | horizontal offset, –1.0 to 1.0 |
| `"Tilt"` | float | vertical offset, –1.0 to 1.0 |
| `"DynamicZoomEase"` | int | 0=none, 1=ease in, 2=ease out, 3=both |
| `"Font"` | str | font family name |
| `"FontSize"` | str | numeric string e.g. `"36"` |

### `item.GetFusionCompCount() → int`
Returns number of Fusion compositions on this clip. 0 = no Fusion comp.

### `item.GetFusionCompByIndex(i: int) → FusionComp | None`
**0-based indexing** (unlike most other Resolve APIs which are 1-based).
First comp = index 0. Returns `None` if out of range.

---

## 7. MediaPoolItem

A clip in the Media Pool (not yet on timeline, or a reference to a pool item).

### `mpi.GetClipProperty() → dict | None`
Returns a dict of clip metadata. Keys are **not standardized** across Resolve
versions. File path has 4 possible keys — try in order:

```python
# src/utils/resolve_utils.py:44
for key in ("File Path", "FilePath", "Clip Path", "clipPath"):
    val = props.get(key)
    if val:
        return str(val)
```

Other known keys: `"Clip Name"`, `"Type"`, `"FPS"`, `"Duration"`,
`"Start TC"`, `"End TC"`, `"Video Codec"`, `"Frames"`.

### `mpi.GetFusionCompByIndex(i: int) → FusionComp | None`
Same as TimelineItem. 0-based. Used to access Fusion comps on template clips.

### `mpi.GetFusionCompCount() → int`
Same as TimelineItem.

---

## 8. MediaPoolFolder

### `folder.GetClipList() → list[MediaPoolItem] | None`
Returns `None` (not `[]`) when empty. Guard:
```python
clips = folder.GetClipList() or []
```

### `folder.GetSubFolderList() → list[MediaPoolFolder] | None`
Returns `None` (not `[]`) when no subfolders. Guard with `or []`.

---

## 9. Fusion Composition

Obtained via `item.GetFusionCompByIndex(0)` on a TimelineItem or MediaPoolItem.

### `comp.FindToolByID(tool_id: str) → FusionTool | None`
Finds a tool by type ID. Use for typed tools:
- `"TextPlus"` — Text+ generator
- `"Template"` — template node

Returns `None` if not found.

### `comp.FindTool(tool_name: str) → FusionTool | None`
Finds a tool by its **name** (label in the node graph), not type.
Useful when you know the specific node name.

### `comp.GetToolList() → dict | None`
Returns dict of `{name: tool}` for all tools. Used for debugging to discover
what's in a comp. Can return `None`.

---

## 10. Fusion Tool (TextPlus)

Obtained via `comp.FindToolByID("TextPlus")` or `comp.FindTool(name)`.

### `tool.SetInput(name: str, value) → None`
**Always wrap each call individually in try/except.** Missing input names are
silently ignored — no exception — but some Resolve versions do raise.

```python
# src/subtitles/fusion_style.py pattern
try:
    tool.SetInput("Font", "Arial")
except Exception:
    pass
try:
    tool.SetInput("Size", 0.1)
except Exception:
    pass
```

Never batch-guard multiple SetInput calls under one try/except — a failure on
one would silently skip the rest.

### `tool.GetInput(name: str) → value | None`
Returns `None` for missing or undefined inputs. Cannot be relied on to check
if an input exists — some inputs report `None` even when defined.

### Known TextPlus input names

| Input | Type | Notes |
|-------|------|-------|
| `"StyledText"` | str | Main text content. Prefer over `"Text"`. |
| `"Text"` | str | Fallback for older comps. |
| `"Font"` | str | Font family name. |
| `"Style"` | str | `"Regular"`, `"Bold"`, `"Italic"`. |
| `"Size"` | float | Normalized: `point_size / 360.0`. |
| `"Bold"` | int | 1 = bold. |
| `"Italic"` | int | 1 = italic. |
| `"Underline"` | int | 1 = underline. |
| `"Red1"` | float | Primary color R (0.0–1.0). |
| `"Green1"` | float | Primary color G (0.0–1.0). |
| `"Blue1"` | float | Primary color B (0.0–1.0). |
| `"Red2"` | float | Secondary color R. |
| `"Green2"` | float | Secondary color G. |
| `"Blue2"` | float | Secondary color B. |
| `"BorderWidth"` | float | Outline width. |
| `"HorizontalJustificationNew"` | int | 0=left, 1=center, 2=right. |
| `"VerticalJustificationNew"` | int | 0=top, 1=center, 2=bottom. |
| `"Center"` | table | `{1: x, 2: y}` position (0.0–1.0). |

---

## 11. Free Edition Restrictions Summary

| Feature | Free behavior | Workaround |
|---------|--------------|-----------|
| External scripting | Disabled. `scriptapp("Resolve")` = `None` | HTTP bridge (Clautter's approach) |
| `SetTrackName()` | May fail silently | wrap try/except, treat as non-fatal |
| `AppendToTimeline()` | May return `[]` even on valid clips | log warning, inform user |
| `GetCurrentVideoItem()` | May return `None` | fallback: scan track for playhead position |
| `GetMediaPoolItem()` on generators | Returns `None` | skip or use track-level detection |
| SRT `recordFrame` | Ignored by Resolve | user drags manually (logged warning) |
| Keyframe API | Does not exist in any edition | static `SetProperty` only |

---

## 12. Known Bugs / Unresolved Issues

### `recordFrame` ignored for subtitle clips
Resolve ignores `recordFrame` when appending SRT subtitle items via
`AppendToTimeline`. Clip always lands at frame 0. No scripting workaround known.
User must drag the subtitle clip to the correct position manually.
**Source:** `src/subtitles/srt_importer.py:88`

### `AppendToTimeline` silent failure on free edition
Returns `[]` without error when placing clips on a video track that the free
edition restricts. Not reproducible on Studio. Treat as informational failure —
log it, surface a user message, don't retry.
**Source:** `src/broll/placer.py:178`

### File path key in `GetClipProperty()`
No single standard key for the file path. Four variants observed across versions:
`"File Path"`, `"FilePath"`, `"Clip Path"`, `"clipPath"`. Try in that order.
**Source:** `src/utils/resolve_utils.py:44`

### `InsertFusionTitleIntoTimeline` leaves MediaPoolItem behind
Deleting the timeline item does not remove the generated MediaPoolItem from the
pool. This is an intentional Resolve behavior, not a bug from our side — the
subtitles pipeline exploits it to bootstrap templates. Just be aware the pool
accumulates these items over time.
**Source:** `src/subtitles/fusion_placer.py`

### No keyframe API on TimelineItem
`SetProperty` sets static values only. Resolve does not expose any per-clip
keyframe animation API through Python scripting. Fusion scripted tools
(`SetInput("Size", …)`) are also a no-op because the node is not wired into
the render graph. Static zoom values (`ZoomX`/`ZoomY`/`Pan`/`Tilt`) do work.
**Source:** `src/zooms/applier.py:6–14`, confirmed by `scripts/zoom_probe.py`

### `GetFusionCompByIndex` is 0-based; everything else is 1-based
The entire Resolve API uses 1-based indexing except `GetFusionCompByIndex`.
First comp = index 0. This has caused off-by-one bugs. Always use index 0 for
the first (and usually only) comp.
**Source:** `src/subtitles/srt_importer.py:102`
