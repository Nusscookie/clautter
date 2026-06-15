"""Audio track placement for Music & SFX.

Places an MP3 or WAV file on a named audio track in DaVinci Resolve.
Mirrors src/broll/placer.py but uses mediaType=2 (audio) and
GetTrackCount("audio") / AddTrack("audio").
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.constants import TRACKS
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class AudioPlacerResult:
    clip_path: str
    position_sec: float
    placed: bool
    reason: str = ""

    def __repr__(self) -> str:
        status = "placed" if self.placed else f"skipped ({self.reason})"
        return f"<AudioPlacerResult {Path(self.clip_path).name} @ {self.position_sec:.1f}s — {status}>"


def _find_or_create_audio_track(timeline: Any, track_name: str) -> int:
    """Return 1-based audio track index for track_name; creates + names one if absent."""
    try:
        count = timeline.GetTrackCount("audio")
        for i in range(1, count + 1):
            try:
                name = timeline.GetTrackName("audio", i) or ""
                if name.strip().lower() == track_name.lower():
                    log.debug("[audio_placer] found '%s' track at audio index %d", track_name, i)
                    return i
            except Exception:
                continue

        timeline.AddTrack("audio")
        new_index = count + 1
        try:
            timeline.SetTrackName("audio", new_index, track_name)
            log.info("[audio_placer] created '%s' track at audio index %d", track_name, new_index)
        except Exception as e:
            log.debug("[audio_placer] SetTrackName failed (non-fatal, track %d usable): %s", new_index, e)
        return new_index
    except Exception as e:
        log.warning("[audio_placer] _find_or_create_audio_track failed (%s) — using track 2", e)
        return 2


def _walk_pool(folder: Any):
    """Yield every MediaPoolItem in the folder tree."""
    try:
        for clip in (folder.GetClipList() or []):
            yield clip
    except Exception:
        pass
    try:
        for sub in (folder.GetSubFolderList() or []):
            yield from _walk_pool(sub)
    except Exception:
        pass


def _find_in_pool(media_pool: Any, filename: str) -> Any | None:
    """Scan the whole media pool for a clip whose name matches filename."""
    fname_lower = filename.lower()
    try:
        for item in _walk_pool(media_pool.GetRootFolder()):
            try:
                props = item.GetClipProperty() or {}
                name = (props.get("Clip Name") or "").lower()
                if name == fname_lower or name == fname_lower.rsplit(".", 1)[0]:
                    log.debug("[audio_placer] found existing pool item: %s", name)
                    return item
            except Exception:
                continue
    except Exception as e:
        log.debug("[audio_placer] pool scan failed: %s", e)
    return None


def _fps_from_timeline(timeline: Any) -> float:
    try:
        raw = timeline.GetSetting("timelineFrameRate") or "25"
        return float(str(raw).split()[0])
    except Exception:
        return 25.0


def _sec_to_frame(sec: float, fps: float) -> int:
    return max(0, int(round(sec * fps)))


def place_audio_clip(
    app: Any,
    clip_path: str,
    position_sec: float,
    duration_sec: float = 0.0,
    track_name: str = TRACKS.MUSIC,
) -> AudioPlacerResult:
    """Place an MP3/WAV on the named audio track at position_sec.

    Args:
        app:          ClautterApp — needs .resolve.
        clip_path:    Absolute path to a local MP3/WAV file.
        position_sec: Start position on the timeline (seconds).
        duration_sec: How much of the clip to use; 0 = full clip.
        track_name:   Audio track name to place on ("Music" or "SFX").

    Returns:
        AudioPlacerResult with placed=True on success.
    """
    clip_path = str(clip_path)
    clip_name = Path(clip_path).name

    resolve = getattr(app, "resolve", None)
    if resolve is None:
        return AudioPlacerResult(clip_path, position_sec, False,
                                 "app.resolve is None — not connected to Resolve")

    try:
        project    = resolve.GetProjectManager().GetCurrentProject()
        if project is None:
            return AudioPlacerResult(clip_path, position_sec, False, "GetCurrentProject() returned None")
        media_pool = project.GetMediaPool()
        if media_pool is None:
            return AudioPlacerResult(clip_path, position_sec, False, "GetMediaPool() returned None")
        timeline   = project.GetCurrentTimeline()
        if timeline is None:
            return AudioPlacerResult(clip_path, position_sec, False,
                                     "GetCurrentTimeline() returned None — open a timeline in Resolve")
    except Exception as e:
        return AudioPlacerResult(clip_path, position_sec, False, f"Resolve API chain failed: {e}")

    try:
        items = media_pool.ImportMedia([clip_path])
        if not items:
            # Resolve returns [] when the clip is already in the pool — scan for it
            log.debug("[audio_placer] ImportMedia returned empty for %s — scanning pool", clip_name)
            mpi = _find_in_pool(media_pool, clip_name)
            if mpi is None:
                return AudioPlacerResult(clip_path, position_sec, False,
                                         f"ImportMedia returned empty for {clip_name} and not found in pool")
        else:
            mpi = items[0]
    except Exception as e:
        return AudioPlacerResult(clip_path, position_sec, False, f"ImportMedia failed: {e}")

    fps = _fps_from_timeline(timeline)
    try:
        tl_start = timeline.GetStartFrame()
    except Exception:
        tl_start = 0

    # Resolve clip frame count (source duration cap — endFrame must not exceed this)
    clip_frames: int | None = None
    try:
        props = mpi.GetClipProperty() or {}
        raw = props.get("Frames") or ""
        if raw:
            clip_frames = int(str(raw).split()[0])
    except Exception:
        pass
    if clip_frames is None:
        # Audio files often have no "Frames" entry — derive from pydub
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(clip_path)
            clip_frames = max(1, _sec_to_frame(len(seg) / 1000.0, fps))
        except Exception:
            pass

    record_frame   = tl_start + _sec_to_frame(position_sec, fps)
    audio_track_idx = _find_or_create_audio_track(timeline, track_name)

    clip_info: dict[str, Any] = {
        "mediaPoolItem": mpi,
        "mediaType":     2,
        "startFrame":    0,
        "recordFrame":   record_frame,
        "trackIndex":    audio_track_idx,
    }
    if duration_sec > 0.0:
        want_frames = max(1, _sec_to_frame(duration_sec, fps))
        # Cap to clip's actual length so Resolve doesn't loop/stretch a short clip
        if clip_frames is not None:
            want_frames = min(want_frames, clip_frames)
        clip_info["endFrame"] = want_frames
    elif clip_frames is not None:
        # No explicit trim requested — still set endFrame to prevent any Resolve looping
        clip_info["endFrame"] = clip_frames

    log.debug(
        "[audio_placer] AppendToTimeline: %s → audio track %d '%s', "
        "recordFrame %d (%.1fs), endFrame %s",
        clip_name, audio_track_idx, track_name,
        record_frame, position_sec, clip_info.get("endFrame", "full"),
    )

    try:
        placed = media_pool.AppendToTimeline([clip_info])
        if placed:
            log.info("[audio_placer] placed %s on '%s' track at %.1fs", clip_name, track_name, position_sec)
            return AudioPlacerResult(clip_path, position_sec, True)
        log.warning("[audio_placer] AppendToTimeline returned empty for %s", clip_name)
        return AudioPlacerResult(clip_path, position_sec, False,
                                 "AppendToTimeline returned empty (free edition restriction?)")
    except Exception as e:
        log.error("[audio_placer] AppendToTimeline raised: %s", e)
        return AudioPlacerResult(clip_path, position_sec, False, str(e))
