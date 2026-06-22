<img src="assets/icon.png" width="96" alt="Clutter icon" />

# Clautter

**CLAUDE + CUTTER** — built by Claude Code.
A DaVinci Resolve plugin for editing talking-head videos faster.

> **Status: BETA** — core features work, bugs expected.

Works with **DaVinci Resolve free and Studio** on Windows, macOS, and Linux.

---

## Philosophy

Clautter is built around one idea: **the editor shouldn't have to babysit the tool.**

Most Resolve plugins for talking-head cleanup are assistants — they surface candidates,
mark regions, or highlight pauses, then wait for you to confirm or discard each one.
That's still a lot of clicking. Clautter goes the other direction: it analyzes the timeline, 
makes the call, and applies the edit.

---

## Features

| Tab | Status | Description |
|---|---|---|
| **Smart Cuts** | ✅ Full | Remove silences with a pace slider (1–10) + fine-grained controls. VAD-based detection. Padding scales with pace preset and is applied as total (not per-edge). |
| **Subtitles** | ✅ Full | ElevenLabs or local Whisper STT → styled Fusion Title subtitle track. Hormozi/TikTok word-by-word mode. Re-running replaces existing subtitle clips automatically. |
| **Auto Zooms** | ✅ Full | Face Detection (OpenCV) or RMS peaks → zoom cuts with Fusion ease-in/out. |
| **B-Roll** | ✅ Full | Manual: folder scan + keyword match + online search (Pixabay/Pexels). Autonomous: one-click end-to-end pipeline. The **LLM mode** button is a provider picker — `Off` plus one segment per cloud LLM you have a key for (OpenAI / Gemini / Minimax / NVIDIA / Anthropic); pick one to let the LLM choose clips and positions. |
| **Music & SFX** | ✅ Full | Mood-matched background music (Jamendo / local folder), keyword or LLM mood engine, single-track or per-segment placement. Auto-placed sound effects (Freesound / Pixabay) keyed off cuts, zooms, and B-roll. Volume, fades, and ducking baked in via pydub. |
| **Enhance Audio** | ✅ Full | Clean up crappy source audio: DeepFilterNet noise/reverb removal + VAD gating (core, always on), with optional heavy engines (resemble-enhance speech restoration, demucs voice isolation) that install on demand behind a CPU-cost prompt. Cleaned audio lands on a dedicated **Enhanced** track, non-destructively. Auphonic cloud polish is stubbed for a later release. |
| **Motion Graphics** | 🔧 Beta | LLM-driven Hyperframes pipeline: describe the look, pick a style, let the LLM choose and customize templates. Templates are rendered to MOV (alpha channel) via the Hyperframes CLI (requires Node.js) and placed on the Motion Graphics track in Resolve. Supports Ollama and all cloud LLM providers. |

Clautter supports OpenAI, Gemini, Minimax, Anthropic, **NVIDIA**, and **Ollama**. NVIDIA grants free access to many open-source models via an OpenAI-compatible API, so you can run the cloud-LLM features without paying — paste an NVIDIA key in Settings → LLM Keys and the model id (e.g. `moonshotai/kimi-k2.6`) in Settings → LLM Models. For local inference, point Ollama to a running instance in Settings → LLM.

---

## Quick Start

> **Python 3.10 / 3.11 / 3.12 only.** DaVinci Resolve's compiled scripting
> module segfaults on 3.13+.

```
py -3.12 install.py             
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

`customtkinter`, `pydantic`, `faster-whisper`, `silero-vad`, `torchaudio`, `soundfile`, `onnxruntime`, `deepfilternet`, `spacy`, `yake`, `keybert`, `joblib`, `sentence-transformers`, `opencv-python`, `scenedetect`, `pydub`, `requests`, `numpy`, `Pillow` — plus `ffmpeg` (system) and **Node.js** (system, required for Motion Graphics rendering).

Install: `py -3.12 -m pip install -r requirements.txt`

---

## Compatibility

- DaVinci Resolve **free** and **Studio** (v18+)
- **Python 3.10 / 3.11 / 3.12** (3.13+ segfaults on import)
- Windows, macOS, Linux

> **Tested on Windows only.** macOS and Linux are untested.
> API key status: ElevenLabs ✅ · NVIDIA ✅ · OpenAI ⚠ untested · Gemini ⚠ untested · Anthropic ⚠ untested.

---

## Support

This is a part-time project. A paid installer is planned — pay once, get a one-click setup that handles Python, ffmpeg, and the plugin. No fiddling required. The installer is a way to support the project; the plugin itself stays free on GitHub.

No website or community yet. Issues and PRs welcome.

**Testing help wanted.** If you run Clautter on macOS or Linux, or test an API key (OpenAI, Gemini, Anthropic), please open an issue and report whether it worked. This helps update the compatibility table above.

---

## License

[GPLv3](LICENSE.md)
