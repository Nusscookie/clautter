"""Enhance Audio tab — clean up noisy source audio onto a dedicated track.

All engines are optional — each shows an info/confirm modal on first use.
Audio clips on track 1 are enhanced clip-by-clip (trimmed segment, not the
full source file), placed on the "Enhanced" audio track, and the original
audio track is muted after placement. Auphonic cloud polish is a disabled stub.
"""

from __future__ import annotations

import threading
import webbrowser
from typing import Any

import customtkinter as ctk

from src.constants import COLORS
from src.enhance_audio import dep_installer, engines
from src.ui._enhance_audio_build import build  # noqa: F401  (re-exported for main_window)
from src.ui._enhance_audio_workers import worker_thread
from src.ui.icon_helper import apply_clautter_icon
from src.utils.logger import get_logger

log = get_logger(__name__)


def setup(frame: Any, app: Any) -> None:
    w = frame._w
    _state: dict[str, Any] = {"running": False}

    def _ui(fn: Any) -> None:
        frame.after(0, fn)

    def set_status(msg: str, color: str = COLORS.TEXT_MUTED) -> None:
        _ui(lambda: w["status"].configure(text=msg, text_color=color))

    def set_progress(pct: int, visible: bool = True) -> None:
        def _do() -> None:
            if visible:
                w["progress"].pack(in_=w["progress_frame"], fill="x")
                w["progress"].set(pct / 100)
            else:
                w["progress"].pack_forget()
        _ui(_do)

    # ── Strength slider ──────────────────────────────────────────────
    def on_strength(val: float) -> None:
        pct = int(val)
        w["strength_lbl"].configure(text=f"{pct}%")
        app.settings.set("enhance_strength", pct)

    w["strength_slider"].configure(command=on_strength)

    # ── Scope toggle ─────────────────────────────────────────────────
    def on_scope(value: str) -> None:
        app.settings.set("enhance_scope", "all" if value == "All Clips" else "selected")

    w["scope"].configure(command=on_scope)

    # ── Engine checkboxes → persist selection ───────────────────────
    def _save_engines() -> None:
        selected = [eid for eid, var in w["engine_vars"].items() if var.get()]
        app.settings.set("enhance_engines", selected)

    for eid in w["engine_vars"]:
        w[f"engine_cb_{eid}"].configure(command=_save_engines)

    # ── Hydrate settings ─────────────────────────────────────────────
    saved_strength = max(0, min(100, int(app.settings.get("enhance_strength", 50) or 50)))
    _ui(lambda: (
        w["strength_slider"].set(saved_strength),
        w["strength_lbl"].configure(text=f"{saved_strength}%"),
    ))

    saved_scope = str(app.settings.get("enhance_scope", "selected") or "selected")
    _ui(lambda: w["scope"].set("All Clips" if saved_scope == "all" else "Selected Clip"))

    saved_engines = app.settings.get("enhance_engines", None)
    if isinstance(saved_engines, list):
        _ui(lambda: [
            var.set(1 if eid in saved_engines else 0)
            for eid, var in w["engine_vars"].items()
        ])

    # ── Run ──────────────────────────────────────────────────────────
    def on_run() -> None:
        if _state["running"]:
            return

        engine_ids = [eid for eid, var in w["engine_vars"].items() if var.get()]
        if not engine_ids:
            set_status("Select at least one engine.", COLORS.ERROR)
            return

        # Optional engines that need installing → confirm modal (CPU warning).
        need_install: list[tuple[str, str, str]] = []  # (label, pip_pkg, note)
        for eid in engine_ids:
            spec = engines.get_engine(eid)
            if spec and not dep_installer.is_installed(spec.import_name):
                need_install.append((spec.label, spec.pip_pkg, spec.install_note))

        if need_install and not _confirm_install(_root_of(frame), need_install):
            set_status("Cancelled — optional engine not installed.", COLORS.TEXT_MUTED)
            return

        install_pkgs = [pkg for _label, pkg, _note in need_install]
        strength = int(w["strength_slider"].get()) / 100.0
        scope = "all" if w["scope"].get() == "All Clips" else "selected"

        _save_engines()
        _state["running"] = True
        _ui(lambda: w["run_btn"].configure(state="disabled"))

        threading.Thread(
            target=worker_thread,
            kwargs=dict(
                frame=frame, app=app, state=_state,
                engine_ids=engine_ids, strength=strength, scope=scope,
                install_pkgs=install_pkgs,
                set_status=set_status, set_progress=set_progress, _ui=_ui, w=w,
            ),
            daemon=True,
        ).start()

    w["run_btn"].configure(command=on_run)


def _root_of(widget: Any) -> Any:
    """Walk up to the CTk root window.

    ``parent._w`` holds our widgets dict (it shadows tkinter's internal path
    string), so ``winfo_toplevel()`` raises — see timeline_dialog. Walk ``.master``
    instead, which is unaffected.
    """
    node = widget
    while not isinstance(node, ctk.CTk):
        node = node.master
    return node


def _confirm_install(master: Any, items: list[tuple[str, str, str]]) -> bool:
    """Modal yes/no warning before installing CPU-heavy optional engines.

    Runs on the tkinter main thread. Returns True if the user confirms.
    """
    dlg = ctk.CTkToplevel(master)
    apply_clautter_icon(dlg)
    dlg.title("Engine Info / Install")
    dlg.resizable(True, True)
    dlg.transient(master)
    dlg.lift()
    dlg.focus_force()
    dlg.attributes("-topmost", True)
    dlg.after(200, lambda: dlg.attributes("-topmost", False))
    dlg.after(10, dlg.grab_set)

    result = {"ok": False}

    ctk.CTkLabel(
        dlg, text="⚠  Engine information",
        font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS.WARNING, anchor="w",
    ).pack(fill="x", padx=20, pady=(18, 6))

    lines = "\n\n".join(f"• {label}\n   {note}" for label, _pkg, note in items)
    ctk.CTkLabel(
        dlg,
        text="The following engine(s) may need a one-time install. "
             "Read the notes below before continuing:\n\n" + lines,
        font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_SECONDARY,
        anchor="w", justify="left", wraplength=480,
    ).pack(fill="x", padx=20, pady=(0, 10))

    # Show Rust install link if any selected engine requires it (deepfilternet needs cargo).
    needs_rust = any(pkg == "deepfilternet" for _label, pkg, _note in items)
    if needs_rust:
        rust_row = ctk.CTkFrame(dlg, fg_color="transparent")
        rust_row.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(
            rust_row, text="Rust toolchain required for Python 3.12+:  ",
            font=ctk.CTkFont(size=11), text_color=COLORS.TEXT_MUTED,
        ).pack(side="left")
        lnk = ctk.CTkLabel(
            rust_row, text="https://rustup.rs",
            font=ctk.CTkFont(size=11, underline=True),
            text_color=COLORS.BRAND_PRIMARY, cursor="hand2",
        )
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda _e: webbrowser.open("https://rustup.rs"))

    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(pady=(4, 16))

    def _ok() -> None:
        result["ok"] = True
        dlg.destroy()

    ctk.CTkButton(
        btn_row, text="Install & Continue", width=170,
        fg_color=COLORS.BTN_PRIMARY_BG, hover_color=COLORS.BTN_PRIMARY_HOVER, command=_ok,
    ).pack(side="left", padx=6)
    ctk.CTkButton(
        btn_row, text="Cancel", width=90,
        fg_color=COLORS.SEPARATOR, hover_color=COLORS.TEXT_SUBTLE,
        text_color=COLORS.TEXT_MUTED, command=dlg.destroy,
    ).pack(side="left", padx=6)

    # Estimate height: header ~60px + ~130px per engine item + rust row ~30px + button row ~80px.
    est_h = 60 + len(items) * 130 + (30 if needs_rust else 0) + 80
    dlg.geometry(f"560x{min(max(est_h, 360), 800)}")

    dlg.wait_window()
    return result["ok"]
