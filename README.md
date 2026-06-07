<img src="assets/icon.svg" width="96" alt="Clutter icon" />

# Clutter

**CLAUDE + CUTTER** — built by Claude Code.
A DaVinci Resolve plugin for editing talking-head videos faster.

> **Status: v0.1.0-alpha** — core features work, rough edges expected. Not production-ready.

Works with **DaVinci Resolve free and Studio** on Windows, macOS, and Linux.

---

## Philosophy

Clutter is built around one idea: **the editor shouldn't have to babysit the tool.**

Most Resolve plugins for talking-head cleanup are assistants — they surface candidates,
mark regions, or highlight pauses, then wait for you to confirm or discard each one.
That's still a lot of clicking.

Clutter goes the other direction. It analyzes the timeline, makes the call, and applies
the edit. You set the intent (a pace level, a sensitivity), and Clutter does the rest.
The human reviews the result, not every individual decision.

**AI is used only where it earns its cost.** Transcription (speech-to-text for subtitles)
genuinely requires a model. Silence detection, zoom placement, and B-roll matching do not —
those run locally with zero API calls. This keeps everyday editing free and fast, and leaves
the API budget for operations that actually need it.

The result is a tool that feels lightweight: launch it, set a knob, get an edit.

---

## Features

| Tab | Status | Description |
|---|---|---|
| **Smart Cuts** | ✅ Full | Remove silences with a pace slider (1–10) + fine-grained controls |
| **Subtitles** | ✅ Full | ElevenLabs or local Whisper STT → styled ASS subtitle track import |
| **Auto Zooms** | ✅ Full | Detect high-energy moments → apply zoom cuts |
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

Detects silent sections using pydub's silence analysis and reconstructs the timeline with silences removed.

**Pace Preset** (1–10 slider at the top of the card):

| Level | Style | Threshold | Min Pause |
|---|---|---|---|
| 1 | Very Slow | -55 dB | 1500 ms |
| 5 | YouTube | -35 dB | 350 ms |
| 10 | TikTok / Reels | -22 dB | 80 ms |

Moving the slider auto-fills the detection fields below it. Fine-tune manually if needed.

**Detection Settings:**
- **Silence Threshold** — how quiet counts as silence (dBFS)
- **Min Silence Duration** — minimum pause length to remove (ms)
- **Breathing Room** — ms to leave at each cut edge so speech isn't clipped
- **Preview** — adds red markers at silence locations without cutting
- **Apply Cuts** — dialog to create a new `_cuts` timeline or append to an existing one

Both video and audio tracks are preserved in the output timeline.

### Subtitles

Two STT providers:

| Provider | Notes |
|---|---|
| **ElevenLabs** | Cloud API — high accuracy, requires API key |
| **Local Whisper** | Runs on device via `faster-whisper`. First run downloads the model |

**Workflow:**
1. Choose provider → configure API key or Whisper model size
2. Choose language + layout preset
3. Click **Generate Transcript** → review and edit in the transcript box
4. Configure **Text Style** (font, size, colors, outline)
5. Click **Create Subtitle Track** → choose new or existing timeline → imports styled subtitle file
6. Export SRT / TXT for external use

**Layout Presets:**
- **YouTube** — 2 lines, ~7 words per line
- **Standard** — 2 lines, ~8 words per line
- **TikTok** — 1 line, uppercase, 5 words per line
- **Alex Hormozi Style** — word-by-word, uppercase

**Text Style Presets** (font, size, bold/italic/underline, text color, outline color + width):
- **YouTube** — Arial 36px bold, white text, black outline
- **Clean White** — Arial 32px, white text, thin outline
- **TikTok Bold** — Impact 48px bold, heavy outline
- **Minimal** — Arial 28px, white text, hairline outline

Save custom presets via **Save As…**. Built-in presets are protected from deletion.

> Subtitles are exported as ASS format (Advanced SubStation Alpha), which
> carries full font and color metadata. DaVinci Resolve imports ASS identically
> to SRT via drag-and-drop or Media Pool.

**Transcript editing:** Edit the transcript text freely before clicking
"Create Subtitle Track". Word timings are preserved when word count stays the
same; if count changes, timings are distributed proportionally and an orange
status message is shown.

### Auto Zooms

Analyzes volume peaks in the audio to find high-energy moments:

- **Conservative** — only very loud peaks (σ × 2.0)
- **Standard** — medium sensitivity (σ × 1.0)
- **High Energy** — aggressive, more frequent (σ × 0.5)

Apply shows the timeline dialog; creates a `_zooms` timeline or appends to an existing one.
Zoom is applied via `SetProperty("ZoomX"/"ZoomY")` per segment.
Fade mode uses DaVinci's `DynamicZoomEase` property.

### B-Roll Assistant (Scaffold)

1. Browse a folder of B-roll clips
2. Scan Folder — indexes filenames as keywords
3. Analyze Transcript — cross-references with Subtitles tab transcript
4. Suggest B-Roll — shows confidence-ranked matches

Auto-place planned for V2.

### Motion Graphics (Beta)

Rule-based scan of the transcript for graphic opportunities:
- Numbers/stats → Statistic Callout
- Process words (step, first, then…) → Process Diagram
- Quoted text → Quote Card
- Social media mentions → CTA Overlay

AI-powered generation planned for V2.

---

## Architecture

Two-process model via a localhost HTTP bridge. `main.py` runs inside Resolve's process
(where the `resolve` object lives), starts a bridge server, then spawns `gui.py` as a
subprocess. The GUI talks to Resolve through the proxy — no direct scripting access needed.

See [CLAUDE.md](CLAUDE.md) for full design notes and gotchas.

---

## Dependencies

| Package | Purpose |
|---|---|
| `customtkinter` | The GUI toolkit (resolves the UIManager removal in Resolve free v19.1) |
| `faster-whisper` | Local speech-to-text (optional, CPU or CUDA) |
| `pydub` | Audio loading and silence detection |
| `requests` | ElevenLabs API calls + HTTP bridge client |
| `numpy` | RMS computation for zoom detection |
| `Pillow` | App icon loading |
| `ffmpeg` (system) | Audio decoding (required by pydub) |

Install with `py -3.12 -m pip install -r requirements.txt`.

---

## Compatibility

- DaVinci Resolve **free** and **Studio** (v18+)
- **Python 3.10 / 3.11 / 3.12** (3.13+ segfaults on import)
- Windows, macOS, Linux

---

## License

[GPLv3](LICENSE.md)
