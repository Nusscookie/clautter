"""Motion graphics pipeline orchestrator.

Runs the full pipeline:
  1. Node.js check
  2. Fetch Hyperframes catalog
  3. LLM analyzes transcript → placement decisions
  4. Render each placement to MP4
  5. Import + place on Resolve timeline

All heavy work runs on a worker thread (caller's responsibility).
Call run() from a threading.Thread; it accepts a progress_callback(step, total)
and a status_callback(message) for UI updates.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def run(
    app: Any,
    provider: str | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[int, str]:
    """Execute the full motion graphics pipeline.

    Args:
        app:         AIEditorApp instance (needs .transcript, .resolve, .timeline, .settings).
        provider:    LLM provider name or None (auto-select from available keys).
        status_cb:   Called with human-readable status strings during execution.
        progress_cb: Called with (current_step, total_steps) for progress bar.

    Returns:
        (placed_count, error_str). error_str is "" on full success.
        placed_count may be > 0 even if some placements failed.
    """
    def status(msg: str) -> None:
        log.info("[gfx_engine] %s", msg)
        if status_cb:
            status_cb(msg)

    def progress(current: int, total: int) -> None:
        if progress_cb:
            progress_cb(current, total)

    # ── 1. Node.js check ──────────────────────────────────────────────
    from src.graphics.node_check import check_node
    ok, node_msg = check_node()
    if not ok:
        return 0, node_msg

    status(f"Node.js {node_msg} detected.")

    # ── 2. Transcript guard ───────────────────────────────────────────
    if not app.transcript:
        return 0, "No transcript available. Generate one in the Subtitles tab first."

    # ── 3. Catalog ────────────────────────────────────────────────────
    status("Loading Hyperframes catalog…")
    from src.graphics.catalog_client import list_blocks
    blocks = list_blocks()
    if not blocks:
        return 0, (
            "Could not load Hyperframes catalog. "
            "Check your internet connection and Node.js installation."
        )
    status(f"Catalog loaded: {len(blocks)} blocks available.")

    # ── 4. LLM analysis ───────────────────────────────────────────────
    status("Analyzing transcript with LLM…")
    from src.graphics.llm_director import analyze
    placements, err = analyze(app.transcript, blocks, app.settings, provider=provider)
    if err:
        return 0, err
    if not placements:
        return 0, "LLM found no suitable motion graphics for this transcript."

    status(f"LLM selected {len(placements)} graphic(s). Rendering…")
    total = len(placements)
    progress(0, total)

    # ── 5. Render + place each ────────────────────────────────────────
    from src.graphics.renderer import render_placement
    from src.graphics.placer import place

    project_name = ""
    try:
        project_name = app.project.GetName() if app.project else ""
    except Exception:
        pass

    placed_count = 0
    for i, p in enumerate(placements):
        status(f"Rendering {p.block} ({i + 1}/{total})…")
        mp4 = render_placement(p, project_name)
        if mp4 is None:
            log.warning("[gfx_engine] render failed for %r — skipping", p.block)
            progress(i + 1, total)
            continue

        status(f"Placing {p.block} on timeline at {p.start_sec:.1f}s…")
        if not app.resolve or not app.timeline:
            log.warning("[gfx_engine] no resolve/timeline — cannot place %r", p.block)
            progress(i + 1, total)
            continue

        ok = place(mp4, p, app.resolve, app.timeline)
        if ok:
            placed_count += 1
        progress(i + 1, total)

    if placed_count == 0:
        return 0, "Rendering or placement failed for all graphics. Check logs for details."

    return placed_count, ""
