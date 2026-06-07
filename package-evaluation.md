# Package Evaluation — Clutter

**Current stack:** pydub, numpy, faster-whisper, yake (opt), spacy (opt), customtkinter.
**Goal:** identify high-value additions, prioritizing local/no-API-key options.

---

## By Feature

### Smart Cuts — silence detection
*Gap: crude RMS threshold struggles with quiet speakers in noisy rooms.*

| Package | Rating | Verdict |
|---|---|---|
| `silero-vad` *(not on list)* | ★★★★★ | ONNX VAD. Handles music/noise. Best local option for speech/silence. **Top pick.** |
| `webrtcvad` *(not on list)* | ★★★★★ | Google VAD. Tiny, fast, no model download. **Strong alternative.** |
| `librosa` | ★★★★ | Spectral + onset detection. Already in requirements as optional — make required. |
| `scipy` | ★★★ | Bandpass filter (300–3000Hz) before RMS. Lightweight add. |
| `soundfile` | ★★ | Audio reader. pydub+ffmpeg covers this. **Skip.** |

---

### Retake Detection
*Gap: filler words ("um", "uh") cause false positives in difflib matching.*

| Package | Rating | Verdict |
|---|---|---|
| `spacy` | ★★★ | Already optionally used in broll. Normalize fillers before difflib. **Reuse — no new dep.** |
| `nltk` | ★★ | Redundant with spacy here. **Skip.** |
| `openai-whisper` | ✗ | Slower, requires PyTorch. faster-whisper is strictly better. **Skip.** |
| `ctranslate2` | ✗ | Already the faster-whisper backend. **Skip.** |

---

### Subtitles — transcription
*Gap: model size hardcoded to "base"; no speaker identification.*

| Package | Rating | Verdict |
|---|---|---|
| `faster-whisper` | ✓ IN USE | Expose model size (tiny/base/small/medium/large) in settings UI. |
| `whisperx` *(not on list)* | ★★★★ | Forced word-level alignment on top of faster-whisper. Tighter subtitle timestamps. **Add.** |
| `pyannote.audio` *(not on list)* | ★★★ | Speaker diarization. Multi-speaker subtitle coloring + zoom tracking. Needs HuggingFace token. |
| `openai-whisper` | ✗ | Redundant. **Skip.** |

---

### B-Roll — keyword extraction & placement
*Gap: word-overlap matching with ~2 words/sec timeline estimate. Semantic matching noted as TODO in [matcher.py](src/broll/matcher.py).*

| Package | Rating | Verdict |
|---|---|---|
| `sentence-transformers` | ★★★★★ | **Fixes the TODO.** Semantic similarity, fully local. `all-MiniLM-L6-v2` = 80MB, no API key. **Add.** |
| `keybert` | ★★★★ | Uses sentence-transformers for keyword extraction. Better than YAKE for semantic relevance. Add as backend in [keywords.py](src/broll/keywords.py). |
| `open-clip-torch` | ★★★★ | CLIP — matches video frames to text. Visual B-roll ranking against transcript. Requires torch (~2GB). |
| `scenedetect` | ★★★ | Detects scene cuts in B-roll clips. Avoids mid-scene splice in timeline placement. |
| `spacy` | ★★★ | NER extracts "Paris", "BMW", "sunset" as B-roll topics. Already optionally supported. |
| `yake` | ✓ IN USE | Statistical fallback when no model available. Keep. |
| `transformers` | ★★ | sentence-transformers already wraps it. **Skip as direct dep.** |
| `torch` | ★★★ | Required by sentence-transformers + open-clip. ~2GB. Add only alongside those. |

---

### Auto-Zoom
*Gap: pure RMS peak detection — zooms on loud sounds, not faces.*

| Package | Rating | Verdict |
|---|---|---|
| `mediapipe` | ★★★★★ | Face detection + landmark tracking. Zoom-to-face instead of zoom-to-noise. ~50MB, fully local. **Top priority.** |
| `opencv-python` | ★★★★ | Frame extraction from video, required as mediapipe input. **Add with mediapipe.** |
| `face-recognition` | ★★ | Wraps dlib. Slower and heavier than mediapipe. **Skip.** |
| `dlib` | ✗ | Large C++ build dep. mediapipe is better. **Skip.** |

---

### Local LLM — no API key
*Gap: B-roll reasoning, editing suggestions, smart defaults all require cloud API.*

| Package | Rating | Verdict |
|---|---|---|
| `llama-cpp-python` | ★★★★ | Runs GGUF models locally via CPU (4-bit quant). B-roll reasoning, editing suggestions. **Add.** |
| `gpt4all` | ★★★ | Simpler API than llama-cpp. Good fallback if llama-cpp build fails. |
| `mlx-lm` | ✗ | Mac-only. **Skip on Windows.** |

**Recommended GGUF models (4–8GB RAM):**
- `Qwen3-4B-Q4` — best reasoning/size ratio
- `Phi-4-mini-Q4` — fast, good structured output
- `Llama-3.2-3B-Q4` — reliable baseline

---

### Utility

| Package | Rating | Verdict |
|---|---|---|
| `pydantic` | ★★★★ | Typed settings models for `~/.clutter/config.json`. Replace raw dict in [manager.py](src/settings/manager.py). **Add.** |
| `joblib` | ★★★ | Cache embeddings/keyword extraction results. Add alongside sentence-transformers. |
| `tqdm` | ★★ | Project uses CTk progress bars. tqdm is CLI/debug only. **Skip or dev-only.** |
| `loguru` | ✗ | Already using stdlib logging with rotation. Switching is churn. **Skip.** |
| `pandas` | ✗ | Overkill. numpy + Python lists sufficient. **Skip.** |

---

### OCR / Text Detection

| Package | Rating | Verdict |
|---|---|---|
| `easyocr` | ★ | No use case for talking-head editing. **Skip.** |
| `pytesseract` | ★ | Same. **Skip.** |

---

## Priority Tiers

**Tier 1 — high value, low weight, add now:**
- `silero-vad` — smarter silence detection (replaces crude RMS)
- `mediapipe` + `opencv-python` — face-based zoom placement
- `sentence-transformers` — semantic B-roll matching
- `pydantic` — typed settings

**Tier 2 — high value, heavier, add when feature prioritized:**
- `whisperx` — tighter subtitle word alignment
- `keybert` — smarter B-roll keywords
- `scenedetect` — B-roll boundary detection
- `librosa` — make required (currently optional)
- `llama-cpp-python` + GGUF model — local LLM reasoning

**Tier 3 — conditional on Tier 2:**
- `open-clip-torch` — visual frame-to-text B-roll matching (requires torch)
- `torch` — needed by sentence-transformers + open-clip

**Skip entirely:**
`openai-whisper`, `ctranslate2`, `soundfile`, `dlib`, `face-recognition`, `easyocr`, `pytesseract`, `moviepy`, `mlx-lm`, `loguru`, `pandas`, `tqdm`, `nltk`

---

*All Tier 1 + Tier 2 packages run fully locally. No API key required.*
