"""Timeline selection dialog — choose existing timeline or create new one."""

from __future__ import annotations
from typing import Any, Optional

import customtkinter as ctk

from src.constants import COLORS
from src.ui.icon_helper import apply_clautter_icon
from src.utils.logger import get_logger
from src.utils.resolve_utils import find_named_video_track  # noqa: F401 — re-exported for callers

log = get_logger(__name__)


def show_warning_dialog(parent: Any, message: str, title: str = "Warning") -> bool:
    """Modal warning dialog with Proceed / Cancel buttons.

    Returns True if user clicked Proceed, False if cancelled.
    """
    result: dict[str, bool] = {"ok": False}

    root = parent
    while not isinstance(root, ctk.CTk):
        root = root.master

    root.update_idletasks()
    dialog_w, dialog_h = 440, 200
    rx = root.winfo_x() + (root.winfo_width() - dialog_w) // 2
    ry = root.winfo_y() + (root.winfo_height() - dialog_h) // 2

    dialog = ctk.CTkToplevel(root)
    apply_clautter_icon(dialog)
    dialog.title(title)
    dialog.geometry(f"{dialog_w}x{dialog_h}+{rx}+{ry}")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes('-topmost', True)
    dialog.after(200, lambda: dialog.attributes('-topmost', False))
    dialog.after(10, dialog.grab_set)

    ctk.CTkLabel(
        dialog,
        text="⚠️  " + title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=COLORS.WARNING,
    ).pack(pady=(20, 8))

    ctk.CTkLabel(
        dialog,
        text=message,
        font=ctk.CTkFont(size=12),
        text_color=COLORS.TEXT_SECONDARY,
        wraplength=380,
        justify="center",
    ).pack(padx=24)

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(pady=(18, 0))

    def on_proceed() -> None:
        result["ok"] = True
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    ctk.CTkButton(
        btn_row, text="Proceed", command=on_proceed,
        fg_color=COLORS.BTN_PRIMARY_BG, hover_color=COLORS.BTN_PRIMARY_HOVER, width=100,
    ).pack(side="left", padx=8)

    ctk.CTkButton(
        btn_row, text="Cancel", command=on_cancel,
        fg_color=COLORS.SEPARATOR, hover_color=COLORS.TEXT_SUBTLE, width=80,
    ).pack(side="left", padx=8)

    dialog.wait_window()
    return result["ok"]


def show_timeline_dialog(
    parent: Any,
    project: Any,
    *,
    current_timeline: Any = None,
    secondary_section: dict | None = None,
) -> dict | None:
    """Choose which timeline to apply an effect to.

    If the project has only one timeline, returns immediately without showing a dialog.
    If multiple timelines exist, shows a picker defaulting to the current timeline.

    Args:
        current_timeline: The active timeline object (used as default selection).
        secondary_section: Optional dict with keys:
            detect (bool): show extra radio group when True
            label (str): section heading text
            existing_text (str): label for "use existing" option
            new_text (str): label for "create new" option
            key (str): key for the extra choice in the return dict

    Returns:
        {
            "timeline": ("existing", tl_obj),
            <key>: "existing" | "new",  # present only when secondary_section detect=True
        }
        or None if user cancelled.
    """
    # Fetch timelines
    timelines: list[tuple[str, Any]] = []
    try:
        count = project.GetTimelineCount()
        for i in range(count):
            tl = project.GetTimelineByIndex(i + 1)
            if tl:
                timelines.append((tl.GetName(), tl))
    except Exception as e:
        log.warning("Could not fetch timeline list: %s", e)

    show_secondary = bool(secondary_section and secondary_section.get("detect"))

    # Single timeline — no dialog needed
    if len(timelines) <= 1:
        tl_obj = timelines[0][1] if timelines else current_timeline
        ret: dict[str, Any] = {"timeline": ("existing", tl_obj)}
        if show_secondary and secondary_section:
            ret[secondary_section["key"]] = "new"
        return ret

    # Multiple timelines — show picker
    result: dict[str, Any] = {"choice": None}

    dialog_height = 230 if show_secondary else 160

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
    apply_clautter_icon(dialog)
    dialog.title("Choose Timeline")
    dialog.geometry(f"420x{dialog_height}+{rx}+{ry}")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes('-topmost', True)
    dialog.after(200, lambda: dialog.attributes('-topmost', False))
    dialog.after(10, dialog.grab_set)

    ctk.CTkLabel(
        dialog,
        text="Apply to which timeline?",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=COLORS.TEXT_PRIMARY,
    ).pack(pady=(20, 10))

    timeline_names = [name for name, _ in timelines]

    # Default to current timeline name
    current_name = current_timeline.GetName() if current_timeline else None
    default_name = current_name if current_name in timeline_names else timeline_names[0]

    combo = ctk.CTkComboBox(
        dialog,
        values=timeline_names,
        state="readonly",
        width=340,
        fg_color=COLORS.BG_CARD,
    )
    combo.set(default_name)
    combo.pack(padx=30, pady=(0, 6))

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
        sel = combo.get()
        tl_obj = next((obj for name, obj in timelines if name == sel), None)
        tl_choice = ("existing", tl_obj) if tl_obj else ("existing", current_timeline)
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
