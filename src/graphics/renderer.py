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
        from src.utils.llm_providers import resolve_provider, call_llm

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
            "NOTE: Any param value that looks like a filename (e.g. 'logo.png', 'icon.svg') is a "
            "local asset copied into the same directory as this HTML file. Reference it with a "
            "bare filename only (e.g. src=\"logo.png\", NOT an absolute path).\n\n"
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

        system = "You are a code editor. Output raw HTML only. No markdown, no explanation."
        reply = call_llm(
            chosen, prompt, settings,
            max_tokens=8192,
            temperature=0.1,
            system=system,
        )

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


def _make_index_html(
    workspace: Path,
    block_name: str,
    block_html_rel: str,
    block: dict,
    duration_override: float | None = None,
) -> Path:
    """Generate a host index.html that embeds the block composition.

    hyperframes render requires an index.html at the workspace root that uses
    data-composition-src to reference the installed block HTML. The block cannot
    be rendered directly.
    """
    dims = block.get("dimensions") or {}
    width = dims.get("width", 1920)
    height = dims.get("height", 1080)
    duration = duration_override if duration_override is not None else block.get("duration", 15)
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
    # ── Creative mode: pre-built custom HTML, skip catalog steps ────────
    if placement.block == "_custom":
        html_path_str = placement.params.get("_html_path", "")
        if not html_path_str or not Path(html_path_str).exists():
            log.warning("[renderer] _custom placement missing _html_path: %r", html_path_str)
            return None

        block_html_path = Path(html_path_str)
        workspace = block_html_path.parent
        log.info("[renderer] creative mode workspace: %s", workspace)

        # Copy ref assets into workspace so Hyperframes file server can find them.
        if ref_folder and ref_folder.is_dir():
            import shutil as _shutil
            for asset in ref_folder.iterdir():
                if asset.is_file():
                    dest = workspace / asset.name
                    if not dest.exists():
                        try:
                            _shutil.copy2(asset, dest)
                            log.debug("[renderer] copied ref asset %s → workspace", asset.name)
                        except Exception as _e:
                            log.debug("[renderer] could not copy ref asset %s: %s", asset.name, _e)

        # Ensure data-composition-id and data-duration are on the ROOT WRAPPER DIV,
        # NOT on <html>. Hyperframes lint requires a div (not the html element) as the
        # composition root; placing these on <html> always fails the lint check.
        html_text = block_html_path.read_text(encoding="utf-8")
        dur = placement.duration_sec if placement.duration_sec > 0 else 8.0

        # If LLM (wrongly) placed composition attrs on <html>, strip them from there
        # and we'll re-inject on the body's first child div below.
        html_text = re.sub(
            r'(<html[^>]*?)\s+data-composition-id="[^"]*"',
            r'\1', html_text, count=1, flags=re.IGNORECASE,
        )
        html_text = re.sub(
            r'(<html[^>]*?)\s+data-duration="[^"]*"',
            r'\1', html_text, count=1, flags=re.IGNORECASE,
        )
        html_text = re.sub(
            r'(<html[^>]*?)\s+data-width="[^"]*"',
            r'\1', html_text, count=1, flags=re.IGNORECASE,
        )
        html_text = re.sub(
            r'(<html[^>]*?)\s+data-height="[^"]*"',
            r'\1', html_text, count=1, flags=re.IGNORECASE,
        )

        if 'data-composition-id' not in html_text:
            # No wrapper div present — inject one wrapping the body contents.
            html_text = re.sub(
                r'(<body[^>]*>)',
                rf'\1\n<div data-composition-id="anim" data-duration="{dur}" '
                rf'style="position:relative;width:100%;height:100%;">',
                html_text, count=1, flags=re.IGNORECASE,
            )
            html_text = re.sub(
                r'(</body>)',
                r'</div>\n\1',
                html_text, count=1, flags=re.IGNORECASE,
            )
            log.debug("[renderer] injected wrapper div with data-composition-id for _custom")
        elif 'data-duration' not in html_text:
            html_text = re.sub(
                r'(data-composition-id="[^"]*")',
                rf'\1 data-duration="{dur}"',
                html_text, count=1,
            )
            log.debug("[renderer] injected data-duration onto existing wrapper div")

        # Enforce correct body dimensions — LLMs sometimes output partial sizes
        # (e.g. body { height: 300px }) which causes Hyperframes "Set maximum size exceeded".
        # Inject/override width+height directly after the opening <body> style block.
        if timeline_dims:
            tl_w, tl_h = timeline_dims
            # Replace explicit body width/height declarations if present
            def _fix_body_dim(m: re.Match) -> str:
                body_css = m.group(1)
                body_css = re.sub(r'\bwidth\s*:\s*[^;]+;', f'width:{tl_w}px;', body_css)
                body_css = re.sub(r'\bheight\s*:\s*[^;]+;', f'height:{tl_h}px;', body_css)
                if 'width' not in body_css:
                    body_css = f'width:{tl_w}px;' + body_css
                if 'height' not in body_css:
                    body_css = f'height:{tl_h}px;' + body_css
                return f'body {{{body_css}}}'
            new_text = re.sub(r'body\s*\{([^}]*)\}', _fix_body_dim, html_text, count=1)
            if new_text != html_text:
                html_text = new_text
                log.debug("[renderer] enforced body dimensions %dx%d for _custom", tl_w, tl_h)

        # Remove tl.play() — Hyperframes controls timeline playback; manual play() breaks capture.
        html_text = re.sub(r'\btl\.play\(\)\s*;?\s*\n?', '', html_text)

        block_html_path.write_text(html_text, encoding="utf-8")

        # Use composition.html directly as index.html — Hyperframes renders
        # a standalone page without needing a data-composition-src wrapper.
        index_path = workspace / "index.html"
        if block_html_path.name != "index.html":
            import shutil as _shutil
            _shutil.copy2(block_html_path, index_path)
            log.debug("[renderer] copied composition.html → index.html")

        # Validate the composition (lint + headless Chrome) and self-heal once
        # before the expensive render. Catches determinism/structure bugs that
        # would otherwise produce a silently-broken MOV.
        _validate_and_heal(workspace, index_path, settings, provider)

        safe_name = f"custom_{int(placement.start_sec)}s"
        return _render_with_alpha(workspace, "_custom", safe_name, int(placement.start_sec))

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

    # Copy ref assets into workspace so Hyperframes' local file server can serve them.
    # Then remap absolute paths back to bare filenames (relative to workspace root).
    if ref_folder and ref_folder.is_dir():
        import shutil as _shutil
        remapped: dict = {}
        for k, v in effective_params.items():
            str_v = str(v)
            src_path = Path(str_v)
            if src_path.is_absolute() and src_path.is_file():
                dest = workspace / src_path.name
                if not dest.exists():
                    try:
                        _shutil.copy2(src_path, dest)
                        log.debug("[renderer] copied ref asset %s → workspace", src_path.name)
                    except Exception as _ce:
                        log.debug("[renderer] could not copy ref asset %s: %s", src_path.name, _ce)
                remapped[k] = src_path.name
            else:
                remapped[k] = v
        effective_params = remapped

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
    _html = _sanitize_selectors(_html)

    # Scale all data-duration attributes in the block HTML so Hyperframes renders
    # at placement.duration_sec instead of the catalog default.
    # Strategy: find the root composition element's data-duration to get original
    # total, then scale every data-duration value by the same factor.
    if placement.duration_sec > 0:
        _root_dur_match = re.search(
            r'data-composition-id="[^"]*"[\s\S]*?data-duration="([^"]+)"',
            _html,
        )
        if _root_dur_match:
            try:
                _orig_dur = float(_root_dur_match.group(1))
                if _orig_dur > 0:
                    _scale = placement.duration_sec / _orig_dur
                    def _scale_dur(m: re.Match) -> str:
                        try:
                            return f'{m.group(1)}{float(m.group(2)) * _scale}{m.group(3)}'
                        except ValueError:
                            return m.group(0)
                    _html = re.sub(
                        r'(data-duration=")([^"]+)(")',
                        _scale_dur,
                        _html,
                    )
                    log.debug(
                        "[renderer] scaled block durations ×%.3f (%.2fs → %.2fs) for %s",
                        _scale, _orig_dur, placement.duration_sec, placement.block,
                    )
            except (ValueError, ZeroDivisionError):
                pass

    block_html_path.write_text(_html, encoding="utf-8")

    # hyperframes render needs a host index.html — build one wrapping the block
    block_html_rel = block_html_path.relative_to(workspace).as_posix()
    index_path = _make_index_html(
        workspace, placement.block, block_html_rel, block_meta or {},
        duration_override=placement.duration_sec if placement.duration_sec > 0 else None,
    )
    log.debug("[renderer] host index.html: %s", index_path)

    safe_name = re.sub(r"[^\w\-]", "_", placement.block)
    return _render_with_alpha(workspace, placement.block, safe_name, int(placement.start_sec))


def _run_hyperframes(args: list[str], workspace: Path, timeout: int = 90) -> tuple[bool, str]:
    """Run an `npx hyperframes <args>` command in the workspace. Returns (ok, output)."""
    try:
        result = subprocess.run(
            [_NPX, "--yes", "hyperframes", *args],
            capture_output=True, text=True, timeout=timeout, cwd=str(workspace),
        )
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, f"hyperframes {args[0]} timed out"
    except FileNotFoundError:
        # npx/hyperframes not available — treat as "skip validation", don't block render.
        return True, ""
    except Exception as e:
        return False, str(e)


def _llm_repair_html(html: str, error_text: str, settings: Any, provider: str | None) -> str | None:
    """Ask the LLM to fix a composition that failed lint/validate. Returns fixed HTML or None."""
    try:
        from src.utils.llm_providers import resolve_provider, call_llm

        chosen = resolve_provider(settings, provider)
        if chosen is None:
            return None

        prompt = (
            "This Hyperframes HTML composition failed validation. Fix ONLY what the error reports.\n"
            "Key rules:\n"
            "  - data-composition-id MUST be on the first <div> inside <body>, NOT on <html>.\n"
            "    Correct: <body><div id='root' data-composition-id='anim' data-duration='N' "
            "data-width='W' data-height='H' style='position:relative;width:100%;height:100%;'>\n"
            "  - Determinism: all motion on a paused GSAP timeline at window.__timelines, "
            "no requestAnimationFrame / Date.now / setTimeout / unseeded Math.random, no tl.play().\n\n"
            f"VALIDATION ERROR:\n{error_text[:1500]}\n\n"
            f"HTML:\n```html\n{html[:8000]}\n```\n\n"
            "Return ONLY the complete fixed HTML, raw, starting with <!doctype — no markdown, no prose."
        )
        system = "You are a code editor. Output raw HTML only. No markdown, no explanation."
        reply = call_llm(
            chosen, prompt, settings,
            max_tokens=8192,
            temperature=0.1,
            system=system,
        )

        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        reply = re.sub(r"^```(?:html)?\s*", "", reply, flags=re.IGNORECASE).strip()
        reply = re.sub(r"\s*```$", "", reply).strip()
        if not reply.startswith(("<!doctype", "<!DOCTYPE", "<!--", "<html", "<HTML", "<!")):
            return None
        return reply
    except Exception as e:
        log.warning("[renderer] _llm_repair_html failed (non-fatal): %s", e)
        return None


def _validate_and_heal(
    workspace: Path, index_path: Path, settings: Any, provider: str | None
) -> None:
    """Run hyperframes lint + validate; on failure, attempt one LLM repair pass.

    Non-fatal: if tooling is missing or repair fails, leaves the composition as-is
    and lets the render proceed (it may still work / will fail loudly there).
    """
    for cmd in (["lint"], ["validate"]):
        ok, out = _run_hyperframes(cmd, workspace)
        if ok:
            continue
        # gsap_studio_edit_blocked is a Studio-IDE-only warning (⚠) about GSAP-targeted
        # elements not being drag-editable in the GUI — it has no effect on CLI render.
        # Hyperframes exits non-zero for warnings too, but we only need to heal real errors (✖).
        # Skip the expensive LLM repair pass when the only issues are warnings.
        _error_lines = [l for l in out.splitlines() if "✖" in l or "error" in l.lower()]
        _warn_only_patterns = ("gsap_studio_edit_blocked",)
        _has_real_errors = bool(_error_lines) and not all(
            any(p in l for p in _warn_only_patterns) for l in _error_lines
        )
        if not _has_real_errors:
            log.debug("[renderer] hyperframes %s: only warnings (no errors) — skipping heal, proceeding", cmd[0])
            continue
        log.warning("[renderer] hyperframes %s failed: %s", cmd[0], out[:300])
        if settings is None:
            return
        html = index_path.read_text(encoding="utf-8")
        fixed = _llm_repair_html(html, out, settings, provider)
        if not fixed:
            log.warning("[renderer] self-heal produced no fix for %s — rendering as-is", cmd[0])
            return
        index_path.write_text(fixed, encoding="utf-8")
        log.info("[renderer] self-heal applied after %s failure; re-validating", cmd[0])
        ok2, out2 = _run_hyperframes(cmd, workspace)
        if not ok2:
            log.warning("[renderer] still failing %s after heal: %s — rendering as-is", cmd[0], out2[:200])
            return


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
