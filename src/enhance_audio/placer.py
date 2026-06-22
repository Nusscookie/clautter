"""Resolve orchestration for Enhance Audio.

Collects clips on audio track 1, extracts each clip's *trimmed* segment from
the source file (respecting timeline in/out offsets so cuts are honoured), runs
the enhancement chain, then places the cleaned WAV on a dedicated "Enhanced"
audio track at the clip's timeline position.

Non-destructive: the original audio track is muted (not deleted) after all
clips are placed.  Video clips are never touched.

Reuses:
  - ``src.music.placer.place_audio_clip`` for import + AppendToTimeline
  - ``src.utils.resolve_utils.get_clip_file_path`` / ``get_fps``
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.constants import TRACKS
from src.enhance_audio import processor
from src.music.placer import place_audio_clip
from src.utils.logger import get_logger
from src.utils.resolve_utils import get_clip_file_path, get_fps

log = get_logger(__name__)

ProgressCb = Callable[[int, int, str], None]


@dataclass
class EnhanceResult:
    clip_name: str
    placed: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Clip selection
# ---------------------------------------------------------------------------

def _get_audio_clips(timeline: Any, track_index: int = 1) -> list[Any]:
    try:
        items = timeline.GetItemListInTrack("audio", track_index)
        return list(items) if items else []
    except Exception as e:
        log.error("[enhance_placer] GetItemListInTrack('audio', %d): %s", track_index, e)
        return []


def _select_clips(timeline: Any, scope: str) -> list[Any]:
    """Return audio track-1 clips filtered by scope."""
    all_clips = _get_audio_clips(timeline, track_index=1)
    if scope != "selected" or not all_clips:
        return all_clips
    # 'selected' → try to match the currently-selected video item by start frame
    try:
        sel = timeline.GetCurrentVideoItem()
    except Exception:
        sel = None
    if sel is not None:
        try:
            sel_start = sel.GetStart()
            match = [c for c in all_clips if _safe_start(c) == sel_start]
            if match:
                return match
        except Exception:
            pass
    return all_clips


def _safe_start(clip: Any) -> Any:
    try:
        return clip.GetStart()
    except Exception:
        return None


def _clip_name(clip: Any) -> str:
    try:
        return clip.GetName() or "clip"
    except Exception:
        path = get_clip_file_path(clip)
        return Path(path).name if path else "clip"


# ---------------------------------------------------------------------------
# Trimmed-segment extraction
# ---------------------------------------------------------------------------

def _extract_trimmed_wav(clip: Any, fps: float, tmp_dir: str) -> str | None:
    """Export the exact portion of the source file that is visible on the timeline.

    Uses ``GetSourceStartFrame`` + ``GetStart``/``GetEnd`` to compute the
    segment in/out points, then slices with pydub.  Returns the temp WAV path,
    or None if the source cannot be resolved.
    """
    src_path = get_clip_file_path(clip)
    if not src_path or not os.path.exists(src_path):
        return None

    try:
        src_start_frame = clip.GetSourceStartFrame()  # offset into source media
        tl_start = clip.GetStart()                    # timeline in-point (absolute)
        tl_end = clip.GetEnd()                        # timeline out-point (absolute)
        duration_frames = max(1, tl_end - tl_start)
        in_frame = src_start_frame                    # first source frame used
        out_frame = src_start_frame + duration_frames
    except Exception as e:
        log.warning("[enhance_placer] frame offset query failed (%s) — using full source", e)
        in_frame, out_frame = 0, None  # fallback: full file

    try:
        from pydub import AudioSegment  # type: ignore
        seg = AudioSegment.from_file(src_path)
        if fps and fps > 0 and in_frame is not None:
            in_ms = int((in_frame / fps) * 1000)
            out_ms = int((out_frame / fps) * 1000) if out_frame else len(seg)
            seg = seg[in_ms:out_ms]

        out_path = os.path.join(tmp_dir, f"trim_{abs(hash(src_path + str(in_frame)))}.wav")
        seg.export(out_path, format="wav")
        return out_path
    except Exception as e:
        log.error("[enhance_placer] trim extract failed for %s: %s", src_path, e)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def enhance_timeline(
    app: Any,
    engine_ids: list[str],
    strength: float,
    scope: str = "selected",
    mute_original: bool = True,
    progress: ProgressCb | None = None,
) -> tuple[list[EnhanceResult], str]:
    """Enhance clips on audio track 1 and place results on "Enhanced" audio track.

    Workflow per clip:
      1. Extract the *trimmed* portion of the source file (pydub slice).
      2. Run the enhancement chain (processor.enhance_clip on the trim).
      3. Place the cleaned WAV on the "Enhanced" audio track at the clip's
         timeline position.
    After all clips are placed, audio track 1 is muted (not disabled).

    Args:
        app:           ClautterApp — needs .resolve / .project / .timeline.
        engine_ids:    Engines to chain (resolved to canonical order).
        strength:      0.0–1.0.
        scope:         "selected" or "all".
        mute_original: Mute audio track 1 after placing enhanced clips.
        progress:      (done, total, msg) callback.

    Returns:
        (results, summary_message).
    """
    resolve = getattr(app, "resolve", None)
    if resolve is None:
        return [], "Not connected to Resolve."

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
    except Exception as e:
        return [], f"Resolve API chain failed: {e}"
    if timeline is None:
        return [], "No timeline open in Resolve."

    fps = get_fps(project)
    tl_start = 0
    try:
        tl_start = int(timeline.GetStartFrame())
    except Exception:
        pass

    clips = _select_clips(timeline, scope)
    if not clips:
        return [], "No audio clips found on audio track 1" + (
            " (nothing selected)." if scope == "selected" else "."
        )

    results: list[EnhanceResult] = []
    total = len(clips)

    with tempfile.TemporaryDirectory(prefix="clautter_enhance_") as tmp_dir:
        for i, clip in enumerate(clips):
            name = _clip_name(clip)
            if progress:
                progress(i, total, f"Enhancing {i + 1}/{total}: {name}")

            # Step 1: extract trimmed segment from source
            trimmed_wav = _extract_trimmed_wav(clip, fps, tmp_dir)
            if not trimmed_wav:
                results.append(EnhanceResult(name, False, "could not extract source audio"))
                continue

            # Step 2: run enhancement chain on the trimmed segment
            try:
                out_wav = processor.enhance_clip(trimmed_wav, engine_ids, strength)
            except Exception as e:
                log.error("[enhance_placer] enhance failed for %s: %s", name, e)
                results.append(EnhanceResult(name, False, str(e)))
                continue

            # Step 3: place on Enhanced audio track at clip's timeline position
            try:
                tl_clip_start = int(clip.GetStart())
            except Exception:
                tl_clip_start = tl_start
            position_sec = max(0.0, (tl_clip_start - tl_start) / fps) if fps else 0.0

            res = place_audio_clip(
                app, out_wav, position_sec, duration_sec=0.0,
                track_name=TRACKS.ENHANCED,
            )
            results.append(EnhanceResult(name, res.placed, res.reason))

    # Mute original audio track 1 after all clips placed
    if mute_original and any(r.placed for r in results):
        _mute_audio_track(timeline, track_index=1)

    if progress:
        progress(total, total, "Done.")

    placed = sum(1 for r in results if r.placed)
    summary = f"Enhanced {placed}/{total} clip(s) onto the '{TRACKS.ENHANCED}' track."
    if placed < total:
        summary += " Some clips skipped — see log."
    return results, summary


def _mute_audio_track(timeline: Any, track_index: int) -> None:
    """Disable audio track 1 after enhanced clips are placed."""
    try:
        timeline.SetTrackEnable("audio", track_index, False)
        log.info("[enhance_placer] disabled audio track %d via SetTrackEnable", track_index)
    except Exception as e:
        log.warning("[enhance_placer] could not disable audio track %d: %s", track_index, e)
