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
    retakes_found: int = 0
    retake_track_index: int = 0  # 0 = no retake track created


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
    target_timeline: Optional[Any] = None,
    detect_retakes: bool = False,
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

    from src.smartcuts.retake_detector import SegmentRecord, find_retakes as _find_retakes

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

    if not all_segment_records:
        raise RuntimeError(
            "No valid clip segments found after silence analysis.\n"
            "Check that the media files are accessible and that ffmpeg is installed."
        )

    # Retake detection — tags each SegmentRecord.is_retake in-place
    retakes_found = 0
    if detect_retakes:
        def _retake_progress(msg: str) -> None:
            if progress_callback:
                progress_callback(clips_processed, total, msg)
        try:
            retakes_found = _find_retakes(all_segment_records, progress_callback=_retake_progress)
        except Exception as e:
            log.error("Retake detection failed: %s — continuing without retake isolation", e)
            retakes_found = 0

    retake_count = sum(1 for s in all_segment_records if s.is_retake)

    if progress_callback:
        progress_callback(total, total, f"Building timeline '{new_name}'...")

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

    # Black Solid Color MediaPoolItem for retake gaps on Track 1.
    # Only attempt when retakes exist — no need to spend the bootstrap if we won't use it.
    from src.utils.black_clip import get_black_media_item
    black_item: Any | None = None
    if retake_count > 0:
        black_item = get_black_media_item(resolve)

    # Unified stream walk: best-takes go to Track 1; retakes leave a black gap
    # on Track 1 of the same duration AND go to Track 2 at the same recordFrame.
    # NOTE: Resolve's AppendToTimeline interprets endFrame EXCLUSIVELY for
    # explicit recordFrame entries (placed_length = endFrame - startFrame).
    # So endFrame = startFrame + placed_length, not startFrame + placed_length - 1.
    tl_start = dest_timeline.GetStartFrame()
    cursor = tl_start
    track1_entries: list[dict] = []
    retake_placements: list[tuple[int, int, Any, int]] = []  # (start_frame, end_frame, media_item, record_frame)
    for s in all_segment_records:
        dur = s.end_frame - s.start_frame + 1
        if s.is_retake:
            if black_item is not None:
                track1_entries.append({
                    "mediaPoolItem": black_item,
                    "mediaType":     1,
                    "startFrame":    0,
                    "endFrame":      dur,
                    "recordFrame":   cursor,
                    "trackIndex":    1,
                })
            else:
                log.warning(
                    "No black Solid Color — retake at recordFrame=%d (%.2fs) "
                    "omitted from Track 1; drag it manually from Track 2.",
                    cursor, dur / fps,
                )
            retake_placements.append((s.start_frame, s.end_frame, s.media_item, cursor))
        else:
            track1_entries.append({
                "mediaPoolItem": s.media_item,
                "startFrame":    s.start_frame,
                "endFrame":      s.end_frame + 1,  # exclusive: +1 to get dur frames
                "recordFrame":   cursor,
                "trackIndex":    1,
            })
        cursor += dur

    result = media_pool.AppendToTimeline(track1_entries)
    if not result:
        log.warning(
            "AppendToTimeline returned falsy — timeline '%s' may be incomplete.", new_name
        )

    # Place retakes on a separate disabled track when requested
    retake_track_index = 0
    if retake_placements:
        try:
            dest_timeline.AddTrack("video")
            retake_track_index = dest_timeline.GetTrackCount("video")

            # Ensure a matching audio track exists at the same index BEFORE placing clips,
            # so Resolve routes the clips' linked audio to the retake audio track.
            audio_count = dest_timeline.GetTrackCount("audio")
            while audio_count < retake_track_index:
                dest_timeline.AddTrack("audio")
                audio_count += 1

            track2_entries: list[dict] = [
                {
                    "mediaPoolItem": mi,
                    "startFrame":    sf,
                    "endFrame":      ef + 1,  # exclusive — same convention as track 1
                    "recordFrame":   rf,
                    "trackIndex":    retake_track_index,
                }
                for (sf, ef, mi, rf) in retake_placements
            ]
            retake_result = media_pool.AppendToTimeline(track2_entries)
            if not retake_result:
                log.warning("AppendToTimeline for retake track returned falsy")

            try:
                dest_timeline.SetTrackName("video", retake_track_index, "Retakes")
            except Exception as e:
                log.debug("SetTrackName video retake track failed: %s", e)
            try:
                dest_timeline.SetTrackEnable("video", retake_track_index, False)
            except Exception as e:
                log.warning("SetTrackEnable video retake track failed: %s", e)

            try:
                dest_timeline.SetTrackName("audio", retake_track_index, "Retakes")
            except Exception as e:
                log.debug("SetTrackName audio retake track failed: %s", e)
            try:
                dest_timeline.SetTrackEnable("audio", retake_track_index, False)
            except Exception as e:
                log.warning("SetTrackEnable audio retake track failed: %s", e)

            log.info(
                "Retake track %d created on '%s': %d retake(s)",
                retake_track_index, new_name, len(retake_placements),
            )
        except Exception as e:
            log.error("Failed to create retake track: %s", e)
            retake_track_index = 0

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
    )
