"""Audio enhancement processing — decode a clip, run the engine chain, export.

Pure logic: no Resolve, no widgets. Decodes any source clip to a working WAV
via pydub (same decode path as ``src.smartcuts.analyzer``), then runs each
selected engine in chain order, piping each engine's output into the next.
Final cleaned WAV lands in ``PATHS.AUDIO_ENHANCE_CACHE``.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from src.constants import PATHS
from src.enhance_audio import engines
from src.utils.logger import get_logger

log = get_logger(__name__)


def _cache_dir() -> Path:
    PATHS.AUDIO_ENHANCE_CACHE.mkdir(parents=True, exist_ok=True)
    return PATHS.AUDIO_ENHANCE_CACHE


def _out_name(in_path: str, engine_ids: list[str], strength: float) -> str:
    """Deterministic output filename keyed on source + chain + strength."""
    key = f"{in_path}|{'+'.join(engine_ids)}|{strength:.2f}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    stem = Path(in_path).stem
    return f"{stem}_enhanced_{digest}.wav"


def enhance_clip(
    in_path: str,
    engine_ids: list[str],
    strength: float = 0.5,
) -> str:
    """Run the engine chain on a clip's source media; return the cleaned WAV path.

    Args:
        in_path:    Absolute path to the source media (audio or video).
        engine_ids: Engine ids to run, resolved to canonical chain order.
        strength:   0.0–1.0 enhancement strength, passed to each engine.

    Returns:
        Path to the cleaned WAV in the enhance cache.

    Raises:
        FileNotFoundError: source missing.
        ValueError:        no valid engines selected.
        RuntimeError:      an engine failed (re-raised with engine id).
    """
    if not os.path.exists(in_path):
        raise FileNotFoundError(f"Source media not found: {in_path}")

    specs = engines.ordered(engine_ids)
    if not specs:
        raise ValueError(f"No valid engines in {engine_ids!r}")

    out_path = _cache_dir() / _out_name(in_path, [s.id for s in specs], strength)
    if out_path.exists():
        log.info("[enhance] cache hit: %s", out_path)
        return str(out_path)

    # Decode source → 48 kHz mono WAV working copy (engines expect a real WAV).
    from pydub import AudioSegment  # type: ignore

    work_dir = _cache_dir()
    current = work_dir / f".work_{out_path.stem}_src.wav"
    AudioSegment.from_file(in_path).set_channels(1).set_frame_rate(48000).export(
        str(current), format="wav"
    )

    tmp_files: list[Path] = [current]
    try:
        for i, spec in enumerate(specs):
            is_last = i == len(specs) - 1
            stage_out = out_path if is_last else work_dir / f".work_{out_path.stem}_{spec.id}.wav"
            log.info("[enhance] stage %d/%d: %s", i + 1, len(specs), spec.id)
            try:
                spec.run(str(current), str(stage_out), strength)
            except Exception as e:
                raise RuntimeError(f"engine '{spec.id}' failed: {e}") from e
            current = stage_out
            if not is_last:
                tmp_files.append(stage_out)
    finally:
        for f in tmp_files:
            try:
                if f.exists() and f != out_path:
                    f.unlink()
            except OSError:
                pass

    log.info("[enhance] done: %s", out_path)
    return str(out_path)
