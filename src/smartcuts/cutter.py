"""Timeline reconstruction after silence removal.

Strategy: non-destructive new-timeline approach.
  1. For each clip, analyze audio and find non-silent segments.
  2. Express each segment as {mediaPoolItem, startFrame, endFrame}.
  3. Create a new empty timeline and AppendToTimeline() with all segments.

The original timeline is never modified.

Segment extraction lives in cutter_segments.py.
Retake timeline placement lives in cutter_retakes.py.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.timeline_utils import _unique_timeline_name
from src.smartcuts.cutter_segments import _collect_segments
from src.smartcuts.cutter_retakes import _build_timeline_entries, _create_retake_track

log = get_logger(__name__)


@dataclass
class CutResult:
    new_timeline_name: str
    segments_created: int
    time_saved_sec: float
    total_clips_processed: int
    retakes_found: int = 0
    retake_track_index: int = 0  # 0 = no retake track created
    segment_records: list = None  # type: ignore[assignment]  # list[SegmentRecord] for Music/SFX tab


def apply_cuts(
    resolve: Any,
    timeline: Any,
    clips: list[Any],
    threshold_db: float = -35.0,
    min_duration_ms: float = 350.0,
    padding_ms: float = 120.0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    target_timeline: Optional[Any] = None,
    detect_retakes: bool = False,
    existing_retake_track: Optional[int] = None,
    silence_method: str = "vad",
    retake_method: str = "spacy",
    vad_threshold: float = 0.5,
) -> CutResult:
    """Remove silences by building a timeline with only non-silent clip segments.

    Non-destructive when creating a new timeline; appends to target_timeline if provided.

    Args:
        resolve:           DaVinci Resolve object.
        timeline:          Source timeline to process.
        clips:             List of TimelineItem objects (from video track 1).
        threshold_db:      Silence threshold (dBFS).
        min_duration_ms:   Minimum silence duration to remove (ms).
        padding_ms:        Breathing room at each cut edge (ms).
        progress_callback: Optional fn(current, total, message) for UI updates.
        target_timeline:   If set, append clips here instead of creating a new timeline.

    Returns:
        CutResult with stats about the timeline.

    Raises:
        RuntimeError on critical failures.
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()

    try:
        fps = float(project.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        fps = 25.0

    if target_timeline is not None:
        new_name = target_timeline.GetName()
        log.info("Appending to existing timeline: '%s' | FPS: %.2f", new_name, fps)
    else:
        new_name = _unique_timeline_name(project, f"{timeline.GetName()}_cuts")
        log.info("Target new timeline: '%s' | FPS: %.2f", new_name, fps)

    all_segment_records, total_silence_ms, clips_processed = _collect_segments(
        clips, fps, threshold_db, min_duration_ms, padding_ms, progress_callback, silence_method,
        vad_threshold,
    )

    if not all_segment_records:
        raise RuntimeError(
            "No valid clip segments found after silence analysis.\n"
            "Check that the media files are accessible and that ffmpeg is installed."
        )

    retakes_found = 0
    if detect_retakes:
        from src.smartcuts.retake_detector import find_retakes as _find_retakes

        def _retake_progress(msg: str) -> None:
            if progress_callback:
                progress_callback(clips_processed, len(clips), msg)
        try:
            retakes_found = _find_retakes(
                all_segment_records,
                progress_callback=_retake_progress,
                method=retake_method,
            )
        except Exception as e:
            log.error("Retake detection failed: %s — continuing without retake isolation", e)
            retakes_found = 0

    retake_count = sum(1 for s in all_segment_records if s.is_retake)

    if progress_callback:
        progress_callback(len(clips), len(clips), f"Building timeline '{new_name}'...")

    if target_timeline is not None:
        dest_timeline = target_timeline
        project.SetCurrentTimeline(dest_timeline)
        for _ttype in ("video", "audio"):
            try:
                _count = dest_timeline.GetTrackCount(_ttype)
                for _i in range(1, _count + 1):
                    _items = dest_timeline.GetItemListInTrack(_ttype, _i)
                    if _items:
                        dest_timeline.DeleteClips(_items)
            except Exception as _e:
                log.warning("Could not clear %s tracks: %s", _ttype, _e)
    else:
        dest_timeline = media_pool.CreateEmptyTimeline(new_name)
        if dest_timeline is None:
            raise RuntimeError(
                f"DaVinci Resolve could not create timeline '{new_name}'.\n"
                "Check that a project is open and the name is valid."
            )
        project.SetCurrentTimeline(dest_timeline)

    from src.utils.black_clip import get_black_media_item
    black_item: Any | None = None
    if retake_count > 0:
        black_item = get_black_media_item(resolve)

    tl_start = dest_timeline.GetStartFrame()
    track1_entries, retake_placements = _build_timeline_entries(
        all_segment_records, black_item, fps, tl_start,
    )

    result = media_pool.AppendToTimeline(track1_entries)
    if not result:
        raise RuntimeError(
            f"AppendToTimeline returned falsy — timeline '{new_name}' was created but is empty.\n"
            "Try re-analyzing (clip references may be stale)."
        )

    retake_track_index = 0
    if retake_placements:
        retake_track_index = _create_retake_track(
            dest_timeline, retake_placements, media_pool, new_name,
            existing_track_index=existing_retake_track,
        )

    log.info(
        "Created '%s': %d segment(s), %.2fs silence removed from %d clip(s), %d retake(s)",
        new_name,
        len(track1_entries),
        total_silence_ms / 1000.0,
        clips_processed,
        retakes_found,
    )

    return CutResult(
        new_timeline_name=new_name,
        segments_created=len(track1_entries),
        time_saved_sec=total_silence_ms / 1000.0,
        total_clips_processed=clips_processed,
        retakes_found=retakes_found,
        retake_track_index=retake_track_index,
        segment_records=all_segment_records,
    )
