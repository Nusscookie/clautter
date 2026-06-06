"""Clutter — standalone GUI entry point.

Run this directly with system Python (requires customtkinter):
    python gui.py

Connects to a running DaVinci Resolve instance via DaVinciResolveScript.
"""

from __future__ import annotations
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import ctypes
    # Must be called before any window is created. Separates this process from
    # python.exe in the Windows taskbar so iconbitmap() applies to the correct app.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Clutter.Plugin.1")

try:
    _PLUGIN_DIR = Path(__file__).resolve().parent
except NameError:
    _PLUGIN_DIR = Path(sys.argv[0]).resolve().parent

if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from src.utils.logger import get_logger
from src.app import ClutterApp

log = get_logger("gui")


def _connect_with_timeout(app: Any, timeout: float = 5.0) -> None:
    """Try to connect to a running Resolve, but never block the UI thread forever.

    DaVinciResolveScript.scriptapp("Resolve") blocks until Resolve responds; if
    the user runs Clutter without Resolve open (or with the wrong Python), we
    cap the wait so the UI still opens in a disconnected state.
    """
    result: dict[str, Any] = {"done": False, "connected": False, "err": None}

    def _worker() -> None:
        try:
            result["connected"] = app.connect(resolve_obj=None)
        except Exception as e:
            result["err"] = e
        finally:
            result["done"] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if not result["done"]:
        log.warning(
            "Resolve connect timed out after %.1fs — opening UI in disconnected mode", timeout
        )
    elif result["connected"]:
        log.info("Resolve connected")
    elif result["err"] is not None:
        log.warning("Resolve connect error: %s", result["err"])
    else:
        log.warning("Resolve not connected — UI will show disconnected state")


def main() -> None:
    log.info("Clutter GUI starting")

    app = ClutterApp()
    _connect_with_timeout(app, timeout=5.0)

    try:
        from src.ui.main_window import MainWindow
    except Exception as e:
        log.error("Cannot import MainWindow: %s", e)
        traceback.print_exc()
        return

    try:
        window = MainWindow(app)
    except Exception as e:
        log.error("MainWindow() failed: %s", e)
        traceback.print_exc()
        return

    try:
        window.run()
    except Exception as e:
        log.error("window.run() failed: %s", e)
        traceback.print_exc()
        return

    log.info("Clutter closed")


if __name__ == "__main__":
    main()
