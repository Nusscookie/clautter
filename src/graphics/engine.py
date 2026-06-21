"""Motion graphics pipeline orchestrator.

Runs the full pipeline:
  1. Node.js check
  2. Transcript guard
  3. Fetch Hyperframes catalog
  4. Scan reference-assets folder (optional)
  5. LLM analyzes transcript → placement decisions
  6. Render each placement to MOV/WebM with alpha + place on timeline

All heavy work runs on a worker thread (caller's responsibility).
Call run() from a threading.Thread; it accepts a progress_callback(step, total)
and a status_callback(message) for UI updates.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from src.constants import SETTINGS_KEYS
from src.utils.logger import get_logger

log = get_logger(__name__)


def run(
    app: Any,
    provider: str | None = None,
    user_instructions: str | None = None,
    status_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    overflow_resolver: Callable[[list, float], list | None] | None = None,
) -> tuple[int, str]:
    """Execute the full motion graphics pipeline.

    Args:
        app:               AIEditorApp instance (needs .transcript, .resolve, .timeline, .settings).
        provider:          LLM provider name or None (auto-select from available keys).
        user_instructions: Optional free-text guidance from the user, forwarded to the LLM.
        status_cb:         Called with human-readable status strings during execution.
        progress_cb:       Called with (current_step, total_steps) for progress bar.

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
    blocks = list_blocks(force_refresh=False)
    if not blocks:
        return 0, (
            "Could not load Hyperframes catalog. "
            "Check your internet connection and Node.js installation."
        )
    # Pass the full catalog to the LLM — it decides suitability based on
    # transcript + user instructions. (Only restriction is the GPU-renderer
    # note baked into the LLM prompt; see llm_director._build_prompt.)
    status(f"Catalog loaded: {len(blocks)} blocks available.")
    block_by_name = {b["name"]: b for b in blocks if b.get("name")}

    project_name = ""
    try:
        project_name = app.project.GetName() if app.project else ""
    except Exception:
        pass

    timeline_dims: tuple[int, int] | None = None
    try:
        if app.timeline:
            tl_w = int(app.timeline.GetSetting("timelineResolutionWidth") or 0)
            tl_h = int(app.timeline.GetSetting("timelineResolutionHeight") or 0)
            if tl_w > 0 and tl_h > 0:
                timeline_dims = (tl_w, tl_h)
                log.info("[gfx_engine] timeline dims: %dx%d", tl_w, tl_h)
    except Exception as e:
        log.debug("[gfx_engine] could not read timeline dims: %s", e)

    timeline_duration_sec: float | None = None
    try:
        if app.timeline:
            _fps_str = str(app.timeline.GetSetting("timelineFrameRate") or "")
            _fps = float(_fps_str) if _fps_str else 25.0
            _tl_start = app.timeline.GetStartFrame()
            _tl_end   = app.timeline.GetEndFrame()
            timeline_duration_sec = max(0.0, (_tl_end - _tl_start) / _fps)
            log.info("[gfx_engine] timeline duration: %.2fs", timeline_duration_sec)
    except Exception as e:
        log.debug("[gfx_engine] could not read timeline duration: %s", e)

    # ── 4. Reference assets ───────────────────────────────────────────
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
    ref_folder: Path | None = None
    ref_assets: list[str] = []
    ref_folder_str = str(app.settings.get(SETTINGS_KEYS.GRAPHICS_REF_FOLDER, "") or "").strip()
    if ref_folder_str:
        _rf = Path(ref_folder_str)
        if _rf.is_dir():
            ref_folder = _rf
            ref_assets = sorted(
                f.name for f in _rf.iterdir()
                if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
            )
            log.info("[gfx_engine] reference assets folder: %s (%d file(s))", _rf, len(ref_assets))
        else:
            log.warning("[gfx_engine] graphics_ref_folder not a directory: %r", ref_folder_str)

    # ── 5. LLM analysis ───────────────────────────────────────────────
    status("Analyzing transcript with LLM…")
    from src.graphics.llm_director import analyze
    placements, err = analyze(
        app.transcript, blocks, app.settings,
        provider=provider, timeline_dims=timeline_dims,
        user_instructions=user_instructions,
        ref_assets=ref_assets or None,
    )
    if err:
        return 0, err
    if not placements:
        return 0, "LLM returned no placements. Try a different provider or check the transcript."

    status(f"LLM selected {len(placements)} graphic(s). Rendering…")

    # ── 5b. Overflow guard ────────────────────────────────────────────────
    if timeline_duration_sec is not None and overflow_resolver is not None:
        if any(p.start_sec + p.duration_sec > timeline_duration_sec for p in placements):
            status("Some graphics overflow timeline — waiting for user choice…")
            resolved = overflow_resolver(placements, timeline_duration_sec)
            if resolved is None:
                return 0, "Cancelled: motion graphics would overflow the timeline."
            placements = resolved

    total = len(placements)
    progress(0, total)

    # ── 6. Render + place each ────────────────────────────────────────
    from src.graphics.renderer import render_placement
    from src.graphics.placer import place

    placed_count = 0
    for i, p in enumerate(placements):
        status(f"Rendering {p.block} ({i + 1}/{total})…")
        mp4 = render_placement(
            p, project_name,
            block_meta=block_by_name.get(p.block),
            settings=app.settings,
            timeline_dims=timeline_dims,
            ref_folder=ref_folder,
            provider=provider,
            user_instructions=user_instructions,
        )
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
