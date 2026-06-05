"""Clutter — DaVinci Resolve Plugin launcher.

Place this file AND the src/ folder in DaVinci Resolve's Scripts/Utility folder:

  Windows:  %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\
  macOS:    ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
  Linux:    ~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/

Then launch via:  Workspace → Scripts → Utility → Clutter → main

What this does:

1. Acquires the live ``resolve`` object from Resolve's process.
   Free edition: ``getattr(builtins, "resolve", None)`` works.
   Studio:        ``DaVinciResolveScript.scriptapp("Resolve")`` as fallback.
2. Starts a local HTTP bridge in a daemon thread so the spawned
   ``gui.py`` subprocess can call Resolve methods (free edition has no
   external scripting; the subprocess can't talk to Resolve directly).
3. Spawns ``gui.py`` with the system Python that has ``customtkinter``.
4. **Blocks** until ``gui.py`` exits. The daemon thread holds the live
   ``resolve`` object alive in Resolve's process; if this launcher
   returned, the thread would die and the bridge would go down. The
   Resolve script entry stays "busy" for the lifetime of the GUI, which
   is the intended behavior — clicking "main" again before the GUI
   closes is a no-op anyway because Resolve only allows one execution
   per script at a time.

The HTTP server writes its port to ``~/.clutter/bridge.json``; the
client (gui.py) reads the file and connects. If the file is stale
(Resolve restarted), the client's ``/ping`` fails and the connect
falls through to other strategies.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

try:
    _PLUGIN_DIR = Path(__file__).resolve().parent
except NameError:
    _PLUGIN_DIR = Path(sys.argv[0]).resolve().parent

_GUI_SCRIPT = _PLUGIN_DIR / "gui.py"


def _find_python() -> str | None:
    """Return the first Python interpreter that has ``customtkinter``.

    Resolve's compiled scripting module is no longer required here — the
    bridge runs inside Resolve's process, so the spawned GUI just needs
    a Python that can import ``customtkinter``. We probe in this order:
    ``py -3.12/-3.11/-3.10`` (Windows), then ``python3`` / ``python``.
    """
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

    _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for cmd in probe_scripts:
        try:
            result = subprocess.run(
                [*cmd, "-c", "import customtkinter"],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_no_window,
            )
            if result.returncode == 0:
                return cmd[0] if len(cmd) == 1 else " ".join(cmd)
        except Exception:
            continue
    return None


def _acquire_resolve():
    """Return the live ``resolve`` object, or None if unavailable.

    Resolve injects ``resolve`` into the running script's module globals
    (not builtins) when executing from the Scripts menu. We capture it
    there first, then try builtins (some versions), then Studio's external
    scripting API as a last resort.
    """
    # Primary path: Resolve injects into this module's globals at script
    # launch time. Must be captured here (same module) so globals() is
    # main.py's namespace, which is where the injection lands.
    resolve = globals().get("resolve")
    if resolve is not None:
        return resolve

    # Some Resolve versions / launch modes inject into builtins instead.
    import builtins
    resolve = getattr(builtins, "resolve", None)
    if resolve is not None:
        return resolve

    try:
        import DaVinciResolveScript as dvr  # type: ignore
        resolve = dvr.scriptapp("Resolve")
    except ImportError:
        resolve = None

    return resolve


def main() -> None:
    if not _GUI_SCRIPT.exists():
        print(f"[Clutter] ERROR: gui.py not found at {_GUI_SCRIPT}")
        return

    # 1. Acquire the live resolve object.
    resolve = _acquire_resolve()
    if resolve is None:
        print(
            "[Clutter] ERROR: Cannot reach DaVinci Resolve from this script context.\n"
            "Make sure you launched this from Workspace > Scripts > Utility > Clutter."
        )
        return

    # 2. Start the HTTP bridge so the spawned GUI can call Resolve.
    #    Make sure the plugin's src/ is on sys.path for the rpc_server import.
    if str(_PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(_PLUGIN_DIR))

    try:
        from src.utils.rpc_server import start_server
        # _server is intentionally unused here — the daemon thread holds
        # the only reference it needs to stay alive. We bind it just so
        # the variable isn't garbage-collected mid-call.
        _server, port = start_server(resolve)
    except Exception as e:
        print(f"[Clutter] ERROR: Failed to start HTTP bridge: {e!r}")
        return

    # 3. Find a Python that has customtkinter and spawn the GUI.
    python = _find_python()
    if python is None:
        print(
            "[Clutter] ERROR: No Python interpreter with customtkinter found.\n"
            "Resolve 19.x requires Python 3.10–3.12. Install:\n"
            "  py -3.12 -m pip install customtkinter"
        )
        return

    if " " in python:
        py_args = python.split() + [str(_GUI_SCRIPT)]
    else:
        py_args = [python, str(_GUI_SCRIPT)]

    proc = subprocess.Popen(
        py_args,
        cwd=str(_PLUGIN_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    # 4. Block until the user closes the GUI. The bridge thread needs
    #    this process to stay alive — once main() returns, the daemon
    #    thread dies and the GUI loses its connection to Resolve.
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
