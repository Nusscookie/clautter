# Clutter

**CLAUDE + CUTTER** — built by Claude Code.
A professional DaVinci Resolve plugin for editing talking-head videos faster.

Works with **DaVinci Resolve free and Studio** on Windows, macOS, and Linux.

---

## Features

| Tab | Status | Description |
|---|---|---|
| **Smart Cuts** | ✅ Full | Automatically remove silences. Non-destructive — creates a new timeline |
| **Pace Control** | ✅ Full | One slider (1–10) maps to editing intensity. Drives Smart Cuts |
| **Subtitles** | ✅ Full | ElevenLabs STT → SRT generation → subtitle track import |
| **Auto Zooms** | ✅ Full | Detect high-energy moments → apply zoom cuts to new timeline |
| **B-Roll Assistant** | 🔧 Scaffold | Folder scan + keyword matching. Auto-place coming in V2 |
| **Motion Graphics** | 🔧 Beta | Rule-based graphic suggestions. AI generation coming in V2 |

---

## Quick Start

> **Python 3.10 / 3.11 / 3.12 only.** DaVinci Resolve's compiled scripting
> module segfaults on 3.13+.

```
1. Install dependencies:  py -3.12 -m pip install -r requirements.txt
2. Install ffmpeg:         https://ffmpeg.org/download.html
3. Copy folder to:        %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\
4. Open DaVinci Resolve → Workspace → Scripts → Utility → Clutter → main
```

See [INSTALL.md](INSTALL.md) for the full guide.

---

## Tab Details

### Smart Cuts

Detects silent sections using pydub's silence analysis and creates a new clean timeline with all silences removed.

- **Silence Threshold** — how quiet counts as silence (dBFS)
- **Min Silence Duration** — minimum pause length to remove (ms)
- **Breathing Room** — ms to leave at each cut edge so speech isn't clipped
- **Preview** — adds red markers at silence locations without cutting
- **Apply Cuts** — creates a new `_cuts` timeline with silences removed

### Pace Control

Maps a single 1–10 slider to Smart Cuts parameters:

| Level | Style | Threshold | Min Pause |
|---|---|---|---|
| 1 | Very Slow | -55 dB | 1500 ms |
| 5 | YouTube | -35 dB | 350 ms |
| 10 | TikTok | -22 dB | 80 ms |

### Subtitles

Uses ElevenLabs Scribe (Speech-to-Text) API:

1. Enter API key → Save
2. Choose language + style preset
3. Click **Generate Transcript** → review transcript in the editor
4. Click **Create Subtitle Track** → imports SRT into timeline
5. Export SRT / TXT for external use

**Presets:**
- **YouTube** — 2 lines, ~7 words per line
- **Standard** — 2 lines, ~8 words per line
- **TikTok** — 1 line, uppercase, 5 words per line
- **Alex Hormozi Style** — word-by-word, uppercase

### Auto Zooms

Analyzes volume peaks in the audio to find high-energy moments:

- **Conservative** — only very loud peaks (σ × 2.0)
- **Standard** — medium sensitivity (σ × 1.0)
- **High Energy** — aggressive, more frequent (σ × 0.5)

Results: a new `_zooms` timeline with zoom segments at detected moments.
Zoom is applied via `SetProperty("ZoomX"/"ZoomY")` per segment.
Fade mode uses DaVinci's `DynamicZoomEase` property.

### B-Roll Assistant (Scaffold)

1. Browse a folder of B-roll clips
2. Scan Folder — indexes filenames as keywords
3. Analyze Transcript — cross-references with Subtitles tab transcript
4. Suggest B-Roll — shows confidence-ranked matches

Auto-place on V2 is planned for V2.

### Motion Graphics (Beta)

Rule-based scan of the transcript for graphic opportunities:
- Numbers/stats → Statistic Callout
- Process words (step, first, then…) → Process Diagram
- Quoted text → Quote Card
- Social media mentions → CTA Overlay

AI-powered generation (Minimax / Gemini / OpenAI) is planned for V2.

---

## Architecture

Two-process model — the GUI is a standalone window that connects to Resolve
via the external scripting API. This works around `UIManager` being removed
from DaVinci Resolve free edition in v19.1.

```
DaVinci Resolve  →  main.py  (Resolve-side launcher, no UI)
                       └─ subprocess.Popen( py -3.12, gui.py )
                            └─ gui.py  (standalone customtkinter window)
                                 └─ src/app.py (AIEditorApp, framework-agnostic)
                                     ├─ src/<feature>/*.py  (business logic, no widgets)
                                     ├─ src/ui/<tab>.py     (customtkinter widgets)
                                     └─ src/utils/resolve_api.py  (Resolve bridge)
```

```
src/
├── app.py              # Central coordinator (framework-agnostic)
├── ui/                 # customtkinter tab layouts + event handlers
├── smartcuts/          # pydub silence detection + timeline reconstruction
├── subtitles/          # ElevenLabs STT client + SRT generator + exporter
├── zooms/              # Volume peak detection + SetProperty zoom applier
├── pace/               # Pace level → SmartCuts parameter mapping
├── broll/              # Folder scanner + keyword matcher
├── graphics/           # Rule-based graphic suggester
├── settings/           # JSON config persistence (~/.clutter/)
└── utils/              # Resolve API helpers, audio loading, logger
```

See [CLAUDE.md](CLAUDE.md) for the full design notes and gotchas.

---

## Dependencies

| Package | Purpose |
|---|---|
| `customtkinter` | The GUI toolkit (resolves the UIManager removal in Resolve free v19.1) |
| `pydub` | Audio loading and silence detection |
| `requests` | ElevenLabs API calls |
| `numpy` | RMS computation for zoom detection |
| `ffmpeg` (system) | Audio decoding (required by pydub) |

Install with `py -3.12 -m pip install -r requirements.txt`.

---

## Compatibility

- DaVinci Resolve **free** and **Studio** (v18+)
- **Python 3.10 / 3.11 / 3.12** (3.13+ segfaults on import)
- Windows, macOS, Linux

---

## License

MIT
