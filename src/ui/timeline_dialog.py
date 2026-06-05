"""Timeline selection dialog — choose existing timeline or create new one."""

from __future__ import annotations
from typing import Any, Optional

import customtkinter as ctk

from src.utils.logger import get_logger

log = get_logger(__name__)


def show_timeline_dialog(
    parent: Any,
    project: Any,
) -> Optional[tuple[str, Any]]:
    """Modal dialog: use existing timeline or create a new one.

    Returns:
        ("new", None)             — create a fresh timeline
        ("existing", timeline)    — append to the chosen existing timeline
        None                      — user cancelled
    """
    result: dict[str, Any] = {"choice": None}

    # Walk up the widget hierarchy to find the CTk root window.
    # parent._w is our widgets dict (overrides Tkinter's internal path string),
    # so winfo_toplevel() would fail — we avoid it entirely.
    root = parent
    while not isinstance(root, ctk.CTk):
        root = root.master

    root.update_idletasks()
    rx = root.winfo_x() + (root.winfo_width() - 420) // 2
    ry = root.winfo_y() + (root.winfo_height() - 230) // 2

    dialog = ctk.CTkToplevel(root)
    dialog.title("Choose Timeline")
    dialog.geometry(f"420x230+{rx}+{ry}")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.after(10, dialog.grab_set)

    # Fetch existing timelines from the project
    timelines: list[tuple[str, Any]] = []
    try:
        count = project.GetTimelineCount()
        for i in range(count):
            tl = project.GetTimelineByIndex(i + 1)
            if tl:
                timelines.append((tl.GetName(), tl))
    except Exception as e:
        log.warning("Could not fetch timeline list: %s", e)

    ctk.CTkLabel(
        dialog,
        text="Where should the result go?",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#ffffff",
    ).pack(pady=(20, 10))

    mode_var = ctk.StringVar(value="new")

    ctk.CTkRadioButton(
        dialog,
        text="Create new timeline  (safe, non-destructive)",
        variable=mode_var,
        value="new",
        text_color="#cccccc",
    ).pack(anchor="w", padx=30, pady=(0, 6))

    existing_row = ctk.CTkFrame(dialog, fg_color="transparent")
    existing_row.pack(fill="x", padx=30, pady=(0, 6))

    timeline_names = [name for name, _ in timelines]
    has_timelines = bool(timeline_names)

    ctk.CTkRadioButton(
        existing_row,
        text="Use existing timeline:",
        variable=mode_var,
        value="existing",
        state="normal" if has_timelines else "disabled",
        text_color="#cccccc",
    ).pack(side="left")

    combo = ctk.CTkComboBox(
        existing_row,
        values=timeline_names if has_timelines else ["(none available)"],
        state="readonly" if has_timelines else "disabled",
        width=190,
        fg_color="#2a2a2a",
    )
    if timeline_names:
        combo.set(timeline_names[0])
    combo.pack(side="left", padx=(10, 0))

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(pady=(14, 0))

    def on_continue() -> None:
        mode = mode_var.get()
        if mode == "existing" and has_timelines:
            sel = combo.get()
            tl_obj = next((obj for name, obj in timelines if name == sel), None)
            result["choice"] = ("existing", tl_obj) if tl_obj else ("new", None)
        else:
            result["choice"] = ("new", None)
        dialog.destroy()

    def on_cancel() -> None:
        result["choice"] = None
        dialog.destroy()

    ctk.CTkButton(
        btn_row, text="Continue", command=on_continue,
        fg_color="#1565c0", hover_color="#1976d2", width=100,
    ).pack(side="left", padx=8)

    ctk.CTkButton(
        btn_row, text="Cancel", command=on_cancel,
        fg_color="#444444", hover_color="#555555", width=80,
    ).pack(side="left", padx=8)

    dialog.wait_window()
    return result["choice"]
