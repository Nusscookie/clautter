"""Audio loading and analysis helpers using pydub + numpy."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def load_audio(file_path: str) -> Any:
    """Load audio from any media file (video or audio) via pydub.

    Requires ffmpeg on PATH.

    Returns:
        pydub.AudioSegment

    Raises:
        RuntimeError if pydub is missing or file cannot be loaded.
    """
    try:
        from pydub import AudioSegment  # type: ignore
    except ImportError:
        raise RuntimeError(
            "pydub is not installed.\n"
            "Run: pip install pydub\n"
            "Also ensure ffmpeg is installed and on your PATH."
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    try:
        audio = AudioSegment.from_file(str(path))
        log.debug(
            "Loaded audio: %s | %.1fs | %dch | %dHz",
            path.name,
            len(audio) / 1000.0,
            audio.channels,
            audio.frame_rate,
        )
        return audio
    except Exception as e:
        raise RuntimeError(f"Failed to load audio from '{path.name}': {e}") from e


def audio_to_mono(audio: Any) -> Any:
    """Convert AudioSegment to mono."""
    if audio.channels > 1:
        return audio.set_channels(1)
    return audio


def compute_rms_windows(audio: Any, window_ms: int = 100) -> list[float]:
    """Compute RMS (dBFS) per window across the audio.

    Returns list of dBFS values, one per window_ms interval.
    """
    results: list[float] = []
    total_ms = len(audio)
    for start in range(0, total_ms - window_ms + 1, window_ms):
        chunk = audio[start : start + window_ms]
        results.append(chunk.dBFS)
    return results


def find_volume_peaks(
    rms_values: list[float],
    window_ms: int = 100,
    sigma_multiplier: float = 1.0,
) -> list[tuple[float, float]]:
    """Find time positions (ms) of volume peaks above mean + sigma.

    Returns list of (start_ms, peak_dbfs) tuples.
    """
    try:
        import numpy as np  # type: ignore
    except ImportError:
        raise RuntimeError("numpy not installed. Run: pip install numpy")

    if not rms_values:
        return []

    arr = np.array(rms_values)
    # Exclude -inf values (complete silence) from stats
    valid = arr[arr > -80]
    if len(valid) == 0:
        return []

    threshold = float(valid.mean() + sigma_multiplier * valid.std())

    peaks = []
    for i, val in enumerate(rms_values):
        if val >= threshold:
            time_ms = i * window_ms
            peaks.append((float(time_ms), float(val)))

    return peaks


def extract_cut_audio(clips: list, tmp_dir: str, fps: float) -> str | None:
    """ffmpeg-extract kept audio from timeline clips and concatenate into one WAV.

    Returns path to the WAV (inside tmp_dir) or None if extraction fails.
    The caller is responsible for cleaning up tmp_dir.
    """
    import subprocess
    from src.utils.resolve_api import get_clip_file_path

    segments: list[str] = []
    for i, clip in enumerate(clips):
        try:
            src = get_clip_file_path(clip)
            if not src or not os.path.exists(src):
                continue
            start_s = clip.GetSourceStartFrame() / fps
            end_s   = clip.GetSourceEndFrame()   / fps
            dur     = end_s - start_s
            if dur < 0.05:
                continue
            seg = os.path.join(tmp_dir, f"seg_{i:04d}.wav")
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", src, "-ss", str(start_s), "-t", str(dur),
                 "-vn", "-ac", "1", "-ar", "16000", seg],
                capture_output=True, timeout=120,
            )
            if r.returncode == 0:
                segments.append(seg)
            else:
                log.debug("ffmpeg seg %d: %s", i, r.stderr.decode(errors="replace")[:200])
        except Exception as _e:
            log.debug("extract_cut_audio clip %d: %s", i, _e)

    if not segments:
        return None
    if len(segments) == 1:
        return segments[0]

    lst = os.path.join(tmp_dir, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segments:
            f.write(f"file '{s.replace(chr(92), '/')}'\n")
    out = os.path.join(tmp_dir, "cut_audio.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", lst, out],
        capture_output=True, timeout=120,
    )
    if r.returncode == 0:
        return out
    log.warning("extract_cut_audio concat failed — using first segment only")
    return segments[0]
