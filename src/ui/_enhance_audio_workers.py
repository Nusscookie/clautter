"""Background worker for the Enhance Audio tab.

Installs any selected optional engines (if confirmed), then runs the
enhancement + placement pipeline. All UI updates route through the ``_ui``
helper (frame.after(0, ...)) per CLAUDE.md threading rules.
"""

from __future__ import annotations

from typing import Any, Callable

from src.constants import COLORS
from src.enhance_audio import dep_installer, engines, placer
from src.utils.logger import get_logger

log = get_logger(__name__)


def worker_thread(
    *,
    frame: Any,
    app: Any,
    state: dict[str, Any],
    engine_ids: list[str],
    strength: float,
    scope: str,
    install_pkgs: list[str],
    set_status: Callable[..., None],
    set_progress: Callable[..., None],
    _ui: Callable[[Any], None],
    w: dict[str, Any],
) -> None:
    """Install missing engines, then enhance + place. Re-enables the button."""
    try:
        # ── 1. Install any confirmed optional deps ──────────────────
        for pkg in install_pkgs:
            set_status(f"Installing {pkg} … (CPU-heavy, may take a while)", COLORS.WARNING)
            ok = dep_installer.install(pkg, log_cb=lambda ln: set_status(ln[:120], COLORS.TEXT_MUTED))
            if not ok:
                set_status(f"Install of {pkg} failed — check the console/log.", COLORS.ERROR)
                return

        # ── 2. Verify every selected engine is importable ───────────
        for eid in engine_ids:
            spec = engines.get_engine(eid)
            if spec and not dep_installer.is_installed(spec.import_name):
                set_status(f"Engine '{spec.label}' not installed.", COLORS.ERROR)
                return

        # ── 3. Run pipeline ─────────────────────────────────────────
        set_progress(0, visible=True)
        set_status("Enhancing…", COLORS.TEXT_MUTED)

        def _progress(done: int, total: int, msg: str) -> None:
            pct = int((done / total) * 100) if total else 0
            set_progress(pct, visible=True)
            set_status(msg, COLORS.TEXT_MUTED)

        results, summary = placer.enhance_timeline(
            app, engine_ids=engine_ids, strength=strength, scope=scope,
            mute_original=True, progress=_progress,
        )

        any_placed = any(r.placed for r in results)
        color = COLORS.SUCCESS if any_placed else COLORS.ERROR
        if results and any_placed and not all(r.placed for r in results):
            color = COLORS.WARN_PARTIAL
        set_status(summary, color)

    except Exception as e:
        log.error("[enhance] worker failed: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
    finally:
        set_progress(0, visible=False)
        state["running"] = False
        _ui(lambda: w["run_btn"].configure(state="normal"))
