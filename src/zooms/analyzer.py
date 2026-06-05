"""Zoom point detection based on audio volume peaks.

Identifies high-energy moments where a zoom cut improves viewer retention.
Works on the audio track of any video file.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field

from src.utils.logger import get_logger

log = get_logger(__name__)

_WINDOW_MS = 100       # RMS window size in ms
_ZOOM_DURATION_MS = 2500  # Default zoom region length (ms)


@dataclass
class ZoomPoint:
    """A detected moment where a zoom cut is recommended."""

    timeline_frame: int      # Frame number on the main timeline
    duration_frames: int     # How long the zoom region lasts
    zoom_amount: float       # e.g. 1.15 = 115%
    energy_dbfs: float = 0.0 # RMS energy that triggered detection (debug info)

    def __repr__(self) -> str:
        return (
            f"<ZoomPoint frame={self.timeline_frame} "
            f"dur={self.duration_frames}fr zoom={self.zoom_amount:.2f}>"
        )


def detect_zoom_points(
    file_path: str,
    clip_start_frame: int = 0,
    src_start_frame: int = 0,
    src_end_frame: int = -1,
    fps: float = 25.0,
    max_per_minute: int = 4,
    sigma_multiplier: float = 1.0,
    zoom_amount: float = 1.15,
    zoom_duration_ms: float = _ZOOM_DURATION_MS,
) -> list[ZoomPoint]:
    """Detect high-energy moments for zoom cuts.

    Args:
        file_path:        Source media file path.
        clip_start_frame: Timeline frame at which this clip starts (offset applied to results).
        fps:              Timeline frame rate.
        max_per_minute:   Maximum zoom points per minute of audio.
        sigma_multiplier: How many standard deviations above mean to threshold.
                          Lower = more zooms, Higher = fewer, only very loud moments.
        zoom_amount:      Zoom scale factor (1.15 = 115%).
        zoom_duration_ms: Duration of each zoom region in ms.

    Returns:
        List of ZoomPoint objects sorted by timeline_frame.
    """
    from src.utils.audio import load_audio, audio_to_mono, compute_rms_windows, find_volume_peaks

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    log.debug(
        "detect_zoom_points: %s | max=%d/min | sigma=%.1f | zoom=%.2f",
        os.path.basename(file_path),
        max_per_minute,
        sigma_multiplier,
        zoom_amount,
    )

    audio = load_audio(file_path)
    audio = audio_to_mono(audio)
    duration_sec = len(audio) / 1000.0

    rms_windows = compute_rms_windows(audio, window_ms=_WINDOW_MS)
    if not rms_windows:
        return []

    peak_times = find_volume_peaks(rms_windows, window_ms=_WINDOW_MS,
                                   sigma_multiplier=sigma_multiplier)

    if not peak_times:
        log.info("No peaks above threshold in '%s'", os.path.basename(file_path))
        return []

    # Source window in ms — filter peaks to only the portion this clip uses
    src_start_ms = (src_start_frame / fps) * 1000.0
    src_end_ms = (src_end_frame / fps) * 1000.0 if src_end_frame >= 0 else float("inf")

    # Min spacing between zooms to enforce max_per_minute
    min_spacing_ms = (60_000.0 / max(max_per_minute, 1)) if max_per_minute > 0 else 99_999.0
    zoom_dur_frames = max(1, int((zoom_duration_ms / 1000.0) * fps))

    points: list[ZoomPoint] = []
    last_accepted_ms = -min_spacing_ms  # Allow first point immediately

    for peak_ms, peak_dbfs in sorted(peak_times, key=lambda x: x[0]):
        if not (src_start_ms <= peak_ms < src_end_ms):
            continue
        if peak_ms - last_accepted_ms < min_spacing_ms:
            continue

        timeline_frame = clip_start_frame + int(((peak_ms - src_start_ms) / 1000.0) * fps)

        points.append(ZoomPoint(
            timeline_frame=timeline_frame,
            duration_frames=zoom_dur_frames,
            zoom_amount=zoom_amount,
            energy_dbfs=peak_dbfs,
        ))
        last_accepted_ms = peak_ms

    log.info(
        "Found %d zoom point(s) in '%s' (%.1fs)",
        len(points),
        os.path.basename(file_path),
        duration_sec,
    )
    return points
