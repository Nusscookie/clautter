"""Background thread workers for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
Each function receives all captured state as explicit parameters.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


def suggest_local_thread(
    w: dict,
    app: Any,
    _state: dict,
    set_status: Callable,
    set_suggestions: Callable,
    _ui: Callable,
) -> None:
    """Scan folder, check transcript, then generate B-roll suggestions in one pass."""
    try:
        from src.broll.matcher import suggest_broll
        from src.broll.scanner import scan_folder
        from src.ui._broll_build import _set_textbox

        _ui(lambda: w["suggest_local_btn"].configure(state="disabled"))

        folder = _state.get("folder", "").strip()
        if not folder:
            set_status("Select a folder first.", "#ff6b6b")
            return

        if not app.transcript:
            set_status("No transcript found. Generate one in the Subtitles tab first.", "#ff6b6b")
            return

        set_status(f"Scanning: {folder}…")
        clips = scan_folder(folder)
        _state["clips"] = clips

        if not clips:
            set_status("No video clips found in folder.", "#ffa726")
            _ui(lambda: _set_textbox(w["suggestions"], "No clips found in the selected folder."))
            return

        set_status(f"Found {len(clips)} clip(s). Analyzing transcript…")

        transcript_text = " ".join(
            ww["word"] for ww in app.transcript if ww.get("type") == "word"
        )
        suggestions = suggest_broll(clips, transcript_text, words=app.transcript)
        _state["suggestions"] = suggestions

        if not suggestions:
            _ui(lambda: _set_textbox(w["suggestions"],
                "No strong keyword matches found. "
                "Try clips with more descriptive filenames."))
            set_status("No matches. Rename clips with descriptive keywords.", "#ffa726")
            return

        lines = ["B-ROLL SUGGESTIONS:\n"]
        for s in suggestions:
            lines.append(
                f"  [{s['confidence']:.0%} match] {s['clip_name']}\n"
                f"    Keywords: {', '.join(s['matched_keywords'])}\n"
                f"    Suggested at: {s['suggested_time']:.1f}s\n"
            )
        set_suggestions("\n".join(lines))
        set_status(f"{len(suggestions)} suggestion(s) generated.", "#66bb6a")
    except Exception as e:
        log.error("B-roll suggest error: %s", e)
        set_status(f"Error: {e}", "#ff6b6b")
    finally:
        _ui(lambda: w["suggest_local_btn"].configure(state="normal"))


# ──────────────────────────────────────────────────────────────────────
# Online search + download workers
# ──────────────────────────────────────────────────────────────────────

def search_online_thread(
    w: dict,
    frame: Any,
    app: Any,
    _state: dict,
    providers: list[tuple[str, str]],
    set_search_status: Callable,
    set_status: Callable,
    _ui: Callable,
) -> None:
    """Extract keywords from the transcript, query the chosen provider(s),
    merge results, and open a modal results window on the UI thread when done.

    ``providers`` is a list of ``(provider_name, api_key)`` tuples. For the
    "Both" dropdown value the list contains two entries. For mock mode, the
    list is collapsed to a single MockClient that returns the same data set
    under each requested source label (offline dev only).
    """
    from src.broll.cache import BrollCache
    from src.broll.keywords import extract_top_keywords
    from src.broll.providers.base import (
        AuthError, ClipResult, EmptyResultsError, NetworkError, RateLimitError,
    )
    from src.broll.providers.mock import MockClient
    from src.broll.providers.pexels import PexelsClient
    from src.broll.providers.pixabay import PixabayClient
    from src.ui._broll_results_window import BrollResultsWindow

    try:
        if not providers:
            set_search_status("No provider selected.", "#ff6b6b")
            return

        top_n = int(round(float(w["top_n_slider"].get())))
        top_n = max(5, min(15, top_n))
        use_mock = bool(app.settings.get("broll_use_mock", False))

        if not app.transcript:
            set_search_status("No transcript. Generate one in the Subtitles tab first.", "#ff6b6b")
            return

        method = str(app.settings.get("broll_keyword_method", "spacy"))
        hint = " (may download model on first use)" if method in ("keybert", "spacy") else ""
        set_search_status(f"Extracting keywords via {method}{hint}…", "#4fc3f7")
        keywords = extract_top_keywords(app.transcript, top_n=top_n, method=method)
        if not keywords:
            set_search_status(
                "Couldn't extract keywords. Need at least a few non-stopword tokens in the transcript.",
                "#ffa726",
            )
            return

        cache = BrollCache()
        # Build a (provider_name, client) list. Mock mode: single client,
        # reused for every slot; we re-label results per slot at search time.
        if use_mock:
            mock = MockClient()
            slots: list[tuple[str, Any]] = [(name, mock) for name, _ in providers]
        else:
            slots = []
            for name, key in providers:
                if name == "Pixabay":
                    slots.append(("Pixabay", PixabayClient(key, cache=cache)))
                elif name == "Pexels":
                    slots.append(("Pexels", PexelsClient(key, cache=cache)))
                else:
                    log.warning("search_online_thread: unknown provider %r", name)

        if not slots:
            set_search_status("No valid provider slots.", "#ff6b6b")
            return

        provider_label = (
            slots[0][0] if len(slots) == 1 else f"{slots[0][0]}+{slots[1][0]}"
        )

        results_by_keyword: dict[str, list[ClipResult]] = {}
        errors: list[str] = []
        total_hits = 0

        def _sort_key(c: ClipResult) -> int:
            # Pixabay first (blue), then Pexels (orange), then anything else.
            return 0 if c.source == "pixabay" else (1 if c.source == "pexels" else 2)

        for idx, kw in enumerate(keywords, start=1):
            for slot_name, client in list(slots):
                set_search_status(
                    f"Searching {provider_label} for '{kw}' ({idx}/{len(keywords)})…",
                    "#4fc3f7",
                )
                try:
                    hits = client.search(kw, per_page=5)
                except AuthError as e:
                    errors.append(f"{slot_name}/{kw}: {e}")
                    set_search_status(
                        f"{slot_name} auth failed — disabling for this search.",
                        "#ff6b6b",
                    )
                    slots = [(n, c) for n, c in slots if n != slot_name]
                    continue
                except RateLimitError as e:
                    errors.append(f"{slot_name}/{kw}: rate limit")
                    set_search_status(
                        f"{slot_name} rate limit hit. Skipping it; "
                        f"continuing with others.",
                        "#ffa726",
                    )
                    slots = [(n, c) for n, c in slots if n != slot_name]
                    continue
                except NetworkError as e:
                    errors.append(f"{slot_name}/{kw}: {e}")
                    continue
                except EmptyResultsError as e:
                    errors.append(f"{slot_name}/{kw}: {e}")
                    continue
                except Exception as e:
                    log.error("Unexpected search error for %r on %r: %s",
                              kw, slot_name, e)
                    errors.append(f"{slot_name}/{kw}: {e}")
                    continue
                # Re-label mock results with the slot name so each slot's
                # results show the right source tag colour in the UI.
                if use_mock:
                    hits = [ClipResult(**{**c.__dict__, "source": slot_name.lower()})
                            for c in hits]
                results_by_keyword.setdefault(kw, []).extend(hits)
            # Stable order per keyword
            if kw in results_by_keyword:
                results_by_keyword[kw] = sorted(
                    results_by_keyword[kw], key=_sort_key
                )
                total_hits += len(results_by_keyword[kw])
            if not slots:
                break

        if not results_by_keyword:
            msg = "No results for any keyword."
            if errors:
                msg += f" ({len(errors)} error(s) — check log)"
            set_search_status(msg, "#ffa726")
            return

        # Store results in state so other code (debug) can inspect
        _state["online_results"] = results_by_keyword

        # Resolve target dir for the downloader
        target_dir = _state.get("dl_folder") or str(Path.home() / "broll_downloads")

        def _open() -> None:
            try:
                # master=None: frame._w is overwritten with the widget dict
                # (CLAUDE.md convention), so winfo_toplevel() breaks. None
                # uses the Tk root; grab_set() still makes the window modal.
                BrollResultsWindow(
                    master=None,
                    app=app,
                    results_by_keyword=results_by_keyword,
                    target_dir=target_dir,
                    set_status=set_status,
                    ui=_ui,
                )
            except Exception as e:
                log.exception("Results window open failed")
                set_search_status(
                    f"Results window failed to open: {e}", "#ff6b6b")

        _ui(_open)

        summary = (
            f"{total_hits} result(s) across {len(results_by_keyword)} keyword(s)"
            f" from {provider_label}."
            + (f" {len(errors)} error(s)." if errors else "")
        )
        set_search_status(summary, "#66bb6a")

    except Exception as e:
        log.error("B-roll online search error: %s", e)
        set_search_status(f"Error: {e}", "#ff6b6b")
    finally:
        # Re-enable the search button if a transcript + key is still present
        def _reenable() -> None:
            try:
                w["search_online_btn"].configure(state="normal")
            except Exception:
                pass
        _ui(_reenable)


def autonomous_thread(
    w: dict,
    frame: Any,
    app: Any,
    _state: dict,
    local_folder: str | None,
    providers: list[tuple[str, str]],
    download_folder: str,
    cloud_rerank: bool,
    clips_per_segment: int,
    max_clips: int,
    on_progress: Callable,
    set_auto_status: Callable,
    _ui: Callable,
    llm_director_mode: bool = False,
) -> None:
    """End-to-end autonomous B-roll pipeline on a daemon thread."""
    from src.broll.autonomous import run_autonomous

    try:
        result = run_autonomous(
            app=app,
            local_folder=local_folder,
            providers=providers,
            download_folder=download_folder,
            cloud_rerank=cloud_rerank,
            clips_per_segment=clips_per_segment,
            on_progress=on_progress,
            max_clips=max_clips,
            llm_director_mode=llm_director_mode,
        )

        if result.warnings:
            for warn in result.warnings:
                log.warning("[autonomous] %s", warn)

        placed = result.placed_count
        skipped = result.skipped_count
        total = placed + skipped

        if placed == 0 and total == 0:
            msg = result.warnings[0] if result.warnings else "No segments processed."
            set_auto_status(msg, "#ffa726")
        elif placed == 0:
            set_auto_status(
                f"Clips matched but not placed on timeline — check Resolve connection. "
                f"({skipped} segment(s) skipped)",
                "#ffa726",
            )
        else:
            set_auto_status(
                f"Done! {placed}/{total} segment(s) placed on B-Roll track."
                + (f" {skipped} skipped." if skipped else ""),
                "#66bb6a",
            )

    except Exception as e:
        log.error("Autonomous B-roll error: %s", e)
        set_auto_status(f"Error: {e}", "#ff6b6b")
    finally:
        _state["auto_running"] = False
        _ui(lambda: w["auto_run_btn"].configure(state="normal"))
        _ui(lambda: w["auto_progress"].pack_forget())


def download_thread(
    frame: Any,
    app: Any,
    clip: Any,
    target_dir: str,
    on_status: Callable,
    _ui: Callable,
) -> None:
    """Stream a clip to disk and import it to the Resolve media pool.

    Status updates land on the UI thread via ``on_status`` (which should
    already wrap ``frame.after(0, ...)``).
    """
    from src.broll.downloader import BrollDownloader
    from src.broll.providers.base import NetworkError

    try:
        on_status(f"Downloading {clip.title}…", "#4fc3f7")
        downloader = BrollDownloader(Path(target_dir), app)
        result = downloader.download_and_import(clip)
        on_status(
            f"Saved: {Path(result['path']).name} → media pool.",
            "#66bb6a",
        )
    except NetworkError as e:
        log.error("Download failed for %s: %s", clip.external_id, e)
        on_status(f"Download failed: {e}", "#ff6b6b")
    except Exception as e:
        log.error("Unexpected download error: %s", e)
        on_status(f"Error: {e}", "#ff6b6b")

