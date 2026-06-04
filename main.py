"""Clutter — DaVinci Resolve Plugin

A mix of CLAUDE + CUTTER. Built by Claude Code.

Place this file AND the src/ folder in your DaVinci Resolve Scripts directory:

  Windows:  %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Edit\\
  macOS:    ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/
  Linux:    ~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/

Then launch via:  Workspace > Scripts > Clutter

See INSTALL.md for full setup instructions including Python dependencies.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure the plugin's src/ package is importable regardless of working directory
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from src.utils.logger import get_logger
from src.app import AIEditorApp

log = get_logger("main")


def main() -> None:
    log.info("=" * 60)
    log.info("AI Editor Assistant starting")

    app = AIEditorApp()
    connected = app.connect()

    if not connected:
        log.warning("Resolve connection failed — UI will display error state")

    # Get Fusion and bmd from the Resolve environment.
    # When running from the Scripts menu, 'fusion' and 'bmd' are Resolve-injected globals.
    # When running externally (after importing DaVinciResolveScript), bmd is in sys.modules.
    fusion = None
    bmd_module = None

    if connected and app.resolve is not None:
        try:
            fusion = app.resolve.Fusion()
        except Exception as e:
            log.error("Failed to get Fusion object: %s", e)

    # bmd is injected as a side effect of loading fusionscript (via DaVinciResolveScript import)
    bmd_module = sys.modules.get("bmd")
    if bmd_module is None:
        import builtins
        bmd_module = getattr(builtins, "bmd", None)

    if fusion is None or bmd_module is None:
        log.error(
            "Cannot initialize UI: fusion=%s bmd=%s. "
            "Make sure DaVinci Resolve is running.",
            fusion, bmd_module,
        )
        return

    from src.ui.main_window import MainWindow

    window = MainWindow(app, fusion, bmd_module)
    window.run()

    log.info("AI Editor Assistant closed")


if __name__ == "__main__":
    main()
