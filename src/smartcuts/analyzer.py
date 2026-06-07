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

    # Peak-normalize so the silence threshold is relative to this clip's loudness.
    # Without this, a quiet speaker falls below the absolute dBFS threshold and gets cut as silence.
    audio = audio.normalize()

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


def detect_silences_vad(
    file_path: str,
    min_duration_ms: float = 350.0,
    padding_ms: float = 120.0,
    vad_threshold: float = 0.5,
) -> list[SilenceRegion]:
    """Detect silent regions using Silero VAD (neural, handles noise/music/quiet speakers).

    Requires: pip install silero-vad onnxruntime

    Raises:
        RuntimeError if silero-vad or onnxruntime is not installed.
        FileNotFoundError if the file doesn't exist.
    """
    try:
        from silero_vad import load_silero_vad, read_audio, get_speech_timestamps  # type: ignore
    except ImportError:
        raise RuntimeError(
            "silero-vad is not installed.\n"
            "Run: pip install silero-vad onnxruntime"
        )

    import tempfile

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    log.debug("detect_silences_vad: %s | min=%.0fms | padding=%.0fms",
              os.path.basename(file_path), min_duration_ms, padding_ms)

    try:
        from pydub import AudioSegment  # type: ignore
    except ImportError:
        raise RuntimeError("pydub is not installed. Run: pip install pydub")

    # Silero requires 16 kHz mono WAV
    audio = AudioSegment.from_file(file_path).set_channels(1).set_frame_rate(16000)
    total_ms = float(len(audio))

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        audio.export(tmp_path, format="wav")

        model = load_silero_vad()
        wav = read_audio(tmp_path)
        speech_ts = get_speech_timestamps(wav, model, threshold=vad_threshold, return_seconds=True)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Invert speech segments → silence gaps
    silence_gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for ts in speech_ts:
        gap_start = cursor
        gap_end = float(ts["start"]) * 1000.0
        if gap_end - gap_start >= min_duration_ms:
            silence_gaps.append((gap_start, gap_end))
        cursor = float(ts["end"]) * 1000.0
    if total_ms - cursor >= min_duration_ms:
        silence_gaps.append((cursor, total_ms))

    regions: list[SilenceRegion] = []
    for raw_start, raw_end in silence_gaps:
        inner_start = raw_start + padding_ms
        inner_end = raw_end - padding_ms
        if inner_start >= inner_end:
            log.debug("VAD silence %d–%d ms consumed by padding, skipping", raw_start, raw_end)
            continue
        inner_start = max(0.0, inner_start)
        inner_end = min(total_ms, inner_end)
        regions.append(SilenceRegion(inner_start, inner_end))

    log.info(
        "VAD found %d silence region(s) in '%s' (total: %.2fs)",
        len(regions),
        os.path.basename(file_path),
        sum(r.duration_ms for r in regions) / 1000.0,
    )
    return regions


def detect_silences_auto(
    file_path: str,
    method: str = "vad",
    threshold_db: float = -35.0,
    min_duration_ms: float = 350.0,
    padding_ms: float = 120.0,
    vad_threshold: float = 0.5,
) -> list[SilenceRegion]:
    """Dispatch to VAD or pydub RMS silence detection.

    Args:
        method: ``"vad"`` for Silero VAD (default), ``"rms"`` for pydub RMS.
        threshold_db: Only used when method is ``"rms"``.
        vad_threshold: Speech probability cutoff (0–1). Only used when method is ``"vad"``.
    """
    if method == "vad":
        return detect_silences_vad(
            file_path,
            min_duration_ms=min_duration_ms,
            padding_ms=padding_ms,
            vad_threshold=vad_threshold,
        )
    return detect_silences(
        file_path,
        threshold_db=threshold_db,
        min_duration_ms=min_duration_ms,
        padding_ms=padding_ms,
    )


def estimate_time_saved(regions: list[SilenceRegion]) -> float:
    """Return total silence duration in seconds."""
    return sum(r.duration_ms for r in regions) / 1000.0
