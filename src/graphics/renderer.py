"""Hyperframes block renderer.

For each GraphicPlacement:
  1. Creates a timestamped workspace subfolder under ~/.clutter/graphics/<project>/
  2. Installs the block via `npx hyperframes add`
  3. Injects LLM-supplied params into the block's HTML
  4. Renders to output.mp4 via `npx hyperframes render`
  5. Returns the Path to output.mp4

Workspace layout:
  ~/.clutter/graphics/
    <project_name>/
      <timestamp>_<block_name>/
        compositions/
          <block_name>.html
        output.mp4
"""

from __future__ import annotations
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger
from src.graphics.catalog_client import add_block
from src.graphics.llm_director import GraphicPlacement

log = get_logger(__name__)

_RENDER_TIMEOUT = 300  # 5 min max per block
_GRAPHICS_ROOT = Path.home() / ".clutter" / "graphics"


def _workspace_for(project_name: str, placement: GraphicPlacement) -> Path:
    safe_project = re.sub(r"[^\w\-]", "_", project_name or "unknown")
    timestamp = int(time.time())
    safe_block = re.sub(r"[^\w\-]", "_", placement.block)
    folder = _GRAPHICS_ROOT / safe_project / f"{timestamp}_{safe_block}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _inject_params(html_path: Path, params: dict) -> None:
    """Inject LLM-supplied params as data-* attributes on the root composition element."""
    if not params or not html_path.exists():
        return
    try:
        content = html_path.read_text(encoding="utf-8")
        # For each param key, try to find an existing data-<key> attribute and replace its value.
        # If not found, inject as a new data-param-<key> attribute on the first data-composition-id element.
        for key, value in params.items():
            safe_key = re.sub(r"[^\w\-]", "-", str(key)).lower()
            safe_val = str(value).replace('"', "&quot;")
            attr_pattern = rf'(data-{re.escape(safe_key)}=")[^"]*(")'
            if re.search(attr_pattern, content):
                content = re.sub(attr_pattern, rf'\g<1>{safe_val}\g<2>', content)
            else:
                # Append as data-param-<key> on composition element
                content = re.sub(
                    r'(data-composition-id="[^"]*")',
                    rf'\g<1> data-param-{safe_key}="{safe_val}"',
                    content,
                    count=1,
                )
        html_path.write_text(content, encoding="utf-8")
        log.debug("[renderer] injected params into %s", html_path.name)
    except Exception as e:
        log.warning("[renderer] param injection failed (non-fatal): %s", e)


def render_placement(placement: GraphicPlacement, project_name: str) -> Path | None:
    """Render one GraphicPlacement to an MP4.

    Returns Path to output.mp4, or None on failure.
    """
    workspace = _workspace_for(project_name, placement)
    log.info("[renderer] workspace: %s", workspace)

    if not add_block(placement.block, workspace):
        log.warning("[renderer] failed to add block %r", placement.block)
        return None

    # Find the installed HTML — hyperframes puts it in compositions/
    compositions_dir = workspace / "compositions"
    html_candidates = list(compositions_dir.glob("*.html")) if compositions_dir.exists() else []
    if not html_candidates:
        # Fallback: search workspace root
        html_candidates = list(workspace.glob("*.html"))
    if not html_candidates:
        log.warning("[renderer] no HTML found in %s after add_block", workspace)
        return None

    html_path = html_candidates[0]
    _inject_params(html_path, placement.params)

    output_path = workspace / "output.mp4"
    try:
        result = subprocess.run(
            [
                "npx", "--yes", "hyperframes", "render",
                "-c", str(html_path),
                "-o", str(output_path),
                "--fps", "30",
            ],
            capture_output=True,
            text=True,
            timeout=_RENDER_TIMEOUT,
            cwd=str(workspace),
        )
        if result.returncode != 0:
            log.warning("[renderer] render failed for %r: %s", placement.block, result.stderr[:400])
            return None
        if not output_path.exists():
            log.warning("[renderer] render exited 0 but output.mp4 not found at %s", output_path)
            return None
        log.info("[renderer] rendered %r → %s", placement.block, output_path)
        return output_path
    except subprocess.TimeoutExpired:
        log.warning("[renderer] render timed out for block %r", placement.block)
        return None
    except Exception as e:
        log.warning("[renderer] render error for %r: %s", placement.block, e)
        return None
