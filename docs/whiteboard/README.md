# Whiteboard — feature flow maps

Visual flow maps of how each Clautter feature actually works: the steps, the
decision points, and the real thresholds — so you can understand a feature
**without reading the code**.

One `.excalidraw` scene per feature. Each scene is a top-to-bottom flow
(process boxes, decision diamonds, terminal ellipses, green I/O boxes for
external calls) with a yellow **legend panel** on the right listing the
thresholds/constants and their defaults. Box labels carry a `file:line`
back-reference so the diagram is a map *back into* the source.

## How to open

- **excalidraw.com** — open the site, then *Menu ▸ Open* and pick a `.excalidraw` file (it stays local, nothing is uploaded).
- **VS Code** — install the **Excalidraw** extension (`pomdtr.excalidraw-editor`); `.excalidraw` files then open as an editable canvas in the editor.

## Index

| File | Feature |
|---|---|
| [overview.excalidraw](overview.excalidraw) | System: HTTP bridge + cross-feature data flow (transcript → b-roll/graphics/music, cuts → subtitle remap/SFX) |
| [smartcuts.excalidraw](smartcuts.excalidraw) | Smart Cuts — silence removal (VAD→RMS) + retake detection |
| [pace.excalidraw](pace.excalidraw) | Pace Control — slider → preset → Smart Cuts |
| [zooms.excalidraw](zooms.excalidraw) | Auto Zooms — cut-point driven punch-ins |
| [subtitles.excalidraw](subtitles.excalidraw) | Subtitles — STT → format → remap → Fusion titles |
| [broll.excalidraw](broll.excalidraw) | Autonomous B-Roll — keyword → fetch → rank → place |
| [music.excalidraw](music.excalidraw) | Music & SFX — mood music + auto SFX with ducking |
| [graphics.excalidraw](graphics.excalidraw) | Motion Graphics (BETA) — rule-based suggester |

## Regenerating

The scenes are **generated**, not hand-edited — so layout, arrow bindings, and
ids stay consistent and the legends stay in sync with the source. Edit the
builder for a feature in [`_build/builders.py`](_build/builders.py) (each
function mirrors the code's thresholds, cited inline), then:

```bash
py -3.12 docs/whiteboard/_build/gen.py
```

This rewrites all `.excalidraw` files deterministically (re-running with no
source change produces no git diff). The generator core (shape/arrow/legend
helpers, palette, layout) lives in [`_build/gen.py`](_build/gen.py).

> If you tweak a scene by hand in Excalidraw and want to keep it, fold the
> change back into the builder — a regenerate will otherwise overwrite it.
