"""Timeline reconstruction after silence removal.

Strategy: non-destructive new-timeline approach.
  1. For each clip, analyze audio and find non-silent segments.
  2. Express each segment as {mediaPoolItem, startFrame, endFrame}.
  3. Create a new empty timeline and AppendToTimeline() with all segments.

The original timeline is never modified.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.resolve_api import get_clip_file_path, ms_to_frames
from src.smartcuts.analyzer import SilenceRegion, detect_silences

log = get_logger(__name__)


@dataclass
class CutResult:
    new_timeline_name: str
    segments_created: int
    time_saved_sec: float
    total_clips_processed: int


def _non_silent_segments(
    clip_source_start_ms: float,
    clip_source_end_ms: float,
    all_silence_regions: list[SilenceRegion],
) -> list[tuple[float, float]]:
    """Return keep-segments (in absolute source ms) for a clip's source range.

    Clips silence regions to the clip's own source window, then inverts them.
    Returns list of (start_ms, end_ms) pairs representing non-silent content.
    """
    # Filter and clamp silence regions to this clip's window
    clipped: list[SilenceRegion] = []
    for region in all_silence_regions:
        clamped_start = max(region.start_ms, clip_source_start_ms)
        clamped_end = min(region.end_ms, clip_source_end_ms)
        if clamped_end > clamped_start:
            clipped.append(SilenceRegion(clamped_start, clamped_end))

    if not clipped:
        # No silences in this clip — keep everything
        return [(clip_source_start_ms, clip_source_end_ms)]

    clipped.sort(key=lambda r: r.start_ms)

    segments: list[tuple[float, float]] = []
    cursor = clip_source_start_ms

    for silence in clipped:
        if silence.start_ms > cursor + 10:  # 10ms minimum segment to avoid micro-clips
            segments.append((cursor, silence.start_ms))
        cursor = silence.end_ms

    # Trailing content after last silence
    if cursor < clip_source_end_ms - 10:
        segments.append((cursor, clip_source_end_ms))

    return segments


def _unique_timeline_name(project: Any, base_name: str) -> str:
    """Return a name that does not collide with existing timelines."""
    try:
        count = project.GetTimelineCount()
        existing = {
            project.GetTimelineByIndex(i + 1).GetName()
            for i in range(count)
        }
    except Exception:
        existing = set()

    name = base_name
    i = 2
    while name in existing:
        name = f"{base_name}_{i}"
        i += 1
    return name


def apply_cuts(
    resolve: Any,
    timeline: Any,
    clips: list[Any],
    threshold_db: float = -35.0,
    min_duration_ms: float = 350.0,
    padding_ms: float = 120.0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> CutResult:
    """Remove silences by building a new timeline with only non-silent clip segments.

    Non-destructive: the original timeline and all source media are untouched.

    Args:
        resolve:           DaVinci Resolve object.
        timeline:          Source timeline to process.
        clips:             List of TimelineItem objects (from video track 1).
        threshold_db:      Silence threshold (dBFS).
        min_duration_ms:   Minimum silence duration to remove (ms).
        padding_ms:        Breathing room at each cut edge (ms).
        progress_callback: Optional fn(current, total, message) for UI updates.

    Returns:
        CutResult with stats about the new timeline.

    Raises:
        RuntimeError on critical failures.
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()

    try:
        fps = float(project.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        fps = 25.0

    new_name = _unique_timeline_name(project, f"{timeline.GetName()}_cuts")
    log.info("Target new timeline: '%s' | FPS: %.2f", new_name, fps)

    clip_infos: list[dict] = []
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

        # Source frame range this clip uses
        src_start_frame: int = clip.GetSourceStartFrame()
        src_end_frame: int = clip.GetSourceEndFrame()

        src_start_ms = (src_start_frame / fps) * 1000.0
        src_end_ms = (src_end_frame / fps) * 1000.0

        # Analyze the full source file; silence positions are absolute from file start
        try:
            all_regions = detect_silences(
                file_path,
                threshold_db=threshold_db,
                min_duration_ms=min_duration_ms,
                padding_ms=padding_ms,
            )
        except Exception as e:
            log.error("Clip %d analysis failed (%s): %s — keeping whole clip", idx, file_path, e)
            all_regions = []

        # Accumulate silence for stats (only within this clip's window)
        for region in all_regions:
            overlap_start = max(region.start_ms, src_start_ms)
            overlap_end = min(region.end_ms, src_end_ms)
            if overlap_end > overlap_start:
                total_silence_ms += overlap_end - overlap_start

        # Get non-silent source windows
        keep_segments = _non_silent_segments(src_start_ms, src_end_ms, all_regions)
        log.debug("Clip %d: %d keep segment(s) from %d silence(s)", idx, len(keep_segments), len(all_regions))

        for seg_start_ms, seg_end_ms in keep_segments:
            start_frame = ms_to_frames(seg_start_ms, fps)
            end_frame = ms_to_frames(seg_end_ms, fps) - 1

            if end_frame <= start_frame:
                continue

            clip_infos.append({
                "mediaPoolItem": media_item,
                "startFrame": start_frame,
                "endFrame": end_frame,
                "mediaType": 1,  # 1 = video + audio
            })

        clips_processed += 1

    if not clip_infos:
        raise RuntimeError(
            "No valid clip segments found after silence analysis.\n"
            "Check that the media files are accessible and that ffmpeg is installed."
        )

    if progress_callback:
        progress_callback(total, total, f"Creating timeline '{new_name}'...")

    # Create the new timeline
    new_timeline = media_pool.CreateEmptyTimeline(new_name)
    if new_timeline is None:
        raise RuntimeError(
            f"DaVinci Resolve could not create timeline '{new_name}'.\n"
            "Check that a project is open and the name is valid."
        )

    # Switch to new timeline so AppendToTimeline targets it
    project.SetCurrentTimeline(new_timeline)

    result = media_pool.AppendToTimeline(clip_infos)
    if not result:
        log.warning(
            "AppendToTimeline returned falsy — timeline '%s' may be incomplete.", new_name
        )

    log.info(
        "Created '%s': %d segment(s), %.2fs silence removed from %d clip(s)",
        new_name,
        len(clip_infos),
        total_silence_ms / 1000.0,
        clips_processed,
    )

    return CutResult(
        new_timeline_name=new_name,
        segments_created=len(clip_infos),
        time_saved_sec=total_silence_ms / 1000.0,
        total_clips_processed=clips_processed,
    )
