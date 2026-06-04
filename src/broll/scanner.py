"""B-Roll folder scanner — collects clip metadata from a directory."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mxf",
    ".m4v", ".wmv", ".flv", ".webm", ".ts",
}


def scan_folder(folder: str) -> list[dict]:
    """Scan a folder recursively for video files.

    Args:
        folder: Path to the directory containing B-roll clips.

    Returns:
        List of clip dicts: {name, path, extension, size_mb, duration_sec}.
        duration_sec is 0.0 if not determinable without heavy deps.
    """
    root = Path(folder)
    if not root.exists():
        raise FileNotFoundError(f"B-roll folder not found: {folder}")
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {folder}")

    clips: list[dict] = []

    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in _VIDEO_EXTENSIONS:
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0

        # Extract descriptive keywords from the filename (strip extension, split on separators)
        stem = path.stem
        keywords = _extract_keywords(stem)

        clips.append({
            "name": path.name,
            "path": str(path),
            "extension": path.suffix.lower(),
            "size_mb": size_bytes / 1e6,
            "duration_sec": _get_duration(path),
            "keywords": keywords,
        })

    log.info("Scanned %d B-roll clip(s) in '%s'", len(clips), folder)
    return clips


def _extract_keywords(stem: str) -> list[str]:
    """Extract lowercase keywords from a filename stem."""
    import re
    # Split on underscores, hyphens, spaces, and camelCase boundaries
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", stem)
    words = re.split(r"[_\-\s]+", words)
    return [w.lower().strip() for w in words if len(w) > 2]


def _get_duration(path: Path) -> float:
    """Try to get video duration using pydub. Returns 0.0 if unavailable."""
    try:
        from pydub import AudioSegment  # type: ignore
        audio = AudioSegment.from_file(str(path))
        return len(audio) / 1000.0
    except Exception:
        return 0.0
