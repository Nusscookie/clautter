"""Sound effects placement engine.

Collects SFX trigger events from shared app state (SmartCuts segments,
AutoZoom points, B-Roll placer results), maps each to a Pixabay SFX
search term, downloads the best hit, and places it on an "SFX" audio track.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)

# event_type → Pixabay SFX search term
SFX_TERM_MAP: dict[str, str] = {
    "cut":      "whoosh transition",
    "zoom_in":  "impact punch",
    "zoom_out": "swoosh impact",
    "broll_in": "transition whoosh",
}

# Deduplicate SFX events closer than this (seconds) — avoid stacking clips
_MIN_EVENT_GAP_SEC = 0.5


@dataclass
class SfxEvent:
    frame: int
    position_sec: float
    event_type: str   # "cut" | "zoom_in" | "zoom_out" | "broll_in"
    label: str


def collect_sfx_events(
    app: Any,
    use_cuts:  bool = True,
    use_zooms: bool = True,
    use_broll: bool = True,
) -> list[SfxEvent]:
    """Build a deduplicated, sorted list of SFX trigger events from app shared state.

    Reads:
      app.smartcuts_segments  → list[SegmentRecord]
      app.zoom_points         → list[ZoomPoint]
      app.broll_placer_results → list[PlacerResult]
    """
    events: list[SfxEvent] = []
    fps = getattr(app, "fps", 25.0)

    # Timeline start frame for sec conversion
    tl_start = 0
    try:
        if app.timeline is not None:
            tl_start = app.timeline.GetStartFrame() or 0
    except Exception:
        pass

    def frame_to_sec(frame: int) -> float:
        return max(0.0, (frame - tl_start) / fps)

    # ── SmartCuts cut transitions ──────────────────────────────────
    if use_cuts:
        segs = getattr(app, "smartcuts_segments", [])
        for i in range(len(segs) - 1):
            try:
                frame = int(segs[i].end_frame)
                events.append(SfxEvent(
                    frame=frame,
                    position_sec=frame_to_sec(frame),
                    event_type="cut",
                    label=f"SmartCuts cut #{i + 1}",
                ))
            except Exception as e:
                log.debug("[sfx_engine] skip cut event %d: %s", i, e)

    # ── AutoZoom events ────────────────────────────────────────────
    if use_zooms:
        zoom_pts = getattr(app, "zoom_points", [])
        for zp in zoom_pts:
            try:
                frame = int(zp.timeline_frame)
                zoom_amount = float(getattr(zp, "zoom_amount", 1.15))
                etype = "zoom_in" if zoom_amount >= 1.0 else "zoom_out"
                events.append(SfxEvent(
                    frame=frame,
                    position_sec=frame_to_sec(frame),
                    event_type=etype,
                    label=f"AutoZoom {etype} ({zoom_amount:.2f}x)",
                ))
            except Exception as e:
                log.debug("[sfx_engine] skip zoom event: %s", e)

    # ── B-Roll entry points ────────────────────────────────────────
    if use_broll:
        broll_results = getattr(app, "broll_placer_results", [])
        for pr in broll_results:
            try:
                sec = float(pr.segment_start_sec)
                frame = tl_start + int(round(sec * fps))
                events.append(SfxEvent(
                    frame=frame,
                    position_sec=sec,
                    event_type="broll_in",
                    label=f"B-Roll entry at {sec:.1f}s",
                ))
            except Exception as e:
                log.debug("[sfx_engine] skip broll event: %s", e)

    # Sort by position and deduplicate events too close together
    events.sort(key=lambda e: e.position_sec)
    deduped: list[SfxEvent] = []
    last_sec = -999.0
    for ev in events:
        if ev.position_sec - last_sec >= _MIN_EVENT_GAP_SEC:
            deduped.append(ev)
            last_sec = ev.position_sec

    log.info("[sfx_engine] collected %d event(s) (%d after dedup)", len(events), len(deduped))
    return deduped


def run_sfx_pipeline(
    app: Any,
    events: list[SfxEvent],
    audio_client: Any,
    download_folder: str,
    on_progress: Callable[[str, float], None],
    local_sfx_folder: str | None = None,
) -> list[Any]:
    """For each SFX event: find/download an audio clip → place on 'SFX' track.

    Args:
        app:              ClutterApp.
        events:           List of SfxEvent from collect_sfx_events().
        audio_client:     PixabayAudioClient instance.
        download_folder:  Where to save downloaded MP3s.
        on_progress:      Callback(message, 0.0-1.0).
        local_sfx_folder: Optional folder of local .mp3/.wav files to prefer.

    Returns:
        List of AudioPlacerResult objects.
    """
    from src.music.placer import place_audio_clip, AudioPlacerResult
    import requests as _req

    dl_path = Path(download_folder)
    dl_path.mkdir(parents=True, exist_ok=True)
    results: list[Any] = []

    for idx, event in enumerate(events):
        progress = (idx + 1) / max(len(events), 1)
        term = SFX_TERM_MAP.get(event.event_type, "whoosh transition")
        on_progress(f"SFX: {event.label} — searching '{term}'…", progress * 0.5)

        # Try local folder first
        local_path: str | None = None
        if local_sfx_folder and os.path.isdir(local_sfx_folder):
            local_path = _find_local_sfx(local_sfx_folder, term)
            if local_path:
                log.debug("[sfx_engine] local match: %s", local_path)

        # Fall back to Pixabay SFX
        if not local_path:
            try:
                hits = audio_client.search_sfx(term, per_page=5)
                if not hits:
                    log.warning("[sfx_engine] no SFX results for %r — skipping event", term)
                    continue
                hit = hits[0]
                on_progress(f"SFX: downloading '{hit.title}'…", progress * 0.75)
                dest = dl_path / _sfx_filename(hit)
                if not dest.exists():
                    _download_audio(hit.download_url, dest)
                local_path = str(dest)
            except Exception as e:
                log.error("[sfx_engine] SFX download failed for %r: %s", term, e)
                continue

        # Apply fixed -10 dB gain reduction (baked into a cached processed copy)
        from src.music.audio_processor import get_or_process_sfx, SFX_GAIN_DB
        local_path = get_or_process_sfx(local_path, dl_path / "processed", SFX_GAIN_DB)

        on_progress(f"SFX: placing at {event.position_sec:.1f}s…", progress * 0.9)
        result = place_audio_clip(app, local_path, event.position_sec, track_name="SFX")
        results.append(result)
        if not result.placed:
            log.warning("[sfx_engine] placement failed: %s", result.reason)

    on_progress("SFX pipeline complete.", 1.0)
    return results


def _find_local_sfx(folder: str, term: str) -> str | None:
    """Return path to first local file whose name contains a term keyword."""
    term_words = set(term.lower().split())
    try:
        for fname in os.listdir(folder):
            if not fname.lower().endswith((".mp3", ".wav", ".flac", ".ogg")):
                continue
            name_lower = fname.lower()
            if any(w in name_lower for w in term_words):
                return str(Path(folder) / fname)
    except Exception as e:
        log.warning("[sfx_engine] local SFX scan failed: %s", e)
    return None


def _sfx_filename(hit: Any) -> str:
    import re
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", hit.title).strip("-").lower()[:40] or "sfx"
    return f"sfx-{hit.external_id}-{slug}.mp3"


def _download_audio(url: str, dest: Path) -> None:
    import requests as _req
    with _req.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
