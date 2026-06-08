<img src="assets/icon.png" width="96" alt="Clutter icon" />

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

---

## Features

| Tab | Status | Description |
|---|---|---|
| **Smart Cuts** | ✅ Full | Remove silences with a pace slider (1–10) + fine-grained controls. VAD-based detection. |
| **Subtitles** | ✅ Full | ElevenLabs or local Whisper STT → styled ASS subtitle track. Hormozi/TikTok word-by-word mode. |
| **Auto Zooms** | ✅ Full | Face Detection (OpenCV) or RMS peaks → zoom cuts with Fusion ease-in/out. |
| **B-Roll** | ✅ Full | Manual: folder scan + keyword match + online search (Pixabay/Pexels). Autonomous: one-click end-to-end pipeline with optional LLM re-rank + V2 auto-placement. |
| **Motion Graphics** | 🔧 Beta | Rule-based graphic suggestions. AI generation planned for V2. |

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

## Architecture

Two-process model via a localhost HTTP bridge. `main.py` runs inside Resolve's process
(where the `resolve` object lives), starts a bridge server, then spawns `gui.py` as a
subprocess. The GUI talks to Resolve through the proxy — no direct scripting access needed.

See [CLAUDE.md](CLAUDE.md) for full design notes and gotchas.

---

## Design

Brand color palette documented in [design/palette.md](design/palette.md).
Primary accent: `#D97757` (terracotta orange, from the app icon).

---

## Dependencies

| Package | Purpose |
|---|---|
| `customtkinter` | GUI toolkit |
| `faster-whisper` | Local speech-to-text (optional) |
| `silero-vad` + `onnxruntime` | VAD-based silence detection |
| `spacy` | Retake detection filler normalization |
| `opencv-python` | Face-based zoom detection |
| `sentence-transformers` | Semantic B-roll matching |
| `pydub` | Audio loading and RMS detection |
| `requests` | ElevenLabs API + HTTP bridge client + online B-roll search |
| `numpy` | RMS computation |
| `Pillow` | App icon loading |
| `scenedetect` | B-roll boundary detection |
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
