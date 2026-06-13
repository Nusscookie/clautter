"""Background thread workers for the Music & SFX tab."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from src.constants import COLORS, TRACKS
from src.utils.logger import get_logger

log = get_logger(__name__)

_CHUNK_BYTES = 64 * 1024
_TIMEOUT_SEC = 60


def _download_audio(url: str, dest: Path) -> None:
    import requests
    with requests.get(url, stream=True, timeout=_TIMEOUT_SEC) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=_CHUNK_BYTES):
                if chunk:
                    f.write(chunk)


def _get_timeline_duration_sec(app: Any) -> float | None:
    """Return timeline total duration in seconds, or None if unavailable."""
    try:
        resolve  = getattr(app, "resolve", None)
        if resolve is None:
            return None
        project  = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        if timeline is None:
            return None
        raw_fps = timeline.GetSetting("timelineFrameRate") or "25"
        fps = float(str(raw_fps).split()[0])
        duration_frames = timeline.GetEndFrame() - timeline.GetStartFrame()
        return max(0.0, duration_frames / fps)
    except Exception as e:
        log.warning("[music_worker] could not read timeline duration: %s", e)
        return None


def _get_main_track_rms(app: Any) -> float | None:
    """Return dBFS of the loudest clip on video track 1, or None if unavailable."""
    try:
        from src.music.audio_processor import measure_rms_db
        resolve  = getattr(app, "resolve", None)
        if resolve is None:
            return None
        project  = resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        if timeline is None:
            return None
        items = timeline.GetItemListInTrack("video", 1) or []
        best_rms: float | None = None
        for item in items:
            try:
                mpi   = item.GetMediaPoolItem()
                props = mpi.GetClipProperty() if mpi else {}
                fpath = props.get("File Path") or props.get("Clip Path") or ""
                if not fpath:
                    continue
                rms = measure_rms_db(fpath)
                if rms is not None and (best_rms is None or rms > best_rms):
                    best_rms = rms
            except Exception:
                continue
        if best_rms is not None:
            log.info("[music_worker] main track RMS: %.1f dBFS", best_rms)
        return best_rms
    except Exception as e:
        log.warning("[music_worker] could not measure main track RMS: %s", e)
        return None


def music_thread(
    frame: Any,
    app: Any,
    state: dict,
    jamendo_client_id: str,
    download_folder: str,
    music_mode: str,
    mood_mode: str,
    n_sections: int,
    mood_provider: str | None,
    set_status: Callable,
    set_progress: Callable,
    _ui: Callable,
    w: dict,
    music_source: str = "jamendo",
    local_music_folder: str | None = None,
    music_volume_pct: int = 35,
    fade_in_ms: int = 2000,
    fade_out_ms: int = 2000,
    keyword_method: str = "spacy",
) -> None:
    """Analyze mood, find music (local / Jamendo / both), place on 'Music' audio track."""
    try:
        from src.music.mood_analyzer import analyze_mood_keywords, analyze_mood_llm
        from src.music.placer import place_audio_clip

        set_status("Analyzing transcript mood…")
        set_progress(10, True)

        timeline_duration_sec = _get_timeline_duration_sec(app)
        if timeline_duration_sec is not None:
            log.info("[music_worker] timeline duration: %.1fs", timeline_duration_sec)
        else:
            log.warning("[music_worker] timeline duration unavailable — music will not be trimmed")

        set_status("Measuring main track level…")
        main_track_rms = _get_main_track_rms(app)

        sections_count = n_sections if music_mode == "segments" else 1

        if mood_mode == "llm":
            sections = analyze_mood_llm(app.transcript, app.settings, sections_count,
                                        provider=mood_provider, method=keyword_method)
        else:
            sections = analyze_mood_keywords(app.transcript, sections_count, method=keyword_method)

        if not sections:
            set_status("Could not determine mood from transcript.", COLORS.WARNING)
            set_progress(0, False)
            return

        use_jamendo = music_source in ("jamendo", "both")
        use_local   = music_source in ("local", "both")

        client = None
        if use_jamendo:
            from src.music.audio_provider import JamendoClient
            client = JamendoClient(jamendo_client_id)

        dl_path = Path(download_folder)
        if use_jamendo:
            dl_path.mkdir(parents=True, exist_ok=True)

        placed_count = 0
        total = len(sections)

        for i, section in enumerate(sections):
            pct = int(20 + (i / total) * 70)
            set_progress(pct)
            set_status(f"Searching music for '{section.mood}' mood ({i + 1}/{total})…")

            audio_path: str | None = None

            # Local folder: try to find a file whose name contains a mood keyword
            if use_local and local_music_folder:
                audio_path = _find_local_music(local_music_folder, section.search_term)
                if audio_path:
                    log.debug("[music_worker] local match: %s", audio_path)

            # Jamendo fallback (or primary if source=jamendo)
            if audio_path is None and use_jamendo and client is not None:
                hits = client.search_music(section.search_term, per_page=5)
                if not hits:
                    log.warning("[music_worker] no Jamendo results for %r — skipping section %d",
                                section.search_term, i)
                    continue

                hit = hits[0]
                dest = dl_path / _music_filename(hit)
                set_status(f"Downloading: {hit.title}…")
                if not dest.exists():
                    try:
                        _download_audio(hit.download_url, dest)
                    except Exception as e:
                        log.error("[music_worker] download failed: %s", e)
                        set_status(f"Download failed: {e}", COLORS.ERROR)
                        continue
                audio_path = str(dest)

            if audio_path is None:
                log.warning("[music_worker] no audio found for section %d (%s)", i, section.mood)
                continue

            # Bake volume + fades into a processed copy (pydub, cached on disk)
            from src.music.audio_processor import get_or_process_music
            processed_dir = Path(download_folder) / "processed"
            audio_path = get_or_process_music(
                audio_path, processed_dir, music_volume_pct, fade_in_ms, fade_out_ms,
                target_db=main_track_rms,
            )

            fname = Path(audio_path).name
            set_status(f"Placing '{fname}' at {section.start_sec:.1f}s…")

            if music_mode == "segments":
                duration = section.end_sec - section.start_sec
                if timeline_duration_sec is not None:
                    duration = min(duration, max(0.0, timeline_duration_sec - section.start_sec))
            else:
                # Single track: fill from start to timeline end
                if timeline_duration_sec is not None:
                    duration = max(0.0, timeline_duration_sec - section.start_sec)
                else:
                    duration = 0.0  # full clip (no trim possible)

            result = place_audio_clip(app, audio_path, section.start_sec, duration, TRACKS.MUSIC)

            if result.placed:
                placed_count += 1
                log.info("[music_worker] placed %s at %.1fs", fname, section.start_sec)
            else:
                log.warning("[music_worker] placement failed: %s", result.reason)

        set_progress(100)
        if placed_count == total:
            set_status(f"Done! {placed_count} music track(s) placed on 'Music' audio track.", COLORS.SUCCESS)
        elif placed_count > 0:
            set_status(f"Placed {placed_count}/{total} track(s). Check logs for details.", COLORS.WARN_PARTIAL)
        else:
            set_status("No tracks placed — check Resolve connection and audio source settings.", COLORS.ERROR)

        set_progress(0, False)

    except Exception as e:
        log.error("[music_worker] error: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
        set_progress(0, False)
    finally:
        _ui(lambda: w["run_music_btn"].configure(state="normal"))
        state["running"] = False


def _find_local_music(folder: str, search_term: str) -> str | None:
    """Return path to first local audio file whose name contains a search-term keyword."""
    import os, re
    term_words = set(re.sub(r"[^a-z0-9 ]+", "", search_term.lower()).split())
    try:
        for fname in os.listdir(folder):
            if not fname.lower().endswith((".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a")):
                continue
            name_lower = fname.lower()
            if any(w in name_lower for w in term_words):
                return str(Path(folder) / fname)
        # no keyword match — return first audio file as fallback
        for fname in os.listdir(folder):
            if fname.lower().endswith((".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a")):
                return str(Path(folder) / fname)
    except Exception as e:
        log.warning("[music_worker] local music scan failed: %s", e)
    return None


def sfx_thread(
    frame: Any,
    app: Any,
    state: dict,
    freesound_api_key: str,
    download_folder: str,
    use_cuts: bool,
    use_zooms: bool,
    use_broll: bool,
    local_sfx_folder: str | None,
    set_sfx_status: Callable,
    set_sfx_progress: Callable,
    _ui: Callable,
    w: dict,
    sfx_source: str = "freesound",
    sfx_mood_mode: str = "hardcoded",
    sfx_llm_provider: str | None = None,
) -> None:
    """Collect trigger events and place SFX clips on 'SFX' audio track."""
    try:
        from src.music.sfx_engine import (
            collect_sfx_events, run_sfx_pipeline,
            build_event_manifest, get_sfx_terms_llm,
        )

        use_freesound = sfx_source in ("freesound", "both")

        set_sfx_status("Collecting SFX trigger events…")
        set_sfx_progress(10, True)

        events = collect_sfx_events(app, use_cuts=use_cuts, use_zooms=use_zooms, use_broll=use_broll)
        if not events:
            hint = []
            if not use_cuts and not use_zooms and not use_broll:
                hint.append("No triggers selected — enable at least one checkbox.")
            elif not getattr(app, "smartcuts_segments", []) and not getattr(app, "zoom_points", []) and not getattr(app, "broll_placer_results", []):
                hint.append("No analysis data found — run SmartCuts, Auto Zooms, or B-Roll first.")
            else:
                hint.append("No events found for selected triggers.")
            set_sfx_status(" ".join(hint), COLORS.WARNING)
            set_sfx_progress(0, False)
            return

        set_sfx_status(f"Found {len(events)} event(s). Downloading SFX…")
        set_sfx_progress(20)

        # LLM term selection (optional)
        custom_terms: dict[int, str] | None = None
        if sfx_mood_mode == "llm" and app.transcript:
            set_sfx_status("Asking LLM for context-aware SFX terms…")
            manifest = build_event_manifest(events, app.transcript)
            custom_terms = get_sfx_terms_llm(manifest, app.settings, provider=sfx_llm_provider) or None

        client = None
        if use_freesound and freesound_api_key:
            from src.music.audio_provider import FreesoundClient
            client = FreesoundClient(freesound_api_key)

        dl_path = Path(download_folder)

        def on_progress(msg: str, frac: float) -> None:
            pct = int(20 + frac * 75)
            set_sfx_progress(pct)
            set_sfx_status(msg)

        results = run_sfx_pipeline(
            app=app,
            events=events,
            audio_client=client,
            download_folder=str(dl_path),
            on_progress=on_progress,
            local_sfx_folder=local_sfx_folder or None,
            sfx_source=sfx_source,
            custom_terms=custom_terms,
        )

        placed = sum(1 for r in results if r.placed)
        total  = len(results)
        set_sfx_progress(100)

        if placed == total and total > 0:
            set_sfx_status(f"Done! {placed}/{total} SFX clip(s) placed on 'SFX' track.", COLORS.SUCCESS)
        elif placed > 0:
            set_sfx_status(f"Placed {placed}/{total} SFX clip(s). Check logs.", COLORS.WARN_PARTIAL)
        else:
            set_sfx_status("No SFX placed — check Resolve connection.", COLORS.ERROR)

        set_sfx_progress(0, False)

    except Exception as e:
        log.error("[sfx_worker] error: %s", e)
        set_sfx_status(f"Error: {e}", COLORS.ERROR)
        set_sfx_progress(0, False)
    finally:
        _ui(lambda: w["run_sfx_btn"].configure(state="normal"))
        state["sfx_running"] = False


def _music_filename(hit: Any) -> str:
    import re
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", hit.title).strip("-").lower()[:40] or "music"
    return f"music-{hit.external_id}-{slug}.mp3"
