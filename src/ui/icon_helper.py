"""Apply the Clutter icon to any CTk or CTkToplevel window.

Why this is more than a one-liner: ``CTkToplevel`` creates its underlying Tk
window lazily, so calling ``iconphoto``/``iconbitmap`` immediately after
construction silently no-ops (the window isn't realized yet). That is why
secondary windows kept losing the icon. We therefore defer the call via
``window.after(...)`` for Toplevels, and cache the generated ``.ico`` so we
don't rewrite a temp file on every window.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "icon.png"

# Cached PhotoImage + generated .ico path — built once, reused for every window.
_photo: Any = None
_ico_path: str | None = None
_load_failed = False


def _ensure_assets() -> bool:
    """Build the shared PhotoImage and (on Windows) the .ico once. Returns
    False if Pillow is missing or the icon file is absent."""
    global _photo, _ico_path, _load_failed
    if _load_failed:
        return False
    if _photo is not None:
        return True
    try:
        from PIL import Image, ImageTk  # type: ignore
        if not _ICON_PATH.exists():
            log.debug("Icon file missing: %s", _ICON_PATH)
            _load_failed = True
            return False
        img = Image.open(str(_ICON_PATH)).convert("RGBA")
        _photo = ImageTk.PhotoImage(img)
        if sys.platform == "win32":
            tmp = Path(tempfile.gettempdir()) / "clutter_icon.ico"
            if not tmp.exists():
                img.resize((256, 256), Image.LANCZOS).save(str(tmp), format="ICO")
            _ico_path = str(tmp)
        return True
    except Exception as e:  # Pillow absent, ICO write failure, etc.
        log.debug("Icon asset build failed: %s", e)
        _load_failed = True
        return False


def _set_icon(window: Any) -> None:
    """Apply both the photo (cross-platform title bar) and the .ico (Windows
    taskbar / title bar). Each call is guarded — CTkToplevel may reject one."""
    try:
        window.iconphoto(False, _photo)
        window._icon_ref = _photo  # prevent GC
    except Exception as e:
        log.debug("iconphoto failed: %s", e)
    if _ico_path is not None:
        try:
            window.iconbitmap(_ico_path)
        except Exception:
            pass  # some Toplevels reject iconbitmap on certain platforms


def apply_clutter_icon(window: Any, defer: bool | None = None) -> None:
    """Apply assets/icon.png to *window* (CTk root or any CTkToplevel).

    *defer* controls when the icon is set. Auto-detected when None: the root
    ``CTk`` is already realized so we set immediately; every other window
    (Toplevel) is deferred via ``after`` so Tk has realized it first — this is
    the fix for secondary windows that previously showed no icon. Silently
    skips if Pillow is absent or the icon file is missing.
    """
    if not _ensure_assets():
        return

    if defer is None:
        # CTk root is realized at construction; Toplevels are not.
        defer = type(window).__name__ != "CTk"

    if defer:
        try:
            window.after(120, lambda: _set_icon(window))
            return
        except Exception:
            pass  # no event loop yet — fall through to immediate
    _set_icon(window)
