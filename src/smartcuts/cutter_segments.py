"""Silence-based segment extraction and clip collection for the cutter.

Extracted from cutter.py to keep the main orchestration file under 200 lines.
"""

from __future__ import annotations
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.resolve_api import get_clip_file_path, ms_to_frames
from src.smartcuts.analyzer import SilenceRegion, detect_silences_auto
from src.smartcuts.retake_types import SegmentRecord

log = get_logger(__name__)


def _non_silent_segments(
    clip_source_start_ms: float,
    clip_source_end_ms: float,
    all_silence_regions: list[SilenceRegion],
) -> list[tuple[float, float]]:
    """Return keep-segments (in absolute source ms) for a clip's source range.

    Clips silence regions to the clip's own source window, then inverts them.
    Returns list of (start_ms, end_ms) pairs representing non-silent content.
    """
    clipped: list[SilenceRegion] = []
    for region in all_silence_regions:
        clamped_start = max(region.start_ms, clip_source_start_ms)
        clamped_end = min(region.end_ms, clip_source_end_ms)
        if clamped_end > clamped_start:
            clipped.append(SilenceRegion(clamped_start, clamped_end))

    if not clipped:
        return [(clip_source_start_ms, clip_source_end_ms)]

    clipped.sort(key=lambda r: r.start_ms)

    segments: list[tuple[float, float]] = []
    cursor = clip_source_start_ms

    for silence in clipped:
        if silence.start_ms > cursor + 10:  # 10ms minimum segment to avoid micro-clips
            segments.append((cursor, silence.start_ms))
        cursor = silence.end_ms

    if cursor < clip_source_end_ms - 10:
        segments.append((cursor, clip_source_end_ms))

    return segments


def _collect_segments(
    clips: list[Any],
    fps: float,
    threshold_db: float,
    min_duration_ms: float,
    padding_ms: float,
    progress_callback: Optional[Callable[[int, int, str], None]],
    silence_method: str = "vad",
    vad_threshold: float = 0.5,
) -> tuple[list[SegmentRecord], float, int]:
    """Analyze each clip for silences and build SegmentRecord list.

    Returns:
        (all_segment_records, total_silence_ms, clips_processed)
    """
    all_segment_records: list[SegmentRecord] = []
    total_silence_ms = 0.0
    clips_processed = 0
    total = len(clips)

    for idx, clip in enumerate(clips):
        if progress_callback:
            progress_callback(idx, total, f"Analyzing clip {idx + 1}/{total}...")

        file_path = get_clip_file_path(clip)
        if not file_path:
            log.warning("Clip %d: no file path found, skipping", idx)
            continue

        media_item = clip.GetMediaPoolItem()
        if media_item is None:
            log.warning("Clip %d: no MediaPoolItem, skipping", idx)
            continue

        src_start_frame: int = clip.GetSourceStartFrame()
        src_end_frame: int = clip.GetSourceEndFrame()
        src_start_ms = (src_start_frame / fps) * 1000.0
        src_end_ms = (src_end_frame / fps) * 1000.0

        try:
            all_regions = detect_silences_auto(
                file_path,
                method=silence_method,
                threshold_db=threshold_db,
                min_duration_ms=min_duration_ms,
                padding_ms=padding_ms,
                vad_threshold=vad_threshold,
            )
        except RuntimeError as e:
            if "not installed" in str(e) and silence_method == "vad":
                log.warning("Silero VAD unavailable — falling back to pydub RMS: %s", e)
                try:
                    all_regions = detect_silences_auto(
                        file_path,
                        method="rms",
                        threshold_db=threshold_db,
                        min_duration_ms=min_duration_ms,
                        padding_ms=padding_ms,
                    )
                except Exception as e2:
                    log.error("Clip %d RMS fallback failed (%s): %s — keeping whole clip", idx, file_path, e2)
                    all_regions = []
            else:
                log.error("Clip %d analysis failed (%s): %s — keeping whole clip", idx, file_path, e)
                all_regions = []
        except Exception as e:
            log.error("Clip %d analysis failed (%s): %s — keeping whole clip", idx, file_path, e)
            all_regions = []

        for region in all_regions:
            overlap_start = max(region.start_ms, src_start_ms)
            overlap_end = min(region.end_ms, src_end_ms)
            if overlap_end > overlap_start:
                total_silence_ms += overlap_end - overlap_start

        keep_segments = _non_silent_segments(src_start_ms, src_end_ms, all_regions)
        log.debug("Clip %d: %d keep segment(s) from %d silence(s)", idx, len(keep_segments), len(all_regions))

        for seg_start_ms, seg_end_ms in keep_segments:
            start_frame = ms_to_frames(seg_start_ms, fps)
            end_frame = ms_to_frames(seg_end_ms, fps) - 1
            if end_frame <= start_frame:
                continue
            all_segment_records.append(SegmentRecord(
                clip_idx=idx,
                media_item=media_item,
                file_path=file_path,
                start_ms=seg_start_ms,
                end_ms=seg_end_ms,
                start_frame=start_frame,
                end_frame=end_frame,
            ))

        clips_processed += 1

    return all_segment_records, total_silence_ms, clips_processed
