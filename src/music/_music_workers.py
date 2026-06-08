"""Background thread workers for the Music & SFX tab."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

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


def music_thread(
    frame: Any,
    app: Any,
    state: dict,
    jamendo_client_id: str,
    download_folder: str,
    music_mode: str,
    mood_mode: str,
    n_sections: int,
    set_status: Callable,
    set_progress: Callable,
    _ui: Callable,
    w: dict,
) -> None:
    """Analyze mood, search Jamendo music, download, place on 'Music' audio track."""
    try:
        from src.music.audio_provider import JamendoClient
        from src.music.mood_analyzer import analyze_mood_keywords, analyze_mood_llm
        from src.music.placer import place_audio_clip

        set_status("Analyzing transcript mood…")
        set_progress(10, True)

        sections_count = n_sections if music_mode == "segments" else 1

        if mood_mode == "llm":
            sections = analyze_mood_llm(app.transcript, app.settings, sections_count)
        else:
            sections = analyze_mood_keywords(app.transcript, sections_count)

        if not sections:
            set_status("Could not determine mood from transcript.", "#E8903A")
            set_progress(0, False)
            return

        client = JamendoClient(jamendo_client_id)
        dl_path = Path(download_folder)
        dl_path.mkdir(parents=True, exist_ok=True)

        placed_count = 0
        total = len(sections)

        for i, section in enumerate(sections):
            pct = int(20 + (i / total) * 70)
            set_progress(pct)
            set_status(f"Searching music for '{section.mood}' mood ({i + 1}/{total})…")

            hits = client.search_music(section.search_term, per_page=5)
            if not hits:
                log.warning("[music_worker] no results for %r — skipping section %d", section.search_term, i)
                continue

            hit = hits[0]
            dest = dl_path / _music_filename(hit)
            set_status(f"Downloading: {hit.title}…")

            if not dest.exists():
                try:
                    _download_audio(hit.download_url, dest)
                except Exception as e:
                    log.error("[music_worker] download failed: %s", e)
                    set_status(f"Download failed: {e}", "#ff6b6b")
                    continue

            set_status(f"Placing '{hit.title}' at {section.start_sec:.1f}s…")
            duration = section.end_sec - section.start_sec if music_mode == "segments" else 0.0
            result = place_audio_clip(app, str(dest), section.start_sec, duration, "Music")

            if result.placed:
                placed_count += 1
                log.info("[music_worker] placed %s at %.1fs", dest.name, section.start_sec)
            else:
                log.warning("[music_worker] placement failed: %s", result.reason)

        set_progress(100)
        if placed_count == total:
            set_status(f"Done! {placed_count} music track(s) placed on 'Music' audio track.", "#66bb6a")
        elif placed_count > 0:
            set_status(f"Placed {placed_count}/{total} track(s). Check logs for details.", "#ffa726")
        else:
            set_status("No tracks placed — check Resolve connection and Pixabay key.", "#ff6b6b")

        set_progress(0, False)

    except Exception as e:
        log.error("[music_worker] error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
        set_progress(0, False)
    finally:
        _ui(lambda: w["run_music_btn"].configure(state="normal"))
        state["running"] = False


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
) -> None:
    """Collect trigger events and place SFX clips on 'SFX' audio track."""
    try:
        from src.music.audio_provider import FreesoundClient
        from src.music.sfx_engine import collect_sfx_events, run_sfx_pipeline

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
            set_sfx_status(" ".join(hint), "#E8903A")
            set_sfx_progress(0, False)
            return

        set_sfx_status(f"Found {len(events)} event(s). Downloading SFX…")
        set_sfx_progress(20)

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
        )

        placed = sum(1 for r in results if r.placed)
        total  = len(results)
        set_sfx_progress(100)

        if placed == total and total > 0:
            set_sfx_status(f"Done! {placed}/{total} SFX clip(s) placed on 'SFX' track.", "#66bb6a")
        elif placed > 0:
            set_sfx_status(f"Placed {placed}/{total} SFX clip(s). Check logs.", "#ffa726")
        else:
            set_sfx_status("No SFX placed — check Resolve connection.", "#ff6b6b")

        set_sfx_progress(0, False)

    except Exception as e:
        log.error("[sfx_worker] error: %s", e)
        set_sfx_status(f"Error: {e}", "#ff6b6b")
        set_sfx_progress(0, False)
    finally:
        _ui(lambda: w["run_sfx_btn"].configure(state="normal"))
        state["sfx_running"] = False


def _music_filename(hit: Any) -> str:
    import re
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", hit.title).strip("-").lower()[:40] or "music"
    return f"music-{hit.external_id}-{slug}.mp3"
