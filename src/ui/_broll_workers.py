"""Background thread workers for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
Each function receives all captured state as explicit parameters.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from src.constants import COLORS
from src.utils.logger import get_logger

log = get_logger(__name__)


def add_clip_row(
    suggestions_frame: Any,
    placeholder: Any,
    _state: dict,
    _ui: Callable,
    *,
    clip_path: str,
    clip_name: str,
    label: str = "",
    suggested_time: float = 0.0,
    duration_sec: float = 0.0,
    source: str = "local",
) -> None:
    """Add a single checkable clip row to the suggestions scrollable frame.

    Hides the placeholder on first row. Appends entry to _state["pinned"].
    Deduplicates by path — no-ops if clip already present.
    Must be called on the UI thread (frame.after(0, ...)).
    """
    # Deduplicate
    if any(p["path"] == clip_path for p in _state.get("pinned", [])):
        return

    if placeholder and placeholder.winfo_ismapped():
        placeholder.pack_forget()

    var = ctk.BooleanVar(value=True)

    entry: dict[str, Any] = {
        "path": clip_path,
        "clip_name": clip_name,
        "suggested_time": suggested_time,
        "duration_sec": duration_sec,
        "var": var,
        "source": source,
    }
    _state.setdefault("pinned", []).append(entry)

    row = ctk.CTkFrame(suggestions_frame, fg_color=COLORS.BG_CARD, corner_radius=4)
    row.pack(fill="x", padx=4, pady=(0, 3))
    row.grid_columnconfigure(1, weight=1)

    cb = ctk.CTkCheckBox(
        row, text="", variable=var,
        width=20, checkbox_width=16, checkbox_height=16,
    )
    cb.grid(row=0, column=0, padx=(6, 4), pady=6)

    source_color = COLORS.BRAND_PRIMARY if source == "local" else COLORS.BRAND_DIM
    source_tag = ctk.CTkLabel(
        row, text=source.upper(),
        font=ctk.CTkFont(size=9, weight="bold"),
        text_color=COLORS.BG_DARKEST, fg_color=source_color,
        corner_radius=3, width=50,
    )
    source_tag.grid(row=0, column=1, sticky="w", padx=(0, 6), pady=6)

    ctk.CTkLabel(
        row, text=clip_name,
        font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_PRIMARY, anchor="w",
    ).grid(row=0, column=2, sticky="ew", padx=(0, 6))

    time_str = f"@ {suggested_time:.1f}s"
    if duration_sec > 0:
        time_str += f"  ({duration_sec:.1f}s)"
    ctk.CTkLabel(
        row, text=time_str,
        font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_DIM, anchor="e",
    ).grid(row=0, column=3, padx=(0, 8))

    row.grid_columnconfigure(2, weight=1)

    def _remove() -> None:
        _state["pinned"] = [p for p in _state["pinned"] if p["path"] != clip_path]
        row.pack_forget()
        row.destroy()
        if not _state.get("pinned"):
            placeholder.pack(fill="x", padx=8, pady=12)

    ctk.CTkButton(
        row, text="✕", width=24, height=24,
        fg_color="transparent", hover_color=COLORS.BG_HOVER,
        text_color=COLORS.TEXT_DIM, font=ctk.CTkFont(size=10),
        command=_remove,
    ).grid(row=0, column=4, padx=(0, 4))


def suggest_local_thread(
    w: dict,
    app: Any,
    _state: dict,
    set_status: Callable,
    set_suggestions: Callable,
    _ui: Callable,
) -> None:
    """Scan folder, check transcript, then add B-roll suggestion rows to the pinned list."""
    try:
        from src.broll.matcher import suggest_broll
        from src.broll.scanner import scan_folder

        _ui(lambda: w["suggest_local_btn"].configure(state="disabled"))

        folder = _state.get("folder", "").strip()
        if not folder:
            set_status("Select a folder first.", COLORS.ERROR)
            return

        if not app.transcript:
            set_status("No transcript found. Generate one in the Subtitles tab first.", COLORS.ERROR)
            return

        set_status(f"Scanning: {folder}…")
        clips = scan_folder(folder)
        _state["clips"] = clips

        if not clips:
            set_status("No video clips found in folder.", COLORS.WARNING)
            return

        set_status(f"Found {len(clips)} clip(s). Analyzing transcript…")

        transcript_text = " ".join(
            ww["word"] for ww in app.transcript if ww.get("type") == "word"
        )
        suggestions = suggest_broll(clips, transcript_text, words=app.transcript)
        _state["suggestions"] = suggestions

        if not suggestions:
            set_status("No strong keyword matches. Try clips with more descriptive filenames.", COLORS.WARNING)
            return

        frame = w["suggestions_frame"]
        placeholder = w["suggestions_placeholder"]
        for s in suggestions:
            _ui(lambda s=s: add_clip_row(
                frame, placeholder, _state, _ui,
                clip_path=s["path"],
                clip_name=s["clip_name"],
                label=f"{s['confidence']:.0%} · {', '.join(s['matched_keywords'][:3])}",
                suggested_time=s["suggested_time"],
                duration_sec=s.get("duration_sec", 0.0),
                source="local",
            ))

        set_status(f"{len(suggestions)} suggestion(s) added — check clips to include.", COLORS.SUCCESS)
    except Exception as e:
        log.error("B-roll suggest error: %s", e)
        set_status(f"Error: {e}", COLORS.ERROR)
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
    broll_state: dict | None = None,
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
            set_search_status("No provider selected.", COLORS.ERROR)
            return

        top_n = int(round(float(w["top_n_slider"].get())))
        top_n = max(5, min(15, top_n))
        use_mock = bool(app.settings.get("broll_use_mock", False))

        if not app.transcript:
            set_search_status("No transcript. Generate one in the Subtitles tab first.", COLORS.ERROR)
            return

        method = str(app.settings.get("broll_keyword_method", "spacy"))
        hint = " (may download model on first use)" if method in ("keybert", "spacy") else ""
        set_search_status(f"Extracting keywords via {method}{hint}…", COLORS.BRAND_PRIMARY)
        keywords = extract_top_keywords(app.transcript, top_n=top_n, method=method)
        if not keywords:
            set_search_status(
                "Couldn't extract keywords. Need at least a few non-stopword tokens in the transcript.",
                COLORS.WARNING,
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
            set_search_status("No valid provider slots.", COLORS.ERROR)
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
                    COLORS.BRAND_PRIMARY,
                )
                try:
                    hits = client.search(kw, per_page=5)
                except AuthError as e:
                    errors.append(f"{slot_name}/{kw}: {e}")
                    set_search_status(
                        f"{slot_name} auth failed — disabling for this search.",
                        COLORS.ERROR,
                    )
                    slots = [(n, c) for n, c in slots if n != slot_name]
                    continue
                except RateLimitError as e:
                    errors.append(f"{slot_name}/{kw}: rate limit")
                    set_search_status(
                        f"{slot_name} rate limit hit. Skipping it; "
                        f"continuing with others.",
                        COLORS.WARNING,
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
            set_search_status(msg, COLORS.WARNING)
            return

        # Store results in state so other code (debug) can inspect
        _state["online_results"] = results_by_keyword

        # Resolve target dir for the downloader
        target_dir = _state.get("dl_folder") or str(Path.home() / "broll_downloads")

        def _open() -> None:
            try:
                BrollResultsWindow(
                    master=None,
                    app=app,
                    results_by_keyword=results_by_keyword,
                    target_dir=target_dir,
                    set_status=set_status,
                    ui=_ui,
                    w=w,
                    broll_state=broll_state,
                )
            except Exception as e:
                log.exception("Results window open failed")
                set_search_status(
                    f"Results window failed to open: {e}", COLORS.ERROR)

        _ui(_open)

        summary = (
            f"{total_hits} result(s) across {len(results_by_keyword)} keyword(s)"
            f" from {provider_label}."
            + (f" {len(errors)} error(s)." if errors else "")
        )
        set_search_status(summary, COLORS.SUCCESS)

    except Exception as e:
        log.error("B-roll online search error: %s", e)
        set_search_status(f"Error: {e}", COLORS.ERROR)
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
    fill_frame: bool = False,
    natural_placement: bool = True,
    no_start_broll: bool = True,
    intro_skip_sec: float = 4.0,
    min_gap_sec: float = 5.0,
    max_broll_duration: float = 5.0,
    llm_provider: str | None = None,
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
            llm_provider=llm_provider,
            fill_frame=fill_frame,
            natural_placement=natural_placement,
            no_start_broll=no_start_broll,
            intro_skip_sec=intro_skip_sec,
            min_gap_sec=min_gap_sec,
            max_broll_duration=max_broll_duration,
        )

        if result.warnings:
            for warn in result.warnings:
                log.warning("[autonomous] %s", warn)

        # Expose placer results for Music & SFX tab SFX engine
        placed_results = [
            sr.placer_result for sr in result.segments
            if sr.placer_result is not None and sr.placer_result.placed
        ]
        app.broll_placer_results = placed_results

        placed = result.placed_count
        skipped = result.skipped_count
        total = placed + skipped

        if placed == 0 and total == 0:
            msg = result.warnings[0] if result.warnings else "No segments processed."
            set_auto_status(msg, COLORS.WARNING)
        elif placed == 0:
            if natural_placement and skipped > 0:
                set_auto_status(
                    f"No clips placed — all segments within intro skip or gap window. "
                    f"Try disabling Natural Placement or shortening the intro skip. "
                    f"({skipped} segment(s) skipped)",
                    COLORS.WARNING,
                )
            else:
                set_auto_status(
                    f"Clips matched but not placed on timeline — check Resolve connection. "
                    f"({skipped} segment(s) skipped)",
                    COLORS.WARNING,
                )
        else:
            set_auto_status(
                f"Done! {placed}/{total} segment(s) placed on B-Roll track."
                + (f" {skipped} skipped." if skipped else ""),
                COLORS.SUCCESS,
            )

    except Exception as e:
        log.error("Autonomous B-roll error: %s", e)
        set_auto_status(f"Error: {e}", COLORS.ERROR)
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
        on_status(f"Downloading {clip.title}…", COLORS.BRAND_PRIMARY)
        downloader = BrollDownloader(Path(target_dir), app)
        result = downloader.download_and_import(clip)
        on_status(
            f"Saved: {Path(result['path']).name} → media pool.",
            COLORS.SUCCESS,
        )
    except NetworkError as e:
        log.error("Download failed for %s: %s", clip.external_id, e)
        on_status(f"Download failed: {e}", COLORS.ERROR)
    except Exception as e:
        log.error("Unexpected download error: %s", e)
        on_status(f"Error: {e}", COLORS.ERROR)

