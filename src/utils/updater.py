"""Update checker and installer for Clautter.

Checks GitHub tags API for newer tagged versions and downloads the tag zip
to extract over the app dir. No git required.
No UI imports — all callbacks go through frame.after(0, ...) from callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from src.constants import APP_VERSION
from src.utils.logger import get_logger

log = get_logger(__name__)

GITHUB_REPO = "Nusscookie/clautter"
_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
_REPO_DIR = Path(__file__).resolve().parents[2]


def get_current_version() -> str:
    return APP_VERSION


_NO_RELEASES = object()  # sentinel: repo has no tags yet


def fetch_latest_release(timeout: float = 5.0) -> "dict[str, Any] | None | object":
    """GET GitHub tags list and return the newest semver tag as a dict.

    Returns:
        dict with 'tag_name' key — newest tag found
        _NO_RELEASES sentinel  — repo has no tags yet (treat as up to date)
        None                   — network/API error
    """
    try:
        resp = requests.get(
            _API_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if resp.status_code == 404:
            log.info("Repo not found or no tags")
            return _NO_RELEASES
        resp.raise_for_status()
        tags: list[dict] = resp.json()
        if not tags:
            return _NO_RELEASES
        # Pick tag with highest version number
        def _sort_key(t: dict) -> tuple[int, ...]:
            return _parse_version(t.get("name", ""))
        latest = max(tags, key=_sort_key)
        return {"tag_name": latest["name"]}
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
    """Download tag zip from GitHub and extract over the app dir."""
    import io
    import zipfile

    zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag_name}.zip"
    try:
        log.info("Downloading %s", zip_url)
        resp = requests.get(zip_url, timeout=120, stream=True)
        resp.raise_for_status()
        data = resp.content

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Zip contains a top-level folder like "clautter-0.1.0/" — strip it
            members = zf.namelist()
            prefix = members[0].split("/")[0] + "/"
            for member in members:
                if member == prefix:
                    continue
                rel = member[len(prefix):]
                if not rel:
                    continue
                dest = _REPO_DIR / rel
                if member.endswith("/"):
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(member))

        log.info("Updated to %s", tag_name)
        return True, f"Updated to {tag_name}. Please restart Clautter."
    except Exception as e:
        log.error("run_update error: %s", e)
        return False, str(e)
