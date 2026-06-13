"""Timeline selection dialog — choose existing timeline or create new one."""

from __future__ import annotations
from typing import Any, Optional

import customtkinter as ctk

from src.constants import COLORS
from src.ui.icon_helper import apply_clutter_icon
from src.utils.logger import get_logger
from src.utils.resolve_utils import find_named_video_track  # noqa: F401 — re-exported for callers

log = get_logger(__name__)


def show_timeline_dialog(
    parent: Any,
    project: Any,
    *,
    secondary_section: dict | None = None,
) -> dict | None:
    """Modal dialog: use existing timeline or create a new one.

    Args:
        secondary_section: Optional dict with keys:
            detect (bool): show extra radio group when True
            label (str): section heading text
            existing_text (str): label for "use existing" option
            new_text (str): label for "create new" option
            key (str): key for the extra choice in the return dict

    Returns:
        {
            "timeline": ("new", None) | ("existing", tl_obj),
            <key>: "existing" | "new",  # present only when secondary_section detect=True
        }
        or None if user cancelled.
    """
    result: dict[str, Any] = {"choice": None}

    show_secondary = bool(secondary_section and secondary_section.get("detect"))
    dialog_height = 330 if show_secondary else 230

    # Walk up the widget hierarchy to find the CTk root window.
    # parent._w is our widgets dict (overrides Tkinter's internal path string),
    # so winfo_toplevel() would fail — we avoid it entirely.
    root = parent
    while not isinstance(root, ctk.CTk):
        root = root.master

    root.update_idletasks()
    rx = root.winfo_x() + (root.winfo_width() - 420) // 2
    ry = root.winfo_y() + (root.winfo_height() - dialog_height) // 2

    dialog = ctk.CTkToplevel(root)
    apply_clutter_icon(dialog)
    dialog.title("Choose Timeline")
    dialog.geometry(f"420x{dialog_height}+{rx}+{ry}")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes('-topmost', True)
    dialog.after(200, lambda: dialog.attributes('-topmost', False))
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
        text_color=COLORS.TEXT_PRIMARY,
    ).pack(pady=(20, 10))

    mode_var = ctk.StringVar(value="new")

    ctk.CTkRadioButton(
        dialog,
        text="Create new timeline  (safe, non-destructive)",
        variable=mode_var,
        value="new",
        text_color=COLORS.TEXT_SECONDARY,
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
        text_color=COLORS.TEXT_SECONDARY,
    ).pack(side="left")

    combo = ctk.CTkComboBox(
        existing_row,
        values=timeline_names if has_timelines else ["(none available)"],
        state="readonly" if has_timelines else "disabled",
        width=190,
        fg_color=COLORS.BG_CARD,
    )
    if timeline_names:
        combo.set(timeline_names[0])
    combo.pack(side="left", padx=(10, 0))

    # Optional secondary section (e.g. subtitle layer or retake layer choice)
    track_var: ctk.StringVar | None = None
    if show_secondary:
        sec = secondary_section  # type: ignore[assignment]
        ctk.CTkFrame(dialog, height=1, fg_color=COLORS.SEPARATOR).pack(
            fill="x", padx=20, pady=(12, 0)
        )
        ctk.CTkLabel(
            dialog,
            text=sec["label"],
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS.TEXT_DIM,
        ).pack(anchor="w", padx=30, pady=(8, 4))
        track_var = ctk.StringVar(value="new")
        ctk.CTkRadioButton(
            dialog,
            text=sec["existing_text"],
            variable=track_var,
            value="existing",
            text_color=COLORS.TEXT_SECONDARY,
        ).pack(anchor="w", padx=30, pady=(0, 4))
        ctk.CTkRadioButton(
            dialog,
            text=sec["new_text"],
            variable=track_var,
            value="new",
            text_color=COLORS.TEXT_SECONDARY,
        ).pack(anchor="w", padx=30, pady=(0, 6))

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(pady=(14, 0))

    def on_continue() -> None:
        mode = mode_var.get()
        if mode == "existing" and has_timelines:
            sel = combo.get()
            tl_obj = next((obj for name, obj in timelines if name == sel), None)
            tl_choice = ("existing", tl_obj) if tl_obj else ("new", None)
        else:
            tl_choice = ("new", None)
        ret: dict[str, Any] = {"timeline": tl_choice}
        if show_secondary and track_var is not None and secondary_section:
            ret[secondary_section["key"]] = track_var.get()
        result["choice"] = ret
        dialog.destroy()

    def on_cancel() -> None:
        result["choice"] = None
        dialog.destroy()

    ctk.CTkButton(
        btn_row, text="Continue", command=on_continue,
        fg_color=COLORS.BTN_PRIMARY_BG, hover_color=COLORS.BTN_PRIMARY_HOVER, width=100,
    ).pack(side="left", padx=8)

    ctk.CTkButton(
        btn_row, text="Cancel", command=on_cancel,
        fg_color=COLORS.SEPARATOR, hover_color=COLORS.TEXT_SUBTLE, width=80,
    ).pack(side="left", padx=8)

    dialog.wait_window()
    return result["choice"]
