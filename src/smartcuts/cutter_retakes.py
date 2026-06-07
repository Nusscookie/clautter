"""Retake timeline placement helpers for the cutter.

Extracted from cutter.py. Contains the stream-walk that partitions segments
into Track 1 (best takes) and retake placements, plus the retake track builder.
"""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger
from src.smartcuts.retake_types import SegmentRecord

log = get_logger(__name__)


def _build_timeline_entries(
    all_segment_records: list[SegmentRecord],
    black_item: Any | None,
    fps: float,
    tl_start: int,
) -> tuple[list[dict], list[tuple[int, int, Any, int]]]:
    """Walk segments and build Track 1 entries + retake placements.

    Returns:
        (track1_entries, retake_placements)
        retake_placements is a list of (start_frame, end_frame, media_item, record_frame).
    """
    cursor = tl_start
    track1_entries: list[dict] = []
    retake_placements: list[tuple[int, int, Any, int]] = []

    for s in all_segment_records:
        dur = s.end_frame - s.start_frame + 1

        if not s.is_retake or not s.retake_regions:
            track1_entries.append({
                "mediaPoolItem": s.media_item,
                "startFrame":    s.start_frame,
                "endFrame":      s.end_frame + 1,  # exclusive: +1 to get dur frames
                "recordFrame":   cursor,
                "trackIndex":    1,
            })
            cursor += dur
            continue

        # One or more retake sub-ranges inside this clip. Split the clip at each:
        # kept speech → Track 1, retake spans → black gap on Track 1 + Track 2.
        regions = _merge_regions(s, fps)
        cur = cursor
        prev_frame = s.start_frame  # next kept sub-clip starts here

        for retake_sf, retake_ef in regions:
            if retake_sf > prev_frame:
                track1_entries.append({
                    "mediaPoolItem": s.media_item,
                    "startFrame":    prev_frame,
                    "endFrame":      retake_sf,  # exclusive
                    "recordFrame":   cur,
                    "trackIndex":    1,
                })
                cur += retake_sf - prev_frame

            retake_dur = retake_ef - retake_sf + 1
            if black_item is not None:
                track1_entries.append({
                    "mediaPoolItem": black_item,
                    "mediaType":     1,
                    "startFrame":    0,
                    "endFrame":      retake_dur,
                    "recordFrame":   cur,
                    "trackIndex":    1,
                })
            else:
                log.warning(
                    "No black Solid Color — retake at recordFrame=%d (%.2fs) omitted "
                    "from Track 1; drag it manually from Track 2.", cur, retake_dur / fps,
                )
            retake_placements.append((retake_sf, retake_ef, s.media_item, cur))
            cur += retake_dur
            prev_frame = retake_ef + 1

        if prev_frame <= s.end_frame:
            track1_entries.append({
                "mediaPoolItem": s.media_item,
                "startFrame":    prev_frame,
                "endFrame":      s.end_frame + 1,
                "recordFrame":   cur,
                "trackIndex":    1,
            })
            cur += s.end_frame + 1 - prev_frame

        cursor = cur

    return track1_entries, retake_placements


def _merge_regions(s: SegmentRecord, fps: float) -> list[tuple[int, int]]:
    """Convert a segment's retake_regions (ms) to clamped, sorted, merged frame spans.

    Returns inclusive (start_frame, end_frame) pairs that never overlap and stay
    within [s.start_frame, s.end_frame].
    """
    spans: list[tuple[int, int]] = []
    for r_start_ms, r_end_ms in s.retake_regions:
        sf = s.start_frame + round((r_start_ms - s.start_ms) * fps / 1000)
        ef = s.start_frame + round((r_end_ms   - s.start_ms) * fps / 1000)
        sf = max(s.start_frame, min(sf, s.end_frame))
        ef = max(sf,            min(ef, s.end_frame))
        spans.append((sf, ef))

    spans.sort()
    merged: list[tuple[int, int]] = []
    for sf, ef in spans:
        if merged and sf <= merged[-1][1] + 1:  # overlapping or adjacent
            merged[-1] = (merged[-1][0], max(merged[-1][1], ef))
        else:
            merged.append((sf, ef))
    return merged


def _create_retake_track(
    dest_timeline: Any,
    retake_placements: list[tuple[int, int, Any, int]],
    media_pool: Any,
    new_name: str,
) -> int:
    """Add a retake video+audio track pair, place retakes, and name it.

    Returns the retake track index, or 0 on failure.
    """
    try:
        dest_timeline.AddTrack("video")
        retake_track_index = dest_timeline.GetTrackCount("video")

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

        for track_type in ("video", "audio"):
            try:
                dest_timeline.SetTrackName(track_type, retake_track_index, "Retakes")
            except Exception as e:
                log.debug("SetTrackName %s retake track failed: %s", track_type, e)

        log.info(
            "Retake track %d created on '%s': %d retake(s)",
            retake_track_index, new_name, len(retake_placements),
        )
        return retake_track_index
    except Exception as e:
        log.error("Failed to create retake track: %s", e)
        return 0
