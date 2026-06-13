"""Node.js availability check for the Hyperframes rendering pipeline."""

from __future__ import annotations
import subprocess


def check_node() -> tuple[bool, str]:
    """Return (ok, message). message is version string on success, install hint on failure."""
    try:
        r = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, "Node.js not responding correctly. Reinstall from https://nodejs.org"
    except FileNotFoundError:
        return (
            False,
            "Node.js not installed. Install the LTS version from https://nodejs.org, "
            "then restart Clutter.",
        )
    except Exception as e:
        return False, f"Node.js check failed: {e}"
