"""B-Roll Assistant tab — Manual and Autonomous modes."""

from __future__ import annotations
import threading
import tkinter.filedialog
from pathlib import Path
from typing import Any

from src.constants import COLORS, SETTINGS_KEYS
from src.broll.placement_rules import MIN_COLLISION_GAP, cap_duration, should_place
from src.ui._broll_build import build
from src.ui._broll_workers import (
    suggest_local_thread, search_online_thread, autonomous_thread,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "folder": "",
        "dl_folder": "",
        "auto_folder": "",
        "auto_dl_folder": "",
        "clips": [],
        "suggestions": [],
        "pinned": [],
        "auto_running": False,
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_search_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["search_status"].configure(text=msg, text_color=color))

    def set_auto_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["auto_status"].configure(text=msg, text_color=color))

    def _set_readonly_entry(entry: Any, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.configure(state="readonly")

    # ── Mode toggle ─────────────────────────────────────────────────

    def on_mode_change(value: str) -> None:
        app.settings.set("broll_mode", value)
        if value == "Manual":
            w["auto_container"].pack_forget()
            w["manual_container"].pack(fill="x")
        else:
            w["manual_container"].pack_forget()
            w["auto_container"].pack(fill="x")
            _refresh_auto_run_btn()

    w["mode_toggle"].configure(command=on_mode_change)

    # ── Hydrate manual settings ─────────────────────────────────────
    saved_provider = str(app.settings.get("broll_provider", "Both"))
    if saved_provider not in ("Pixabay", "Pexels", "Both"):
        saved_provider = "Both"
    _ui(lambda: w["provider"].set(saved_provider))

    saved_top_n = int(app.settings.get("broll_top_n", 10) or 10)
    saved_top_n = max(5, min(15, saved_top_n))
    _ui(lambda v=saved_top_n: (
        w["top_n_slider"].set(v),
        w["top_n_value"].configure(text=str(int(v))),
    ))

    saved_dl = str(app.settings.get("last_broll_folder", "") or "")
    if not saved_dl:
        saved_dl = str(Path.home() / "broll_downloads")
    _state["dl_folder"] = saved_dl
    _ui(lambda v=saved_dl: _set_readonly_entry(w["dl_folder"], v))

    # ── Hydrate autonomous settings ─────────────────────────────────
    auto_local = bool(app.settings.get("broll_auto_use_local", True))
    auto_online = bool(app.settings.get("broll_auto_use_online", True))
    from src.utils.llm_providers import available_providers
    auto_cps = str(app.settings.get("broll_auto_clips_per_segment", 1))
    auto_provider = str(app.settings.get("broll_auto_provider", "Both"))
    auto_dl = str(app.settings.get("broll_auto_dl_folder", "") or str(Path.home() / "broll_downloads"))
    auto_folder = str(app.settings.get("last_broll_folder", ""))
    auto_max_clips = int(app.settings.get("broll_auto_max_clips", 10) or 10)
    auto_max_clips = max(1, min(30, auto_max_clips))

    _state["auto_dl_folder"] = auto_dl
    _state["auto_folder"] = auto_folder

    auto_fill_frame = bool(app.settings.get(SETTINGS_KEYS.BROLL_FILL_FRAME, False))
    auto_natural = bool(app.settings.get(SETTINGS_KEYS.BROLL_NATURAL_PLACEMENT, True))

    def _refresh_llm_mode() -> None:
        """Populate the autonomous LLM-mode dropdown from currently-keyed providers."""
        vals = ["Off"] + available_providers(app.settings)
        try:
            current = w["auto_llm_mode"].get()
        except Exception:
            current = ""
        saved = str(app.settings.get("broll_llm_mode", "Off"))
        chosen = current if current in vals else (saved if saved in vals else "Off")
        _ui(lambda: (
            w["auto_llm_mode"].configure(values=vals),
            w["auto_llm_mode"].set(chosen),
        ))

    def _refresh_place_llm_mode() -> None:
        """Populate the manual place LLM-mode dropdown from currently-keyed providers."""
        vals = ["Off"] + available_providers(app.settings)
        try:
            current = w["place_llm_mode"].get()
        except Exception:
            current = ""
        saved = str(app.settings.get("broll_place_llm_mode", "Off"))
        chosen = current if current in vals else (saved if saved in vals else "Off")
        _ui(lambda: (
            w["place_llm_mode"].configure(values=vals),
            w["place_llm_mode"].set(chosen),
        ))

    def _hydrate_auto() -> None:
        if auto_local:
            w["auto_use_local"].select()
        if auto_online:
            w["auto_use_online"].select()
        _refresh_llm_mode()
        if auto_cps in ("1", "2", "3"):
            w["auto_clips_per_seg"].set(auto_cps)
        if auto_provider in ("Pixabay", "Pexels", "Both"):
            w["auto_provider"].set(auto_provider)
        if auto_dl:
            _set_readonly_entry(w["auto_dl_folder"], auto_dl)
        if auto_folder:
            _set_readonly_entry(w["auto_folder"], auto_folder)
        w["auto_max_clips"].set(auto_max_clips)
        w["auto_max_clips_value"].configure(text=str(int(auto_max_clips)))
        if auto_fill_frame:
            w["auto_fill_frame"].select()
        if auto_natural:
            w["auto_natural_placement"].select()

    _ui(_hydrate_auto)

    # ── Restore mode ─────────────────────────────────────────────────
    saved_mode = str(app.settings.get("broll_mode", "Manual"))
    if saved_mode not in ("Manual", "Autonomous"):
        saved_mode = "Manual"

    def _restore_mode() -> None:
        w["mode_toggle"].set(saved_mode)
        on_mode_change(saved_mode)

    _ui(_restore_mode)

    # ── Manual callbacks ────────────────────────────────────────────

    def on_browse() -> None:
        initial = str(app.settings.get("last_broll_folder", "") or Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select B-Roll folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["folder"] = path
        _set_readonly_entry(w["folder"], path)
        app.settings.set("last_broll_folder", path)
        set_status(f"Selected: {path}", COLORS.BRAND_PRIMARY)
        _ui(lambda: w["suggest_local_btn"].configure(state="normal"))

    def on_pick_dl_folder() -> None:
        initial = _state["dl_folder"] or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select download folder for B-roll clips",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["dl_folder"] = path
        _set_readonly_entry(w["dl_folder"], path)
        app.settings.set("last_broll_folder", path)
        set_search_status(f"Download folder: {path}", COLORS.BRAND_PRIMARY)

    def on_provider_change(value: str) -> None:
        app.settings.set("broll_provider", value)
        _refresh_search_button()

    def on_top_n_change(value: Any) -> None:
        n = int(round(float(value)))
        w["top_n_value"].configure(text=str(n))
        app.settings.set("broll_top_n", n)

    def _refresh_search_button() -> None:
        # Always enabled — missing keys / transcript handled with inline errors on click
        _ui(lambda: w["search_online_btn"].configure(state="normal"))

    def set_place_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["place_status"].configure(text=msg, text_color=color))

    place_fill_frame_saved = bool(app.settings.get("broll_place_fill_frame", False))
    if place_fill_frame_saved:
        _ui(lambda: w["place_fill_frame"].select())

    place_natural_saved = bool(app.settings.get("broll_place_natural_placement", True))
    if place_natural_saved:
        _ui(lambda: w["place_natural_placement"].select())

    place_max_dur_saved = float(app.settings.get("broll_place_max_dur", 5.0) or 5.0)
    place_max_dur_saved = max(1.0, min(15.0, place_max_dur_saved))
    _ui(lambda v=place_max_dur_saved: (
        w["place_max_dur"].set(v),
        w["place_max_dur_value"].configure(text=f"{int(v)}s"),
    ))

    def on_place_fill_frame_change() -> None:
        app.settings.set("broll_place_fill_frame", bool(w["place_fill_frame"].get()))

    def on_place_natural_change() -> None:
        app.settings.set("broll_place_natural_placement", bool(w["place_natural_placement"].get()))

    def on_place_max_dur_change(value: Any) -> None:
        n = int(round(float(value)))
        w["place_max_dur_value"].configure(text=f"{n}s")
        app.settings.set("broll_place_max_dur", n)

    def on_place_llm_mode_change(value: str) -> None:
        app.settings.set("broll_place_llm_mode", value)

    def _refresh_place_btn() -> None:
        # Enable when at least one clip is pinned (checked). Runs on UI thread.
        pinned = _state.get("pinned", [])
        has_checked = any(p["var"].get() for p in pinned)
        w["place_btn"].configure(state="normal" if has_checked else "disabled")

    def on_place() -> None:
        # Only place clips the user explicitly checked
        pinned = _state.get("pinned", [])
        to_place = [p for p in pinned if p["var"].get()]
        if not to_place:
            set_place_status("No clips checked — tick clips in the list above.", COLORS.ERROR)
            return
        if not app.transcript:
            set_place_status("No transcript — generate one in the Subtitles tab first.", COLORS.ERROR)
            return

        llm_sel = w["place_llm_mode"].get()
        llm_director = llm_sel != "Off"
        llm_provider = llm_sel if llm_director else None
        fill_frame = bool(w["place_fill_frame"].get())
        max_dur = float(w["place_max_dur"].get())
        natural_placement = bool(w["place_natural_placement"].get())
        intro_skip_sec = float(app.settings.get(SETTINGS_KEYS.BROLL_INTRO_SKIP, 4.0))
        min_gap_sec = float(app.settings.get(SETTINGS_KEYS.BROLL_MIN_GAP, 5.0))

        _ui(lambda: w["place_btn"].configure(state="disabled"))
        set_place_status("Placing clips on B-Roll track…", COLORS.BRAND_PRIMARY)

        def _place_thread() -> None:
            try:
                from src.broll.placer import place_clip

                # Build placements list. All checked clips are placed — no omissions.
                # LLM mode only re-assigns timestamps; it cannot drop clips.
                if llm_director and llm_provider:
                    try:
                        from src.broll.keywords import extract_top_keywords
                        from src.broll.llm_director import direct
                        from src.broll.matcher import _build_segments

                        keywords = extract_top_keywords(app.transcript, top_n=10)
                        segments = _build_segments(app.transcript)
                        candidates = [
                            {"name": p["clip_name"], "path": p["path"],
                             "keywords": [],
                             "duration_sec": p.get("duration_sec", 0.0)}
                            for p in to_place
                        ]
                        decisions, err = direct(
                            transcript_words=app.transcript,
                            segments=segments,
                            keywords=keywords,
                            candidates=candidates,
                            settings=app.settings,
                            provider=llm_provider,
                            max_placements=len(to_place),
                        )
                        if err:
                            log.warning("[place] LLM director: %s — using original timestamps", err)
                            set_place_status(
                                f"LLM failed ({err}) — placing at original timestamps.", COLORS.WARNING)
                            decisions = []

                        if decisions:
                            # Build a name→LLM-timestamp lookup; keep user-order for any clip
                            # the LLM didn't return (ensures ALL checked clips are placed).
                            llm_times: dict[str, tuple[float, float]] = {
                                d.clip_name: (d.timeline_sec,
                                              max(0.0, d.clip_end_sec - d.clip_start_sec))
                                for d in decisions
                            }
                            placements = []
                            for p in to_place:
                                if p["clip_name"] in llm_times:
                                    t, dur = llm_times[p["clip_name"]]
                                else:
                                    t = p.get("suggested_time", 0.0)
                                    dur = p.get("duration_sec", 0.0)
                                placements.append({
                                    "path": p["path"], "start_sec": t, "duration_sec": dur,
                                })
                        else:
                            placements = [
                                {"path": p["path"],
                                 "start_sec": p.get("suggested_time", 0.0),
                                 "duration_sec": p.get("duration_sec", 0.0)}
                                for p in to_place
                            ]
                    except Exception as e:
                        log.warning("[place] LLM director failed (%s) — using original timestamps", e)
                        placements = [
                            {"path": p["path"],
                             "start_sec": p.get("suggested_time", 0.0),
                             "duration_sec": p.get("duration_sec", 0.0)}
                            for p in to_place
                        ]
                else:
                    placements = [
                        {"path": p["path"],
                         "start_sec": p.get("suggested_time", 0.0),
                         "duration_sec": p.get("duration_sec", 0.0)}
                        for p in to_place
                    ]

                # Apply max clip duration cap before collision check so the
                # collision math uses the already-capped durations. A clip with
                # unknown (<=0) duration falls back to the full cap.
                for p in placements:
                    p["duration_sec"] = cap_duration(
                        p.get("duration_sec") or 0.0, max_dur, zero_means_full=True,
                    )

                # Natural placement: filter out clips in the intro window and
                # enforce minimum gap between placed clips (shared predicate).
                if natural_placement:
                    filtered = []
                    last_end = 0.0
                    for p in sorted(placements, key=lambda x: x["start_sec"]):
                        t = p["start_sec"]
                        ok, reason = should_place(
                            t, last_end,
                            natural_placement=True, no_start_broll=True,
                            intro_skip_sec=intro_skip_sec, min_gap_sec=min_gap_sec,
                        )
                        if not ok:
                            log.debug("[place] natural: skipping %s — %s", p["path"], reason)
                            continue
                        filtered.append(p)
                        last_end = t + (p.get("duration_sec") or 0.0)
                    dropped = len(placements) - len(filtered)
                    placements = filtered
                else:
                    dropped = 0

                # Resolve won't place two clips at the same record frame.
                # Sort by start time, then bump any clip that overlaps the
                # previous one so all checked clips are placed.
                placements.sort(key=lambda p: p["start_sec"])
                for i in range(1, len(placements)):
                    prev = placements[i - 1]
                    cur = placements[i]
                    prev_end = prev["start_sec"] + max(prev.get("duration_sec") or 0.0, MIN_COLLISION_GAP)
                    if cur["start_sec"] < prev_end:
                        cur["start_sec"] = prev_end
                        log.debug("[place] collision fix: shifted clip %d to %.1fs", i, cur["start_sec"])

                placed = 0
                skipped = 0
                total = len(placements)
                for p in placements:
                    result = place_clip(
                        app=app,
                        clip_path=p["path"],
                        segment_start_sec=p["start_sec"],
                        clip_duration_sec=p.get("duration_sec", 0.0),
                        fill_frame=fill_frame,
                    )
                    if result.placed:
                        placed += 1
                    else:
                        skipped += 1
                        log.warning("[place] skipped %s: %s", p["path"], result.reason)

                natural_note = (
                    f" {dropped} skipped by Natural Placement (intro/gap rules)."
                    if dropped else ""
                )
                if placed == 0 and total == 0:
                    set_place_status(
                        "No clips to place." + natural_note, COLORS.WARNING)
                elif placed == 0:
                    set_place_status(
                        f"No clips placed — check Resolve connection. ({skipped} skipped){natural_note}",
                        COLORS.ERROR,
                    )
                else:
                    set_place_status(
                        f"Done! {placed}/{total} clip(s) placed on B-Roll track."
                        + (f" {skipped} skipped." if skipped else "")
                        + natural_note,
                        COLORS.SUCCESS,
                    )
                app.broll_placer_results = []
            except Exception as e:
                log.error("Manual place error: %s", e)
                set_place_status(f"Error: {e}", COLORS.ERROR)
            finally:
                _ui(lambda: w["place_btn"].configure(state="normal"))

        threading.Thread(target=_place_thread, daemon=True).start()

    def on_search_online() -> None:
        if not app.transcript:
            set_search_status("No transcript. Generate one in the Subtitles tab first.", COLORS.ERROR)
            return
        provider = w["provider"].get()
        pairs: list[tuple[str, str]] = []
        missing: list[str] = []
        if provider in ("Pixabay", "Both"):
            k = (app.settings.get("pixabay_api_key", "") or "").strip()
            if k:
                pairs.append(("Pixabay", k))
            else:
                missing.append("Pixabay")
        if provider in ("Pexels", "Both"):
            k = (app.settings.get("pexels_api_key", "") or "").strip()
            if k:
                pairs.append(("Pexels", k))
            else:
                missing.append("Pexels")
        if missing:
            set_search_status(
                f"Missing key(s): {', '.join(missing)}. Add in Settings (⚙ top-right).",
                COLORS.ERROR,
            )
            return
        if not pairs:
            set_search_status("Select a provider first.", COLORS.ERROR)
            return
        _ui(lambda: w["search_online_btn"].configure(state="disabled"))
        set_search_status("Searching…", COLORS.BRAND_PRIMARY)
        threading.Thread(
            target=search_online_thread,
            args=(w, frame, app, _state, pairs,
                  set_search_status, set_status, _ui),
            kwargs={"broll_state": _state},
            daemon=True,
        ).start()

    # ── Autonomous callbacks ────────────────────────────────────────

    def _refresh_auto_run_btn() -> None:
        use_local = w["auto_use_local"].get()
        use_online = w["auto_use_online"].get()
        has_folder = bool(_state.get("auto_folder", "").strip())
        has_dl = bool(_state.get("auto_dl_folder", "").strip())
        has_transcript = bool(app.transcript)

        ok = (
            has_transcript
            and (not use_local or has_folder)
            and (not use_online or has_dl)
            and (use_local or use_online)
        )
        _ui(lambda s=("normal" if ok else "disabled"):
            w["auto_run_btn"].configure(state=s))

    def on_auto_browse() -> None:
        initial = _state.get("auto_folder", "") or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select local B-Roll folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["auto_folder"] = path
        _set_readonly_entry(w["auto_folder"], path)
        app.settings.set("last_broll_folder", path)
        _refresh_auto_run_btn()

    def on_auto_dl_browse() -> None:
        initial = _state.get("auto_dl_folder", "") or str(Path.home())
        path = tkinter.filedialog.askdirectory(
            title="Select download folder",
            initialdir=initial,
            mustexist=True,
        )
        if not path:
            return
        _state["auto_dl_folder"] = path
        _set_readonly_entry(w["auto_dl_folder"], path)
        app.settings.set("broll_auto_dl_folder", path)
        _refresh_auto_run_btn()

    def on_auto_source_change() -> None:
        app.settings.set("broll_auto_use_local", bool(w["auto_use_local"].get()))
        app.settings.set("broll_auto_use_online", bool(w["auto_use_online"].get()))
        _refresh_auto_run_btn()

    def on_auto_llm_mode_change(value: str) -> None:
        app.settings.set("broll_llm_mode", value)

    def on_auto_provider_change(value: str) -> None:
        app.settings.set("broll_auto_provider", value)

    def on_auto_cps_change(value: str) -> None:
        app.settings.set("broll_auto_clips_per_segment", int(value))

    def on_auto_max_clips_change(value: Any) -> None:
        n = int(round(float(value)))
        w["auto_max_clips_value"].configure(text=str(n))
        app.settings.set("broll_auto_max_clips", n)

    def on_auto_fill_frame_change() -> None:
        app.settings.set(SETTINGS_KEYS.BROLL_FILL_FRAME, bool(w["auto_fill_frame"].get()))

    def on_auto_natural_change() -> None:
        app.settings.set(SETTINGS_KEYS.BROLL_NATURAL_PLACEMENT, bool(w["auto_natural_placement"].get()))

    def on_auto_run() -> None:
        if _state.get("auto_running"):
            return
        if not app.transcript:
            set_auto_status("No transcript — generate one in the Subtitles tab first.", COLORS.ERROR)
            return

        use_local = bool(w["auto_use_local"].get())
        use_online = bool(w["auto_use_online"].get())
        local_folder = _state.get("auto_folder", "").strip() if use_local else None
        dl_folder = _state.get("auto_dl_folder", "").strip() or str(Path.home() / "broll_downloads")

        provider_val = w["auto_provider"].get()
        providers: list[tuple[str, str]] = []
        if use_online:
            if provider_val in ("Pixabay", "Both"):
                k = (app.settings.get("pixabay_api_key", "") or "").strip()
                if k:
                    providers.append(("Pixabay", k))
            if provider_val in ("Pexels", "Both"):
                k = (app.settings.get("pexels_api_key", "") or "").strip()
                if k:
                    providers.append(("Pexels", k))

        llm_sel = w["auto_llm_mode"].get()
        llm_director = llm_sel != "Off"
        llm_provider = llm_sel if llm_director else None
        cloud_rerank = False
        clips_per_seg = int(w["auto_clips_per_seg"].get() or 1)
        max_clips = int(round(float(w["auto_max_clips"].get())))
        fill_frame = bool(w["auto_fill_frame"].get())
        natural_placement = bool(w["auto_natural_placement"].get())
        no_start_broll = bool(app.settings.get(SETTINGS_KEYS.BROLL_NO_START, True))
        intro_skip_sec = float(app.settings.get(SETTINGS_KEYS.BROLL_INTRO_SKIP, 4.0))
        min_gap_sec = float(app.settings.get(SETTINGS_KEYS.BROLL_MIN_GAP, 5.0))
        max_broll_duration = float(app.settings.get(SETTINGS_KEYS.BROLL_MAX_DUR, 5.0))

        _state["auto_running"] = True
        _ui(lambda: w["auto_run_btn"].configure(state="disabled"))
        _ui(lambda: w["auto_progress"].pack(in_=w["auto_progress_frame"], fill="x"))
        _ui(lambda: w["auto_progress"].set(0))

        def _on_progress(msg: str, frac: float) -> None:
            set_auto_status(msg)
            _ui(lambda f=frac: w["auto_progress"].set(f))

        threading.Thread(
            target=autonomous_thread,
            args=(w, frame, app, _state, local_folder, providers, dl_folder,
                  cloud_rerank, clips_per_seg, max_clips, _on_progress, set_auto_status, _ui,
                  llm_director, fill_frame, natural_placement, no_start_broll,
                  intro_skip_sec, min_gap_sec, max_broll_duration, llm_provider),
            daemon=True,
        ).start()

    # ── Wire commands ───────────────────────────────────────────────
    # Manual
    w["browse_btn"].configure(command=on_browse)
    w["dl_folder_btn"].configure(command=on_pick_dl_folder)
    w["provider"].configure(command=on_provider_change)
    w["top_n_slider"].configure(command=on_top_n_change)
    def _suggest_and_refresh() -> None:
        def _after() -> None:
            suggest_local_thread(w, app, _state, set_status, None, _ui)
            _ui(_refresh_place_btn)
        threading.Thread(target=_after, daemon=True).start()

    w["suggest_local_btn"].configure(command=_suggest_and_refresh)
    w["place_fill_frame"].configure(command=on_place_fill_frame_change)
    w["place_natural_placement"].configure(command=on_place_natural_change)
    w["place_max_dur"].configure(command=on_place_max_dur_change)
    w["place_btn"].configure(command=on_place)
    w["place_llm_mode"].configure(command=on_place_llm_mode_change)
    w["search_online_btn"].configure(command=on_search_online)

    # Autonomous
    w["auto_browse_btn"].configure(command=on_auto_browse)
    w["auto_dl_browse_btn"].configure(command=on_auto_dl_browse)
    w["auto_use_local"].configure(command=on_auto_source_change)
    w["auto_use_online"].configure(command=on_auto_source_change)
    w["auto_llm_mode"].configure(command=on_auto_llm_mode_change)
    w["auto_provider"].configure(command=on_auto_provider_change)
    w["auto_clips_per_seg"].configure(command=on_auto_cps_change)
    w["auto_max_clips"].configure(command=on_auto_max_clips_change)
    w["auto_fill_frame"].configure(command=on_auto_fill_frame_change)
    w["auto_natural_placement"].configure(command=on_auto_natural_change)
    w["auto_run_btn"].configure(command=on_auto_run)

    # Initial state
    _refresh_search_button()
    _refresh_auto_run_btn()
    _refresh_place_llm_mode()

    # Live refresh when Settings → Apply adds/changes a key (no restart needed)
    app.on_settings_changed(_refresh_llm_mode)
    app.on_settings_changed(_refresh_place_llm_mode)
    app.on_settings_changed(_refresh_search_button)
    app.on_settings_changed(_refresh_auto_run_btn)
