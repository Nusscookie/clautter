"""Hyperframes catalog client.

Wraps `npx hyperframes catalog --json` and `npx hyperframes add` so the rest
of the pipeline doesn't need to know CLI details. Catalog JSON is cached for
the lifetime of the process to avoid repeated npx cold-start overhead.
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_TIMEOUT = 60
_catalog_cache: list[dict] | None = None


def list_blocks(force_refresh: bool = False) -> list[dict]:
    """Return available Hyperframes catalog blocks.

    Each block dict contains at minimum: name, type, tags, description.
    Returns [] on failure (caller degrades gracefully).
    """
    global _catalog_cache
    if _catalog_cache is not None and not force_refresh:
        return _catalog_cache

    try:
        result = subprocess.run(
            ["npx", "--yes", "hyperframes", "catalog", "--json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode != 0:
            log.warning("[catalog] npx hyperframes catalog failed: %s", result.stderr[:300])
            return []

        data = json.loads(result.stdout)
        # CLI returns either a list directly or {"blocks": [...]}
        if isinstance(data, list):
            blocks = data
        elif isinstance(data, dict):
            blocks = data.get("blocks") or data.get("items") or []
        else:
            blocks = []

        _catalog_cache = blocks
        log.info("[catalog] loaded %d blocks from Hyperframes catalog", len(blocks))
        return blocks

    except subprocess.TimeoutExpired:
        log.warning("[catalog] npx hyperframes catalog timed out")
        return []
    except json.JSONDecodeError as e:
        log.warning("[catalog] catalog JSON parse error: %s", e)
        return []
    except Exception as e:
        log.warning("[catalog] list_blocks failed: %s", e)
        return []


def add_block(name: str, workspace_dir: Path) -> bool:
    """Run `npx hyperframes add <name> --dir <workspace_dir>`.

    Returns True on success.
    """
    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["npx", "--yes", "hyperframes", "add", name, "--dir", str(workspace_dir)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(workspace_dir),
        )
        if result.returncode != 0:
            log.warning("[catalog] hyperframes add %s failed: %s", name, result.stderr[:300])
            return False
        log.info("[catalog] added block %r to %s", name, workspace_dir)
        return True
    except subprocess.TimeoutExpired:
        log.warning("[catalog] hyperframes add %s timed out", name)
        return False
    except Exception as e:
        log.warning("[catalog] add_block %s failed: %s", name, e)
        return False


def block_summary(blocks: list[dict]) -> str:
    """Format blocks as a compact string for LLM prompts."""
    lines = []
    for b in blocks:
        name = b.get("name", "")
        tags = ", ".join(b.get("tags") or [])
        desc = (b.get("description") or "")[:80]
        lines.append(f'  "{name}" tags=[{tags}] — {desc}')
    return "\n".join(lines)
