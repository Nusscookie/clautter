"""Apply the Clutter icon to any CTk or CTkToplevel window."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from src.utils.logger import get_logger

log = get_logger(__name__)

_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "icon.png"


def apply_clutter_icon(window: object) -> None:
    """Apply assets/icon.png to *window*.

    For CTk (main window) also writes a .ico for the Windows taskbar.
    For CTkToplevel, iconphoto only. Silently skips if icon missing or Pillow absent.
    """
    try:
        from PIL import Image, ImageTk  # type: ignore
        if not _ICON_PATH.exists():
            return
        img = Image.open(str(_ICON_PATH)).convert("RGBA")
        photo = ImageTk.PhotoImage(img)
        window.iconphoto(False, photo)  # type: ignore[attr-defined]
        window._icon_ref = photo  # prevent GC

        if sys.platform == "win32":
            _tmp = Path(tempfile.gettempdir()) / "clutter_icon.ico"
            img.resize((256, 256), Image.NEAREST).save(str(_tmp), format="ICO")
            try:
                window.iconbitmap(str(_tmp))  # type: ignore[attr-defined]
            except Exception:
                pass  # CTkToplevel may reject iconbitmap on some platforms
    except Exception as e:
        log.debug("Icon load failed: %s", e)
