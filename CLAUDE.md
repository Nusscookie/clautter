# CLAUDE.md — Clutter

> DaVinci Resolve plugin for talking-head video editing (silence cutting,
> subtitles, auto-zooms, B-roll, motion graphics). Read this before touching
> the codebase.

---

## Stack

| Component | Version | Why |
|---|---|---|
| **Python** | **3.10 / 3.11 / 3.12 only** | `DaVinciResolveScript.pyd` **segfaults on 3.13+** (ABI mismatch). Pin with `py -3.12`. |
| **DaVinci Resolve** | 18+ (free or Studio) | Free edition removed `UIManager` in v19.1 — see Gotchas. |
| **customtkinter** | ≥ 5.2.0 | The GUI. Replaces the removed UIManager. |
| **pydub, requests, numpy** | see requirements.txt | Audio, ElevenLabs API, RMS. |
| **ffmpeg** | system PATH | Required by pydub. |

**Sanity check on any new machine:**

```bash
py -3.12 -c "import customtkinter, DaVinciResolveScript; print('ok')"
```

If this segfaults, the Python version is wrong. Do not proceed.

---

## Architecture (two-process — do not collapse)

```
DaVinci Resolve → main.py (Resolve-side launcher, no UI)
                     └─ subprocess.Popen(system_python, gui.py)
                          └─ gui.py (standalone CTk window, external scripting API)
                               └─ src/app.py (AIEditorApp, framework-agnostic)
                                    ├─ src/<feature>/*.py  (business logic, no widgets)
                                    ├─ src/ui/<tab>.py     (CTk widgets)
                                    └─ src/utils/resolve_api.py  (Resolve bridge)
```

| File | Role |
|---|---|
| `main.py` | Minimal launcher in `Scripts/Utility/Clutter/`. Probes `py -3.10/3.11/3.12` for one that imports both `customtkinter` and `DaVinciResolveScript`. Spawns `gui.py` via `subprocess.Popen` (never `run`/`wait` — the Scripts menu must return). |
| `gui.py` | CTk window. Connects to Resolve via `DaVinciResolveScript.scriptapp("Resolve")`. **Connect runs on a daemon thread with a 5s timeout** so the UI opens even without Resolve. |
| `src/app.py` | `AIEditorApp` — framework-agnostic, no tkinter import. Holds `resolve`, `project`, `timeline`, `transcript`, `settings`. |
| `src/<feature>/*` | Pure logic. No widgets. Only uses `app.resolve`, `app.project`, etc. |
| `src/ui/<tab>.py` | Each tab has two functions: `build(parent)` (layout) and `setup(parent, app)` (callbacks). Widget refs live in `parent._w = {}`. |
| `src/utils/resolve_api.py` | All Resolve API calls funnel through here. |
| `src/settings/manager.py` | JSON at `~/.clutter/config.json` (API keys, prefs, stats). |
| `src/utils/logger.py` | stderr + rotating file at `~/.clutter/logs/ai_editor.log`. Use `log.info/warn/error` — not `print()`. |

### Tab → module map

| Tab | UI | Logic |
|---|---|---|
| Smart Cuts | `ui/smartcuts_tab.py` | `smartcuts/analyzer.py` + `cutter.py` |
| Pace Control | `ui/pace_tab.py` | `pace/controller.py` |
| Subtitles | `ui/subtitles_tab.py` | `subtitles/elevenlabs.py` + `generator.py` + `exporter.py` |
| Auto Zooms | `ui/zooms_tab.py` | `zooms/analyzer.py` + `applier.py` |
| B-Roll | `ui/broll_tab.py` | `broll/scanner.py` + `matcher.py` |
| Motion Graphics | `ui/graphics_tab.py` | `graphics/suggester.py` |

---

## Conventions

### Threading (tkinter is NOT thread-safe)

Every worker thread routes UI updates through `frame.after(0, ...)`:

```python
def _ui(fn): frame.after(0, fn)
def set_status(msg, color="#aaaaaa"):
    _ui(lambda: w["status"].configure(text=msg, text_color=color))

def on_click():
    threading.Thread(target=_work_thread, daemon=True).start()

def _work_thread():
    try:
        # heavy work
        set_status("done", "#66bb6a")
    except Exception as e:
        log.error("...: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
```

### Progress bars

`pack(in_=w["progress_frame"], fill="x")` to show, `pack_forget()` to hide. Packing state is the truth — no separate `visible` flag.

### Color palette (reuse, don't invent)

`#141414` bg · `#1e1e1e`/`#2a2a2a` card · `#444444` divider · `#aaaaaa` text · `#4fc3f7` accent · `#66bb6a` success · `#ffa726`/`#ff8f00` warn · `#ff6b6b` error · `#555555` disabled · `#888888` section labels.

### Imports

- Top-of-file: stdlib + third-party.
- **Lazy** imports for heavy/Resolve-touching modules (e.g. `from src.subtitles.elevenlabs import ...` inside the worker function). Keeps tab startup snappy.

### Code style

- `from __future__ import annotations`. PEP 604 unions (`X | None`).
- Type hints on every public function. `Any` only at the CTk boundary or for opaque Resolve objects.
- Module docstrings on every file. Don't nest defs > 2 levels. Extract helpers at 50+ lines.

---

## Critical gotchas

1. **UIManager is gone** (Resolve free v19.1+). Don't try to bring it back — the plugin is a separate desktop app connected via external scripting.
2. **Python ≥ 3.13 segfaults** on `import DaVinciResolveScript`. `main.py` must probe 3.10/3.11/3.12 first.
3. **`scriptapp("Resolve")` blocks**. If Resolve isn't running it can hang 30s+. Always connect on a daemon thread with a timeout — never on the Tk main thread.
4. **Don't import DaVinciResolveScript before Tk** — race on Windows COM init. Order: connect → import ctk → build window → `mainloop()`.
5. **Install path is `Scripts/Utility/`**, not `Scripts/Edit/`. The Edit page gives remote Fusion proxies with no usable methods.
6. **`main.py` must NOT block** the Scripts menu. Always `Popen`, never `run`/`call`/`wait`.
7. **Widget refs live on the parent** (`parent._w = {}` in `build()`). Don't return the dict.

---

## Dev loop

```bash
py -3.12 gui.py    # standalone (works without Resolve — disconnected state)
py -3.12 main.py   # simulate Scripts menu launcher
py -3.12 install.py
```

## Adding a feature

1. New folder `src/<feature>/` (logic, no widgets) + `src/ui/<feature>_tab.py` with `build()` + `setup()`.
2. Register in `src/ui/main_window.py` `_TABS`.
3. Document in `README.md`.

## Adding a dep

Add pinned lower-bound to `requirements.txt` with a comment. Verify on 3.10/3.11/3.12. Lazy-import heavy deps inside the tab's worker.
