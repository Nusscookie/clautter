"""Smart Cuts tab — silence detection and removal."""

from __future__ import annotations
import threading
from typing import Any

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="SMART CUTS  —  Remove silences from selected clips",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ── Settings card ──
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(card, text="DETECTION SETTINGS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    w["threshold"] = _labeled_entry(card, "Silence Threshold", "-35", "dB")
    w["min_dur"] = _labeled_entry(card, "Min Silence Duration", "350", "ms")
    w["padding"] = _labeled_entry(card, "Breathing Room (padding)", "120", "ms each side")

    # ── Buttons ──
    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=6)
    btn_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["analyze_btn"] = ctk.CTkButton(btn_row, text="Analyze Audio")
    w["analyze_btn"].grid(row=0, column=0, padx=(0, 3), sticky="ew")

    w["preview_btn"] = ctk.CTkButton(btn_row, text="Preview (Add Markers)",
                                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                                      state="disabled")
    w["preview_btn"].grid(row=0, column=1, padx=3, sticky="ew")

    w["apply_btn"] = ctk.CTkButton(btn_row, text="Apply Cuts (New Timeline)",
                                    fg_color="#1565c0", hover_color="#1976d2",
                                    state="disabled")
    w["apply_btn"].grid(row=0, column=2, padx=(3, 0), sticky="ew")

    # ── Progress ──
    w["progress"] = ctk.CTkProgressBar(parent, height=6)
    w["progress"].set(0)
    w["progress_frame"] = ctk.CTkFrame(parent, height=6, fg_color="transparent")
    w["progress_frame"].pack(fill="x", padx=10, pady=(2, 0))

    w["status"] = ctk.CTkLabel(
        parent,
        text="Ready. Select clips in the Edit page timeline, then click Analyze.",
        font=ctk.CTkFont(size=11),
        text_color="#aaaaaa",
        anchor="w",
        wraplength=800,
    )
    w["status"].pack(fill="x", padx=12, pady=(2, 4))

    _divider(parent)

    # ── Results ──
    ctk.CTkLabel(parent, text="ANALYSIS RESULTS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    results_row = ctk.CTkFrame(parent, fg_color="transparent")
    results_row.pack(fill="x", padx=10, pady=2)
    results_row.grid_columnconfigure((0, 1, 2), weight=1)

    w["found_count"] = _stat_card(results_row, "Silences Found", "0", "#4fc3f7")
    w["found_count"].grid(row=0, column=0, padx=(0, 4), sticky="ew")
    w["time_saved"] = _stat_card(results_row, "Estimated Time Saved", "0.0 s", "#66bb6a")
    w["time_saved"].grid(row=0, column=1, padx=4, sticky="ew")
    w["clips_count"] = _stat_card(results_row, "Clips Analyzed", "0", "#ffa726")
    w["clips_count"].grid(row=0, column=2, padx=(4, 0), sticky="ew")

    w["new_timeline_lbl"] = ctk.CTkLabel(
        parent, text="", font=ctk.CTkFont(size=11), text_color="#66bb6a", anchor="w")
    w["new_timeline_lbl"].pack(fill="x", padx=12, pady=(6, 12))

    parent._w = w


def _labeled_entry(parent: Any, label: str, default: str, unit: str) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=10, pady=2)
    row.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(row, text=label, anchor="w").grid(row=0, column=0, sticky="w")
    entry = ctk.CTkEntry(row, width=90, justify="center")
    entry.insert(0, default)
    entry.grid(row=0, column=1, padx=6)
    ctk.CTkLabel(row, text=unit, text_color="#888888",
                 font=ctk.CTkFont(size=11)).grid(row=0, column=2)
    return entry


def _stat_card(parent: Any, label: str, default: str, color: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    val = ctk.CTkLabel(card, text=default,
                       font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
    val.pack(pady=(8, 2))
    ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                 text_color="#888888").pack(pady=(0, 8))
    card._val = val
    return card


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=6)


def setup(frame: Any, app: Any) -> None:
    w = frame._w

    _state: dict[str, Any] = {
        "silence_regions": [],
        "total_silences": 0,
        "total_time_saved": 0.0,
        "clips": [],
        "timeline_choice": ("new", None),
    }

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = "#aaaaaa") -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(value: float, visible: bool = True) -> None:
        def _apply() -> None:
            if visible:
                w["progress"].pack(in_=w["progress_frame"], fill="x")
                w["progress"].set(value / 100.0)
            else:
                w["progress"].pack_forget()
        _ui(_apply)

    def set_btn(name: str, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        _ui(lambda: w[name].configure(state=state))

    def _analyze_thread() -> None:
        try:
            from src.smartcuts.analyzer import detect_silences
            from src.utils.resolve_api import get_clip_file_path

            set_btn("analyze_btn", False)
            set_btn("apply_btn", False)
            set_btn("preview_btn", False)
            set_progress(0, True)
            set_status("Refreshing timeline...")

            app.refresh_timeline()
            clips = app.get_video_clips(1)
            if not clips:
                set_status("No clips found on Video Track 1.", "#ff6b6b")
                set_progress(0, False)
                set_btn("analyze_btn", True)
                return

            threshold = float(w["threshold"].get())
            min_dur = float(w["min_dur"].get())
            padding = float(w["padding"].get())

            _state["clips"] = clips
            _state["silence_regions"] = []
            total_silences = 0
            total_ms = 0.0

            for i, clip in enumerate(clips):
                set_status(f"Analyzing clip {i + 1} / {len(clips)}...")
                set_progress(int((i / len(clips)) * 90))

                file_path = get_clip_file_path(clip)
                if not file_path:
                    _state["silence_regions"].append((clip, []))
                    continue

                try:
                    regions = detect_silences(
                        file_path,
                        threshold_db=threshold,
                        min_duration_ms=min_dur,
                        padding_ms=padding,
                    )
                except Exception as e:
                    log.error("Analysis error clip %d: %s", i, e)
                    regions = []

                _state["silence_regions"].append((clip, regions))
                total_silences += len(regions)
                total_ms += sum(r.duration_ms for r in regions)

            _state["total_silences"] = total_silences
            _state["total_time_saved"] = total_ms / 1000.0

            _ui(lambda: w["found_count"]._val.configure(text=str(total_silences)))
            _ui(lambda: w["time_saved"]._val.configure(
                text=f"{_state['total_time_saved']:.1f} s"))
            _ui(lambda: w["clips_count"]._val.configure(text=str(len(clips))))

            set_progress(100)
            if total_silences > 0:
                set_status(
                    f"Found {total_silences} silence(s) totaling "
                    f"{_state['total_time_saved']:.1f}s. Click Apply Cuts.",
                    "#66bb6a",
                )
                set_btn("apply_btn", True)
                set_btn("preview_btn", True)
            else:
                set_status("No significant silences found. Try lowering the threshold.", "#ffa726")
            set_progress(0, False)

        except Exception as e:
            log.error("Analyze thread error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
            set_progress(0, False)
        finally:
            set_btn("analyze_btn", True)

    def _apply_thread() -> None:
        try:
            from src.smartcuts.cutter import apply_cuts

            _mode, _target_tl = _state["timeline_choice"]
            set_btn("apply_btn", False)
            set_btn("analyze_btn", False)
            set_progress(0, True)
            if _target_tl is not None:
                set_status(f"Appending cuts to '{_target_tl.GetName()}'...")
            else:
                set_status("Creating new timeline with silence removed...")

            def progress_cb(current: int, total: int, msg: str) -> None:
                set_progress(int((current / max(total, 1)) * 100))
                set_status(msg)

            result = apply_cuts(
                resolve=app.resolve,
                timeline=app.timeline,
                clips=_state["clips"],
                threshold_db=float(w["threshold"].get()),
                min_duration_ms=float(w["min_dur"].get()),
                padding_ms=float(w["padding"].get()),
                progress_callback=progress_cb,
                target_timeline=_target_tl,
            )

            app.refresh_timeline()
            app.settings.add_stat("total_time_saved_sec", result.time_saved_sec)
            app.settings.add_stat("total_edits", 1)

            set_progress(100)
            set_status(
                f"Done! New timeline: '{result.new_timeline_name}' "
                f"({result.time_saved_sec:.1f}s removed)",
                "#66bb6a",
            )
            _ui(lambda: w["new_timeline_lbl"].configure(
                text=f"Created: \"{result.new_timeline_name}\""))
            set_progress(0, False)

        except Exception as e:
            log.error("Apply thread error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
            set_progress(0, False)
        finally:
            set_btn("apply_btn", True)
            set_btn("analyze_btn", True)

    def _preview_thread() -> None:
        try:
            set_btn("preview_btn", False)
            set_status("Adding markers at silence locations...")

            if not app.timeline:
                set_status("No active timeline.", "#ff6b6b")
                return

            marker_count = 0
            for clip, regions in _state["silence_regions"]:
                for region in regions:
                    frame_offset = int((region.start_ms / 1000.0) * app.fps)
                    try:
                        clip.AddMarker(
                            frame_offset, "Red", "Silence",
                            f"Silence: {region.duration_ms:.0f}ms",
                            int((region.duration_ms / 1000.0) * app.fps), "",
                        )
                        marker_count += 1
                    except Exception as me:
                        log.debug("Marker add error: %s", me)

            set_status(f"Added {marker_count} marker(s). Red markers = silences.", "#66bb6a")
        except Exception as e:
            log.error("Preview thread error: %s", e)
            set_status(f"Error: {e}", "#ff6b6b")
        finally:
            set_btn("preview_btn", True)

    def on_analyze() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_analyze_thread, daemon=True).start()

    def on_apply() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        try:
            from src.ui.timeline_dialog import show_timeline_dialog
            choice = show_timeline_dialog(frame, app.project)
        except Exception as e:
            log.error("Timeline dialog error: %s", e)
            set_status(f"Dialog error: {e}", "#ff6b6b")
            return
        if choice is None:
            return
        _state["timeline_choice"] = choice
        threading.Thread(target=_apply_thread, daemon=True).start()

    def on_preview() -> None:
        if not app.connected:
            set_status("Not connected to DaVinci Resolve.", "#ff6b6b")
            return
        threading.Thread(target=_preview_thread, daemon=True).start()

    w["analyze_btn"].configure(command=on_analyze)
    w["apply_btn"].configure(command=on_apply)
    w["preview_btn"].configure(command=on_preview)
