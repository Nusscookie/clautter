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

The GUI subprocess only needs `customtkinter`. The bridge server runs
inside Resolve's process, so it uses Resolve's own Python (which has
`DaVinciResolveScript` available). The sanity check above is still
useful for verifying that the system Python 3.12 is sane; if you
want to test the bridge end-to-end you also need `requests` in the
subprocess's Python (already in `requirements.txt`).

---

## Architecture (two-process via HTTP bridge — do not collapse)

```
DaVinci Resolve → main.py (Resolve-side launcher, no UI)
                     ├─ acquires _G.resolve (or scriptapp fallback)
                     ├─ starts src/utils/rpc_server.py in a daemon thread
                     │     └─ http://127.0.0.1:<random>  +  writes ~/.clutter/bridge.json
                     └─ subprocess.Popen(system_python, gui.py)  [then .wait()s]
                          └─ gui.py (standalone CTk window)
                               └─ src/utils/rpc_client.py reads bridge.json
                                    └─ src/utils/resolve_api.connect() returns a ResolveProxy
                                         └─ src/app.py stores it as self.resolve
                                              └─ feature modules (unchanged) use it
```

The HTTP bridge exists because **DaVinci Resolve free** disables external
scripting — `DaVinciResolveScript.scriptapp("Resolve")` returns `None` from
any process outside Resolve itself. By running the server inside Resolve's
process, the live `resolve` object is reachable via
`getattr(builtins, "resolve", None)`, and the spawned `gui.py` subprocess
talks to it through a localhost proxy that looks identical to a real
`resolve` object to all downstream code.

| File | Role |
|---|---|
| `main.py` | Resolve-side launcher. Acquires `_G.resolve`, starts `rpc_server`, spawns `gui.py`, then **blocks** on `proc.wait()` so the daemon thread stays alive. |
| `gui.py` | CTk window. Connects to the bridge on startup. **Connect runs on a daemon thread with a 5s timeout** so the UI opens even without Resolve. |
| `src/utils/rpc_server.py` | Local HTTP server in Resolve's process. POST `/call` proxies method calls; `/ping` for liveness. Tracks object refs by uuid. |
| `src/utils/rpc_client.py` | `ResolveProxy` (duck-typed Resolve object) + `ResolveHTTP` (requests.Session). `read_bridge_file()` reads `~/.clutter/bridge.json`. |
| `src/utils/resolve_api.py` | `connect()` tries strategies in order: injected obj → bridge → scriptapp → builtins. Returns either a real `resolve` or a `ResolveProxy` — same shape to callers. |
| `src/app.py` | `AIEditorApp` — framework-agnostic, no tkinter import. Holds `resolve`, `project`, `timeline`, `transcript`, `settings`. |
| `src/<feature>/*` | Pure logic. No widgets. Only uses `app.resolve`, `app.project`, etc. Works unchanged through the proxy. |
| `src/ui/<tab>.py` | Each tab has two functions: `build(parent)` (layout) and `setup(parent, app)` (callbacks). Widget refs live in `parent._w = {}`. |
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

## Reference: AutoSubs (working free-edition Resolve script)

AutoSubs (tmoroney/auto-subs) is installed alongside Clutter at:

```
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\AutoSubs\
```

It is a working example of a DaVinci Resolve script that runs in the **free edition**. It works because it runs inside Resolve's process (Scripts menu), where `resolve` is available as a module global — the same mechanism Clutter's `main.py` uses. Consult it when debugging in-Resolve scripting behaviour or verifying a Resolve API call.

---

## Critical gotchas

1. **UIManager is gone** (Resolve free v19.1+). Don't try to bring it back — the plugin is a separate desktop app connected through the HTTP bridge.
2. **External scripting is gone in free** (Resolve free v19.1+). `scriptapp("Resolve")` from outside Resolve returns `None`. This is why the bridge exists — the server runs INSIDE Resolve's process and proxies method calls over localhost.
3. **Python ≥ 3.13 segfaults** on `import DaVinciResolveScript`. The GUI subprocess doesn't need it (only the bridge does, and the bridge runs in Resolve's own Python), but the sanity check above is still a good idea.
4. **`main.py` blocks** on `proc.wait()` after spawning `gui.py`. The bridge daemon thread is bound to this process; if `main.py` returned, the thread would die and the GUI would lose its connection. The Scripts entry stays "busy" while the GUI is open — this is intentional.
5. **Don't import DaVinciResolveScript before Tk** — race on Windows COM init. Order: connect → import ctk → build window → `mainloop()`. The bridge handles connection on a daemon thread with a 5s timeout, so the UI opens even without Resolve.
6. **Install path is `Scripts/Utility/`**, not `Scripts/Edit/`. The Edit page gives remote Fusion proxies with no usable methods.
7. **Widget refs live on the parent** (`parent._w = {}` in `build()`). Don't return the dict.
8. **`resolve` is in module globals, not builtins.** Resolve injects `resolve` into the running script's module namespace. Use `globals().get("resolve")` in `_acquire_resolve()` — `getattr(builtins, "resolve", None)` will always return `None` in free edition.

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
