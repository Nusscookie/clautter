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

For the operations that *do* use a cloud LLM (autonomous B-roll direction, B-roll re-rank,
music mood analysis), Clutter supports OpenAI, Gemini, Minimax, and **NVIDIA**. NVIDIA grants
free access to many open-source models via an OpenAI-compatible API, so you can run the
cloud-LLM features without paying — paste an NVIDIA key in Settings → LLM Keys and the model
id (e.g. `moonshotai/kimi-k2.6`) in Settings → LLM Models.

---

## Features

| Tab | Status | Description |
|---|---|---|
| **Smart Cuts** | ✅ Full | Remove silences with a pace slider (1–10) + fine-grained controls. VAD-based detection. |
| **Subtitles** | ✅ Full | ElevenLabs or local Whisper STT → styled ASS subtitle track. Hormozi/TikTok word-by-word mode. |
| **Auto Zooms** | ✅ Full | Face Detection (OpenCV) or RMS peaks → zoom cuts with Fusion ease-in/out. |
| **B-Roll** | ✅ Full | Manual: folder scan + keyword match + online search (Pixabay/Pexels). Autonomous: one-click end-to-end pipeline. The **LLM mode** button is a provider picker — `Off` plus one segment per cloud LLM you have a key for (OpenAI / Gemini / Minimax / NVIDIA); pick one to let the LLM choose clips and positions. |
| **Music & SFX** | ✅ Full | Mood-matched background music (Jamendo / local folder), keyword or LLM mood engine, single-track or per-segment placement. Auto-placed sound effects (Freesound / Pixabay) keyed off cuts, zooms, and B-roll. Volume, fades, and ducking baked in via pydub. |
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

Visual flow maps of every feature — steps, decision points, and the real
thresholds — live in [docs/whiteboard/](docs/whiteboard/) as editable
Excalidraw diagrams, so you can see how a feature works without reading the code.

---

## Design

Brand color palette documented in [design/palette.md](design/palette.md).
Primary accent: `#D97757` (terracotta orange, from the app icon).

---

## Dependencies

| Package | Purpose |
|---|---|
| `customtkinter` | GUI toolkit |
| `pydantic` | Typed settings models + validation |
| `faster-whisper` | Local speech-to-text (subtitles) |
| `silero-vad` + `torchaudio` + `soundfile` + `onnxruntime` | VAD-based silence detection |
| `spacy` + `en-core-web-sm` | Keyword extraction (B-roll) + retake filler normalization |
| `yake` + `keybert` + `joblib` | Keyword extraction + embedding cache (B-roll search) |
| `sentence-transformers` | Semantic B-roll matching + mood analysis |
| `opencv-python` | Face-based zoom detection |
| `scenedetect` | B-roll boundary detection (autonomous mode) |
| `pydub` | Audio loading, RMS detection, music/SFX volume + fades |
| `requests` | ElevenLabs API + HTTP bridge client + online B-roll/music/SFX search |
| `numpy` | RMS computation |
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
