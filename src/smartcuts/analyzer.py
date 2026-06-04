"""Silence detection using pydub.

Analyzes media files locally — no internet required.
Compatible with DaVinci Resolve free and Studio.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class SilenceRegion:
    """A detected silence region, measured in milliseconds from the start of the audio file."""

    start_ms: float
    end_ms: float

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms

    def __repr__(self) -> str:
        return f"<Silence {self.start_ms:.0f}–{self.end_ms:.0f}ms ({self.duration_ms:.0f}ms)>"


def detect_silences(
    file_path: str,
    threshold_db: float = -35.0,
    min_duration_ms: float = 350.0,
    padding_ms: float = 120.0,
) -> list[SilenceRegion]:
    """Detect silent regions in a media file.

    Args:
        file_path:       Path to any audio or video file (pydub + ffmpeg handle the decoding).
        threshold_db:    Amplitude threshold in dBFS. Audio below this is considered silent.
                         Typical values: -40 (aggressive) to -25 (conservative).
        min_duration_ms: Minimum silence length to detect (milliseconds).
        padding_ms:      Breathing room to leave at each end of the cut (milliseconds).

    Returns:
        Sorted list of SilenceRegion objects. Regions have padding already applied
        (inner boundaries shrunk by padding_ms on each side).

    Raises:
        RuntimeError if pydub is not installed.
        FileNotFoundError if the file doesn't exist.
    """
    try:
        from pydub import AudioSegment  # type: ignore
        from pydub.silence import detect_silence  # type: ignore
    except ImportError:
        raise RuntimeError(
            "pydub is not installed.\n"
            "Run: pip install pydub\n"
            "Also install ffmpeg and make sure it is on your system PATH."
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    log.debug(
        "detect_silences: %s | threshold=%.0fdB | min=%.0fms | padding=%.0fms",
        os.path.basename(file_path),
        threshold_db,
        min_duration_ms,
        padding_ms,
    )

    # Load and convert to mono for analysis (stereo analysis doubles compute for no gain here)
    audio = AudioSegment.from_file(file_path)
    if audio.channels > 1:
        audio = audio.set_channels(1)

    total_ms = len(audio)

    # pydub returns [(start_ms, end_ms), ...]
    raw = detect_silence(
        audio,
        min_silence_len=max(1, int(min_duration_ms)),
        silence_thresh=threshold_db,
        seek_step=10,  # 10ms resolution — fast enough for practical use
    )

    regions: list[SilenceRegion] = []
    for raw_start, raw_end in raw:
        # Apply breathing room (shrink region from both ends)
        inner_start = raw_start + padding_ms
        inner_end = raw_end - padding_ms

        if inner_start >= inner_end:
            log.debug("Silence %d–%d ms consumed by padding, skipping", raw_start, raw_end)
            continue

        # Clamp to audio duration
        inner_start = max(0.0, inner_start)
        inner_end = min(float(total_ms), inner_end)

        regions.append(SilenceRegion(inner_start, inner_end))

    log.info(
        "Found %d silence region(s) in '%s' (total: %.2fs)",
        len(regions),
        os.path.basename(file_path),
        sum(r.duration_ms for r in regions) / 1000.0,
    )
    return regions


def estimate_time_saved(regions: list[SilenceRegion]) -> float:
    """Return total silence duration in seconds."""
    return sum(r.duration_ms for r in regions) / 1000.0
