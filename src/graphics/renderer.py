"""Hyperframes block renderer.

For each GraphicPlacement:
  1. Creates a timestamped workspace subfolder under ~/.clutter/graphics/<project>/
  2. Installs the block via `npx hyperframes add`
  3. LLM edits block HTML with real transcript-derived values
  4. Injects LLM-supplied params as data-param-* attributes
  5. Renders to output.mp4 via `npx hyperframes render`
  6. Returns the Path to output.mp4

Workspace layout:
  ~/.clutter/graphics/
    <project_name>/
      <timestamp>_<block_name>/
        compositions/
          <block_name>.html
        <block_name>_<start>s.mp4
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger
from src.graphics.catalog_client import add_block
from src.graphics.llm_director import GraphicPlacement

log = get_logger(__name__)

_RENDER_TIMEOUT = 300  # 5 min max per block
_GRAPHICS_ROOT = Path.home() / ".clutter" / "graphics"
_NPX = "npx.cmd" if sys.platform == "win32" else "npx"


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


def _llm_edit_html(html_path: Path, placement: GraphicPlacement, settings: Any) -> None:
    """Ask LLM to rewrite block HTML with real values from placement.params.

    Reads the installed block HTML, asks LLM to replace hardcoded placeholder
    text/numbers/data with actual transcript-derived values, writes result back.
    On any failure logs a warning and leaves the original HTML intact.
    """
    try:
        from src.utils.llm_providers import api_key_for, resolve_provider
        import requests as _requests

        chosen = resolve_provider(settings, None)
        if chosen is None:
            log.debug("[renderer] no LLM provider configured — skipping HTML edit for %s", placement.block)
            return

        html = html_path.read_text(encoding="utf-8")
        prompt = (
            f"You are editing a motion graphics HTML template for a talking-head video.\n"
            f"Block: {placement.block}\n"
            f"Params derived from transcript: {json.dumps(placement.params)}\n\n"
            f"BLOCK HTML:\n```html\n{html[:8000]}\n```\n\n"
            "Task: Edit the HTML to replace hardcoded placeholder values — text strings, "
            "numbers, data arrays, labels — with real values from the params above. "
            "If params do not cover a field, leave the original value. "
            "Only change content values. Do NOT change HTML structure, CSS layout, "
            "animation timing, or JavaScript logic. "
            "Return ONLY the complete modified HTML file. No explanations, no markdown fences, "
            "no preamble — raw HTML starting with <!doctype or <!-- only."
        )

        key = api_key_for(settings, chosen)
        openai_url = "https://api.openai.com/v1/chat/completions"
        gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        minimax_url = "https://api.minimax.io/v1/chat/completions"
        nvidia_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        timeout = 90

        system = "You are a code editor. Output raw HTML only. No markdown, no explanation."

        if chosen == "Gemini":
            resp = _requests.post(
                f"{gemini_url}?key={key}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.1}},
                timeout=timeout,
            )
            resp.raise_for_status()
            reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            model_map = {
                "OpenAI": str(settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini"),
                "Minimax": str(settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01"),
                "NVIDIA": str(settings.get("llm_nvidia_model", "") or ""),
            }
            url_map = {"OpenAI": openai_url, "Minimax": minimax_url, "NVIDIA": nvidia_url}
            payload = {
                "model": model_map[chosen],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 8192,
                "temperature": 0.1,
            }
            if chosen == "NVIDIA":
                payload["chat_template_kwargs"] = {"thinking": False}
            resp = _requests.post(
                url_map[chosen],
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]

        # Strip think tags (Minimax/reasoning models) then markdown fences
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        reply = re.sub(r"^```(?:html)?\s*", "", reply, flags=re.IGNORECASE).strip()
        reply = re.sub(r"\s*```$", "", reply).strip()

        # Sanity: must look like HTML
        if not reply.startswith(("<!doctype", "<!DOCTYPE", "<!--", "<html", "<HTML", "<!")):
            log.warning("[renderer] LLM edit non-HTML for %s (starts with: %r) — keeping original",
                        placement.block, reply[:80])
            return

        html_path.write_text(reply, encoding="utf-8")
        log.info("[renderer] LLM (%s) edited HTML for %s", chosen, placement.block)

    except Exception as e:
        log.warning("[renderer] _llm_edit_html failed for %s (non-fatal): %s", placement.block, e)


def _make_index_html(workspace: Path, block_name: str, block_html_rel: str, block: dict) -> Path:
    """Generate a host index.html that embeds the block composition.

    hyperframes render requires an index.html at the workspace root that uses
    data-composition-src to reference the installed block HTML. The block cannot
    be rendered directly.
    """
    dims = block.get("dimensions") or {}
    width = dims.get("width", 1920)
    height = dims.get("height", 1080)
    duration = block.get("duration", 15)
    index_path = workspace / "index.html"
    index_path.write_text(
        f"""<!doctype html>
<html>
<head><meta charset="UTF-8" /></head>
<body>
<div
  data-composition-src="{block_html_rel}"
  data-duration="{duration}"
  data-width="{width}"
  data-height="{height}"
></div>
</body>
</html>
""",
        encoding="utf-8",
    )
    return index_path


def render_placement(
    placement: GraphicPlacement,
    project_name: str,
    block_meta: dict | None = None,
    settings: Any = None,
) -> Path | None:
    """Render one GraphicPlacement to an MP4.

    Returns Path to output mp4, or None on failure.
    block_meta: catalog block dict (for dimensions/duration).
    settings:   SettingsManager for LLM HTML editing.
    """
    workspace = _workspace_for(project_name, placement)
    log.info("[renderer] workspace: %s", workspace)

    if not add_block(placement.block, workspace):
        log.warning("[renderer] failed to add block %r", placement.block)
        return None

    # Find the installed block HTML in compositions/
    compositions_dir = workspace / "compositions"
    html_candidates = list(compositions_dir.glob("*.html")) if compositions_dir.exists() else []
    if not html_candidates:
        html_candidates = list(workspace.glob("*.html"))
    if not html_candidates:
        log.warning("[renderer] no HTML found in %s after add_block", workspace)
        return None

    block_html_path = html_candidates[0]

    # LLM edits HTML with real transcript-derived values before render
    if settings is not None:
        _llm_edit_html(block_html_path, placement, settings)

    _inject_params(block_html_path, placement.params)

    # hyperframes render needs a host index.html — build one wrapping the block
    block_html_rel = block_html_path.relative_to(workspace).as_posix()
    index_path = _make_index_html(workspace, placement.block, block_html_rel, block_meta or {})
    log.debug("[renderer] host index.html: %s", index_path)

    safe_name = re.sub(r"[^\w\-]", "_", placement.block)
    output_path = workspace / f"{safe_name}_{int(placement.start_sec)}s.mp4"
    try:
        result = subprocess.run(
            [
                _NPX, "--yes", "hyperframes", "render",
                str(workspace),
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
            log.warning("[renderer] render exited 0 but %s not found", output_path.name)
            return None
        log.info("[renderer] rendered %r → %s", placement.block, output_path)
        return output_path
    except subprocess.TimeoutExpired:
        log.warning("[renderer] render timed out for block %r", placement.block)
        return None
    except Exception as e:
        log.warning("[renderer] render error for %r: %s", placement.block, e)
        return None
