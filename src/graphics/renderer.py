"""Hyperframes block renderer.

For each GraphicPlacement:
  1. Creates a timestamped workspace subfolder under ~/.clautter/graphics/<project>/
  2. Installs the block via `npx hyperframes add`
  3. LLM edits block HTML with real transcript-derived values + aspect ratio fix
  4. Injects LLM-supplied params as data-param-* attributes
  5. Renders to MOV (ProRes 4444+alpha) via `npx hyperframes render --format mov`
     Falls back to WebM (VP9+alpha) if MOV render fails.
     MOV is primary: DaVinci Resolve handles ProRes 4444 natively with full
     alpha support; WebM decode in Resolve uses an unofficial fallback path
     that produces pixelated/downscaled output.
  6. Returns the Path to the rendered file

Workspace layout:
  ~/.clautter/graphics/
    <project_name>/
      <timestamp>_<block_name>/
        compositions/
          <block_name>.html
        <block_name>_<start>s.mov  (or .webm fallback)
"""

from __future__ import annotations
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from src.constants import PATHS
from src.utils.logger import get_logger
from src.graphics.catalog_client import add_block
from src.graphics.llm_director import GraphicPlacement

log = get_logger(__name__)

_RENDER_TIMEOUT = 300  # 5 min max per block
_GRAPHICS_ROOT = PATHS.GRAPHICS_CACHE
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


def _sanitize_selectors(html: str) -> str:
    """Strip LLM-injected extra attribute conditions from composition selectors.

    The LLM sometimes copies params into CSS selectors as extra
    [data-composition-id="x" data-param-foo="y"] conditions. Those attrs are
    injected onto the DOM *after* the LLM edit (see _inject_params), so such a
    selector never matches and its rule (often the positioning block) is dead.
    Collapse every [data-composition-id="x" ...] back to [data-composition-id="x"].
    Only text inside [...] brackets is touched, so the DOM element's own
    attribute list is left intact.
    """
    return re.sub(
        r'\[data-composition-id="([^"]*)"[^\]]*\]',
        r'[data-composition-id="\1"]',
        html,
    )


def _llm_edit_html(
    html_path: Path,
    placement: GraphicPlacement,
    settings: Any,
    timeline_dims: tuple[int, int] | None = None,
    provider: str | None = None,
    user_instructions: str | None = None,
) -> None:
    """Ask LLM to rewrite block HTML with real values from placement.params.

    Reads the installed block HTML, asks LLM to replace hardcoded placeholder
    text/numbers/data with actual transcript-derived values, apply any layout/
    positioning changes from user_instructions, and if timeline_dims is provided
    and the block's native size differs, rewrite CSS to match aspect ratio.
    On any failure logs a warning and leaves the original HTML intact.
    """
    try:
        from src.utils.llm_providers import api_key_for, resolve_provider
        import requests as _requests

        chosen = resolve_provider(settings, provider)
        if chosen is None:
            log.debug("[renderer] no LLM provider configured — skipping HTML edit for %s", placement.block)
            return

        html = html_path.read_text(encoding="utf-8")

        dims_instruction = ""
        if timeline_dims:
            tl_w, tl_h = timeline_dims
            dims_instruction = (
                f"\n\nTIMELINE DIMENSIONS: {tl_w}x{tl_h} px. "
                "If the block's native dimensions (width/height in CSS or data attributes) do NOT match "
                f"this aspect ratio ({tl_w}:{tl_h}), rewrite the relevant CSS width/height/font-size values "
                "so the block fills the timeline canvas without letterbox bars. "
                "Preserve all animations and layout proportions — only scale to fit."
            )

        user_block = ""
        if user_instructions:
            user_block = (
                f"\n\nUSER INSTRUCTIONS (highest priority — follow these exactly):\n"
                f"{user_instructions}\n"
            )

        prompt = (
            f"You are editing a motion graphics HTML template for a talking-head video.\n"
            f"Block: {placement.block}\n"
            f"Params derived from transcript: {json.dumps(placement.params)}\n\n"
            f"BLOCK HTML:\n```html\n{html[:8000]}\n```\n\n"
            + user_block +
            "\nTask: Edit the HTML to:\n"
            "  1. Replace hardcoded placeholder text, numbers, data arrays, labels with real "
            "values from the params above. If params do not cover a field, leave the original value.\n"
            "  2. Apply any layout, positioning, or style changes from USER INSTRUCTIONS above.\n"
            "     You MAY change: position (top/left/right/bottom), transform, flex/grid layout, "
            "font-size, color, background, padding, margin, z-index, text-align.\n"
            "     You MUST NOT change: animation durations (@keyframes timings, animation-duration, "
            "transition values), JavaScript logic, or DOM structure (no adding/removing elements).\n"
            "     CRITICAL — CSS SELECTORS: Do NOT modify existing CSS selectors. Only edit "
            "property values inside existing rules. Never add extra attribute conditions "
            "(e.g. data-param-*) to selectors — those attributes are injected separately and "
            "will not be present at style-match time. Keep every selector identical to the original.\n"
            "  3. If timeline dimensions are provided and block size does not match, scale CSS "
            "width/height/font-size to fill the canvas."
            + dims_instruction +
            "\nReturn ONLY the complete modified HTML file. No explanations, no markdown fences, "
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


def _resolve_ref_assets(params: dict, ref_folder: Path) -> dict:
    """Replace bare filenames in params with absolute paths from ref_folder.

    Only substitutes values that exactly match a file present in ref_folder.
    Returns a new dict; does not mutate the original.
    """
    if not ref_folder or not ref_folder.is_dir():
        return params
    available = {f.name: f for f in ref_folder.iterdir() if f.is_file()}
    resolved = {}
    for k, v in params.items():
        str_v = str(v)
        if str_v in available:
            resolved[k] = available[str_v].as_posix()
            log.debug("[renderer] ref asset resolved: %s → %s", str_v, resolved[k])
        else:
            resolved[k] = v
    return resolved


def render_placement(
    placement: GraphicPlacement,
    project_name: str,
    block_meta: dict | None = None,
    settings: Any = None,
    timeline_dims: tuple[int, int] | None = None,
    ref_folder: Path | None = None,
    provider: str | None = None,
    user_instructions: str | None = None,
) -> Path | None:
    """Render one GraphicPlacement to MOV (ProRes 4444 alpha) with WebM fallback.

    Returns Path to rendered file, or None on failure.
    block_meta:         catalog block dict (for dimensions/duration).
    settings:           SettingsManager for LLM HTML editing.
    timeline_dims:      (width, height) of Resolve timeline for aspect ratio matching.
    ref_folder:         optional user reference-assets directory; filenames in
                        placement.params that match a file here are replaced with
                        their absolute path before HTML injection.
    provider:           LLM provider name to use for HTML editing (None = auto).
    user_instructions:  free-text user guidance forwarded to the HTML-editing LLM.
    """
    workspace = _workspace_for(project_name, placement)
    log.info("[renderer] workspace: %s", workspace)

    if not add_block(placement.block, workspace):
        log.warning("[renderer] failed to add block %r", placement.block)
        return None

    # Find the installed block HTML in compositions/ (may be nested under components/)
    compositions_dir = workspace / "compositions"
    html_candidates = list(compositions_dir.glob("**/*.html")) if compositions_dir.exists() else []
    if not html_candidates:
        html_candidates = list(workspace.glob("*.html"))
    if not html_candidates:
        log.warning("[renderer] no HTML found in %s after add_block", workspace)
        return None

    block_html_path = html_candidates[0]

    # Resolve reference-asset filenames to absolute paths before injection
    effective_params = (
        _resolve_ref_assets(placement.params, ref_folder)
        if ref_folder else placement.params
    )
    placement = GraphicPlacement(
        block=placement.block,
        start_sec=placement.start_sec,
        duration_sec=placement.duration_sec,
        params=effective_params,
    )

    # LLM edits HTML with real transcript-derived values + aspect ratio fix + user layout instructions
    if settings is not None:
        _llm_edit_html(
            block_html_path, placement, settings,
            timeline_dims=timeline_dims,
            provider=provider,
            user_instructions=user_instructions,
        )

    _inject_params(block_html_path, placement.params)
    # _inject_params regex hits CSS selectors before DOM elements (style block comes first).
    # Re-sanitize to strip any param attrs it re-added to composition selectors.
    _html = block_html_path.read_text(encoding="utf-8")
    block_html_path.write_text(_sanitize_selectors(_html), encoding="utf-8")

    # hyperframes render needs a host index.html — build one wrapping the block
    block_html_rel = block_html_path.relative_to(workspace).as_posix()
    index_path = _make_index_html(workspace, placement.block, block_html_rel, block_meta or {})
    log.debug("[renderer] host index.html: %s", index_path)

    safe_name = re.sub(r"[^\w\-]", "_", placement.block)
    return _render_with_alpha(workspace, placement.block, safe_name, int(placement.start_sec))


def _render_with_alpha(workspace: Path, block: str, safe_name: str, start_sec: int) -> Path | None:
    """Try WebM (VP9+alpha), fall back to MOV (ProRes 4444) on failure."""
    for fmt, ext in (("mov", "mov"), ("webm", "webm")):
        output_path = workspace / f"{safe_name}_{start_sec}s.{ext}"
        try:
            result = subprocess.run(
                [
                    _NPX, "--yes", "hyperframes", "render",
                    str(workspace),
                    "-o", str(output_path),
                    "--fps", "30",
                    "--format", fmt,
                ],
                capture_output=True,
                text=True,
                timeout=_RENDER_TIMEOUT,
                cwd=str(workspace),
            )
            if result.returncode != 0:
                log.warning("[renderer] %s render failed for %r: %s", fmt, block, result.stderr[:300])
                continue
            if not output_path.exists():
                log.warning("[renderer] %s render exited 0 but %s not found", fmt, output_path.name)
                continue
            log.info("[renderer] rendered %r → %s (%s+alpha)", block, output_path, fmt)
            return output_path
        except subprocess.TimeoutExpired:
            log.warning("[renderer] %s render timed out for %r", fmt, block)
            continue
        except Exception as e:
            log.warning("[renderer] %s render error for %r: %s", fmt, block, e)
            continue
    return None
