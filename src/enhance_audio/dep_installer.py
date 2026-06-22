"""On-demand pip installer for optional enhancement engines.

Optional engines (resemble-enhance, demucs) are heavy and not pinned in
requirements.txt. They install on first use into the GUI subprocess's own
Python (``sys.executable``), after the user confirms a CPU/size warning in the
UI. Output streams to a callback so the tab's status label shows progress.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from src.utils.logger import get_logger

log = get_logger(__name__)

LogCb = Callable[[str], None]


def is_installed(import_name: str) -> bool:
    """True if the top-level module is importable (no actual import performed)."""
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def _env_with_cargo() -> dict[str, str]:
    """Return os.environ with ~/.cargo/bin prepended to PATH if cargo not found.

    Rustup installs cargo to ~/.cargo/bin but doesn't always update the current
    process's PATH (especially if installed in the same session). pip needs cargo
    on PATH to build deepfilterlib from source.
    """
    env = os.environ.copy()
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir():
        path_dirs = env.get("PATH", "").split(os.pathsep)
        if str(cargo_bin) not in path_dirs:
            env["PATH"] = str(cargo_bin) + os.pathsep + env.get("PATH", "")
            log.info("[pip] injected %s into PATH for Rust build", cargo_bin)
    return env


def _run_pip(cmd: list[str], env: dict[str, str], emit: Callable[[str], None]) -> bool:
    """Run a pip command, stream output to emit, return True on success."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except Exception as e:
        emit(f"Failed to launch pip: {e}")
        return False

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            emit(line)
    return proc.wait() == 0


def install(pip_pkg: str, log_cb: LogCb | None = None) -> bool:
    """Run ``python -m pip install <pip_pkg>`` in this interpreter.

    Streams stdout lines to ``log_cb`` (and the logger). Returns True on a
    zero exit code. Call from a worker thread — this blocks until pip exits.

    deepfilternet special-case: its metadata pins numpy<2.0, but deepfilterlib
    compiles against whatever numpy is present at build time. If we built against
    numpy 2.x (which is what Clautter requires), we must override that pin so pip
    doesn't downgrade numpy and cause a runtime ABI mismatch.

    resemble-enhance special-case: it depends on deepspeed==0.12.4 which tries
    to pre-compile CUDA ops at build time (DS_BUILD_OPS=1 by default) and asserts
    torch is installed before pip even resolves requirements. Fix: install torch
    first, then set DS_BUILD_OPS=0 so deepspeed skips compilation and installs
    as a pure-Python package.
    """
    def _emit(line: str) -> None:
        log.info("[pip] %s", line)
        if log_cb:
            log_cb(line)

    env = _env_with_cargo()

    if pip_pkg == "resemble-enhance":
        import platform as _platform
        if _platform.system() == "Windows":
            _emit(
                "resemble-enhance cannot be installed on Windows: its deepspeed dependency "
                "fails to build due to a symlink permission error (WinError 5) in setup.py "
                "and has no Windows wheels. Use Linux or macOS."
            )
            return False

    cmd = [sys.executable, "-m", "pip", "install", pip_pkg]
    if pip_pkg == "deepfilternet":
        # Override deepfilternet's numpy<2.0 pin — deepfilterlib compiles against
        # the numpy that is present at build time (numpy 2.x in our env), so
        # downgrading it causes 'ndarray cannot be converted to PyArray' at runtime.
        cmd += ["numpy>=2.0"]

    _emit(f"Installing {pip_pkg} … (this can take a while)")
    ok = _run_pip(cmd, env, _emit)
    if ok:
        _emit(f"Installed {pip_pkg}.")
    else:
        _emit(f"pip install {pip_pkg} failed.")
    return ok
