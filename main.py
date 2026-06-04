"""Clutter — DaVinci Resolve Plugin launcher.

Place this file AND the src/ folder in DaVinci Resolve's Scripts/Utility folder:

  Windows:  %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\
  macOS:    ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
  Linux:    ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/

Then launch via:  Workspace → Scripts → Utility → Clutter → main

This script is intentionally minimal — it just launches gui.py as a subprocess using
system Python. The GUI connects to Resolve via DaVinciResolveScript.scriptapp("Resolve"),
bypassing UIManager (removed from Resolve free edition in v19.1).
"""

from __future__ import annotations
import subprocess
import sys
import shutil
from pathlib import Path

try:
    _PLUGIN_DIR = Path(__file__).resolve().parent
except NameError:
    _PLUGIN_DIR = Path(sys.argv[0]).resolve().parent

_GUI_SCRIPT = _PLUGIN_DIR / "gui.py"


def _find_python() -> str | None:
    """Return the first Python interpreter that has both customtkinter AND
    can import DaVinciResolveScript (Resolve's own scripting module).

    Resolve's compiled .pyd is only stable on Python 3.10–3.12. We probe in this
    order: py launcher with version pin → system python → direct executables.
    """
    # Probe scripts that we run with `-c`. Note: on Windows the `py` launcher
    # is the most reliable way to address a specific version.
    probe_scripts: list[list[str]] = []
    if sys.platform == "win32":
        for ver in ("3.12", "3.11", "3.10"):
            probe_scripts.append(["py", f"-{ver}"])
        for name in ("python", "python3", "py"):
            exe = shutil.which(name)
            if exe:
                probe_scripts.append([exe])
    else:
        for name in ("python3", "python"):
            exe = shutil.which(name)
            if exe:
                probe_scripts.append([exe])
        probe_scripts.append([sys.executable])

    # The probe must succeed for BOTH imports — Resolve's module is the fragile one.
    probe_code = (
        "import sys;"
        "from pathlib import Path;"
        "p=Path(r'C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules');"
        "sys.path.insert(0, str(p)) if p.exists() else None;"
        "import DaVinciResolveScript;"
        "import customtkinter"
    )

    for cmd in probe_scripts:
        try:
            result = subprocess.run(
                [*cmd, "-c", probe_code],
                timeout=8,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                # Return the launcher form for the `py` cases, the exe path otherwise
                return cmd[0] if len(cmd) == 1 else " ".join(cmd)
        except Exception:
            continue
    return None


def main() -> None:
    if not _GUI_SCRIPT.exists():
        print(f"[Clutter] ERROR: gui.py not found at {_GUI_SCRIPT}")
        return

    python = _find_python()
    if python is None:
        print(
            "[Clutter] ERROR: No Python interpreter with customtkinter + DaVinciResolveScript found.\n"
            "Resolve 19.x requires Python 3.10–3.12. Install:\n"
            "  py -3.12 -m pip install customtkinter"
        )
        return

    if " " in python:
        # py launcher form: "py -3.12"
        py_args = python.split() + [str(_GUI_SCRIPT)]
    else:
        py_args = [python, str(_GUI_SCRIPT)]

    subprocess.Popen(
        py_args,
        cwd=str(_PLUGIN_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
