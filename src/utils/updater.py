"""Update checker and installer for Clautter.

Checks GitHub releases API for newer tagged versions and runs
``git fetch --tags && git reset --hard tags/<version>`` to update.
No UI imports — all callbacks go through frame.after(0, ...) from callers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import requests

from src.constants import APP_VERSION
from src.utils.logger import get_logger

log = get_logger(__name__)

GITHUB_REPO = "Nusscookie/clautter"
_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_REPO_DIR = Path(__file__).resolve().parents[2]


def get_current_version() -> str:
    return APP_VERSION


_NO_RELEASES = object()  # sentinel: repo exists but has no releases


def fetch_latest_release(timeout: float = 5.0) -> "dict[str, Any] | None | object":
    """GET GitHub releases/latest.

    Returns:
        dict   — release data (update may be available)
        _NO_RELEASES sentinel — repo has no releases yet (treat as up to date)
        None   — network/API error
    """
    try:
        resp = requests.get(
            _API_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if resp.status_code == 404:
            log.info("No releases on GitHub yet")
            return _NO_RELEASES
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("Update check failed: %s", e)
        return None


def _parse_version(tag: str) -> tuple[int, ...]:
    """'v1.2.3' → (1, 2, 3). Non-numeric parts become 0."""
    stripped = tag.lstrip("v")
    parts = []
    for p in stripped.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_update_available(latest: "dict[str, Any] | object") -> bool:
    if latest is _NO_RELEASES or not isinstance(latest, dict):
        return False
    tag = latest.get("tag_name", "")
    if not tag:
        return False
    try:
        return _parse_version(tag) > _parse_version(APP_VERSION)
    except Exception:
        return False


def run_update(tag_name: str) -> tuple[bool, str]:
    """Fetch tags and hard-reset to the given tag. Returns (success, message)."""
    try:
        fetch = subprocess.run(
            ["git", "fetch", "--tags"],
            cwd=str(_REPO_DIR),
            capture_output=True, text=True, timeout=60,
        )
        if fetch.returncode != 0:
            return False, f"git fetch failed: {fetch.stderr.strip()}"

        reset = subprocess.run(
            ["git", "reset", "--hard", f"tags/{tag_name}"],
            cwd=str(_REPO_DIR),
            capture_output=True, text=True, timeout=30,
        )
        if reset.returncode != 0:
            return False, f"git reset failed: {reset.stderr.strip()}"

        log.info("Updated to %s", tag_name)
        return True, f"Updated to {tag_name}. Please restart Clautter."
    except Exception as e:
        log.error("run_update error: %s", e)
        return False, str(e)
