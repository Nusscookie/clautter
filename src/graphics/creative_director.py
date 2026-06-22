"""Creative-mode motion graphics director.

Instead of picking from the Hyperframes catalog, the LLM generates fully custom
HTML/CSS/JS animations from scratch and saves them as standalone composition files
that Hyperframes can render.

Pipeline per run():
  Call 1 — Placement + concept: LLM reads transcript and decides WHERE to place
            graphics and WHAT to build (concept description + timing).
  Call 2 — HTML generation (one per placement): LLM builds a self-contained
            HTML animation file matching the concept, duration, and canvas size.

Returns GraphicPlacement objects with block="_custom" and
params["_html_path"] pointing to the generated HTML file.
"""

from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Any

from src.constants import PATHS
from src.utils.logger import get_logger
from src.graphics.llm_director import GraphicPlacement

log = get_logger(__name__)

_TIMEOUT = 120

_GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
_GRAPHICS_ROOT = PATHS.GRAPHICS_CACHE


def _call_llm(
    prompt: str,
    system: str,
    settings: Any,
    chosen: str,
    max_tokens: int,
    temperature: float,
    for_codegen: bool = False,
) -> str:
    from src.utils.llm_providers import call_llm, model_for

    model = model_for(settings, chosen)

    if for_codegen:
        # Upgrade cheap defaults for code generation — respect explicit user choices.
        if chosen == "OpenAI" and model == "gpt-4o-mini":
            model = "gpt-4o"
        elif chosen == "Gemini" and model == "gemini-2.0-flash":
            model = "gemini-2.5-flash-preview-05-20"

    return call_llm(
        chosen, prompt, settings,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        model=model,
    )


def _build_design_prompt(
    transcript_text: str,
    timeline_dims: tuple[int, int] | None,
    user_instructions: str | None,
) -> str:
    """Prompt for Call 0 — derive a shared design system (DESIGN.md-equivalent JSON)."""
    dims_block = ""
    if timeline_dims:
        tl_w, tl_h = timeline_dims
        orientation = "PORTRAIT" if tl_h > tl_w else "LANDSCAPE"
        dims_block = f"\nTIMELINE: {tl_w}x{tl_h} px ({orientation}).\n"

    user_block = ""
    if user_instructions:
        user_block = (
            "\nUSER INSTRUCTIONS (highest priority — honor these in the design):\n"
            f"{user_instructions}\n"
        )

    return (
        "You are an art director defining a SHARED visual design system for a set of motion\n"
        "graphics overlaid on a talking-head video. Every graphic will use this system so the\n"
        "whole set looks like one cohesive production.\n\n"
        f"TRANSCRIPT (first 2000 chars):\n\"{transcript_text[:2000]}\"\n"
        + dims_block
        + user_block
        + "\nDefine the system. Choose a mood that fits the content (e.g. minimal Swiss, "
        "high-energy social, editorial, technical/data).\n"
        "\nRespond with ONLY a valid JSON object, nothing else:\n"
        "{\n"
        '  "mood": "short phrase, e.g. minimal editorial",\n'
        '  "palette": {"bg": "#0b0b0d", "fg": "#ffffff", "accent": "#D97757", "muted": "#9aa0a6", "highlight": "#ffd166"},\n'
        '  "font_family": "a web-safe CSS font stack",\n'
        '  "type_scale": {"display": 96, "title": 56, "body": 32, "caption": 22},\n'
        '  "motion_feel": "one of: smooth, snappy, bouncy, springy, dramatic, dreamy",\n'
        '  "gsap_ease": "a concrete GSAP ease matching motion_feel, e.g. power3.out, back.out(1.7), elastic.out(1,0.4)",\n'
        '  "safe_area_pct": 6\n'
        "}"
    )


def _build_placement_prompt(
    transcript_text: str,
    segments: list[tuple[str, float]],
    total_duration_sec: float,
    timeline_dims: tuple[int, int] | None,
    user_instructions: str | None,
    ref_assets: list[str] | None,
    design_system: dict | None = None,
) -> str:
    seg_lines = "\n".join(
        f"  [{i + 1}] {start:.1f}s — \"{text[:120]}\""
        for i, (text, start) in enumerate(segments)
    )

    dims_block = ""
    if timeline_dims:
        tl_w, tl_h = timeline_dims
        orientation = "PORTRAIT" if tl_h > tl_w else "LANDSCAPE"
        dims_block = f"\nTIMELINE: {tl_w}x{tl_h} px ({orientation}).\n"

    user_block = ""
    if user_instructions:
        user_block = (
            "\nUSER INSTRUCTIONS (highest priority — this is the creative brief, follow exactly):\n"
            f"{user_instructions}\n"
        )

    ref_block = ""
    if ref_assets:
        ref_block = (
            "\nREFERENCE ASSETS (available image files — use exact filenames if needed):\n"
            + "\n".join(f"  {n}" for n in ref_assets) + "\n"
        )

    dims_str = ""
    if timeline_dims:
        tl_w, tl_h = timeline_dims
        dims_str = f", \"dimensions\": {{\"width\": {tl_w}, \"height\": {tl_h}}}"

    design_block = ""
    if design_system:
        design_block = (
            "\nSHARED DESIGN SYSTEM (every placement must obey this so the set is cohesive):\n"
            + json.dumps(design_system, indent=2) + "\n"
        )

    return (
        "You are a creative motion graphics director for a talking-head video.\n"
        "CREATIVE MODE: You will invent custom animations — do NOT reference any template library.\n\n"
        f"TRANSCRIPT (first 3000 chars):\n\"{transcript_text[:3000]}\"\n\n"
        f"TOTAL VIDEO DURATION: {total_duration_sec:.1f}s\n"
        + dims_block
        + design_block
        + "\nTRANSCRIPT SEGMENTS (index, start_time_seconds, spoken text):\n"
        + seg_lines + "\n"
        + ref_block
        + user_block
        + "\nStoryboard the placements. Rules:\n"
        "  - Place at most 3 graphics total. Prefer fewer, higher-quality placements.\n"
        "  - Do NOT overlap graphics in time.\n"
        "  - Do NOT place anything in the first 5 seconds.\n"
        "  - Each graphic must fit within the video duration.\n"
        "  - `concept`: describe EXACTLY what to build — visual style, what text/data to show.\n"
        "  - `technique`: the dominant animation approach — one of: per-word-typography, "
        "line-draw-svg, counter, data-viz, kinetic-text, lower-third, callout. Pick what fits the beat.\n"
        "  - `entrance` / `exit`: how the graphic comes in and leaves (e.g. \"slide up + fade\", "
        "\"draw on\", \"scale pop\", \"wipe out\"). Every graphic needs a deliberate exit, not a hard cut.\n"
        "  - `layout`: arrangement of elements (e.g. \"centered stack\", \"left-aligned lower third\").\n"
        "  - `screen_position`: center, bottom-left, top-right, bottom-center, etc.\n"
        + (f"  - Use dimensions matching the timeline ({timeline_dims[0]}x{timeline_dims[1]}).\n"
           if timeline_dims else "  - Use 1920x1080 dimensions.\n")
        + "\nRespond with ONLY a valid JSON array, nothing else:\n"
        "[\n"
        f"  {{\"start_sec\": 12.5, \"duration_sec\": 8.0, "
        f"\"concept\": \"detailed description\", \"technique\": \"per-word-typography\", "
        f"\"entrance\": \"slide up + fade\", \"exit\": \"fade + slide down\", "
        f"\"layout\": \"centered stack\", \"screen_position\": \"center\"{dims_str}}},\n"
        "  ...\n"
        "]"
    )


def _build_html_prompt(
    concept: str,
    duration_sec: float,
    screen_position: str,
    width: int,
    height: int,
    user_instructions: str | None,
    ref_assets: list[str] | None,
    design_system: dict | None = None,
    beat: dict | None = None,
) -> str:
    user_block = ""
    if user_instructions:
        user_block = (
            f"\nUSER INSTRUCTIONS (highest priority):\n{user_instructions}\n"
        )

    ref_block = ""
    if ref_assets:
        ref_block = (
            "\nREFERENCE ASSETS AVAILABLE (use exact filenames as src attributes if needed):\n"
            + "\n".join(f"  {n}" for n in ref_assets) + "\n"
            "Only reference these filenames if a file is genuinely needed by the concept.\n"
        )

    design_block = ""
    if design_system:
        design_block = (
            "\nDESIGN SYSTEM (use these exact colors, fonts, type scale and ease — do not invent your own):\n"
            + json.dumps(design_system, indent=2) + "\n"
        )

    beat_block = ""
    if beat:
        technique = beat.get("technique", "")
        entrance = beat.get("entrance", "")
        exit_ = beat.get("exit", "")
        layout = beat.get("layout", "")
        beat_block = (
            "\nSTORYBOARD DIRECTION FOR THIS BEAT:\n"
            f"  technique: {technique}\n"
            f"  entrance: {entrance}\n"
            f"  exit: {exit_}\n"
            f"  layout: {layout}\n"
            "  Implement exactly this technique. Apply the entrance at the start of the timeline\n"
            "  and the exit at the end (do not leave the graphic frozen on screen at the end).\n"
        )

    return (
        "You are an expert web animator. Build a single self-contained HTML animation\n"
        "for the Hyperframes deterministic frame renderer.\n\n"
        f"CONCEPT: {concept}\n"
        f"DURATION: {duration_sec} seconds\n"
        f"SCREEN POSITION: {screen_position}\n"
        f"CANVAS SIZE: {width}x{height}px\n"
        + design_block
        + beat_block
        + user_block
        + ref_block
        + "\nHOW HYPERFRAMES RENDERS (read carefully — this is why determinism matters):\n"
        "  Hyperframes does NOT play your animation in real time. It seeks a paused GSAP\n"
        "  timeline to t = frame/fps and screenshots each frame. The same frame must always\n"
        "  produce identical pixels. Any animation NOT on the registered timeline is invisible\n"
        "  or flickers.\n"
        "\nStructure requirements:\n"
        "  - Valid HTML5 starting with <!doctype html>\n"
        f"  - Body CSS: width:{width}px; height:{height}px; margin:0; padding:0; overflow:hidden; background:transparent\n"
        "  - CRITICAL: the FIRST child of <body> must be a <div> that is the composition root:\n"
        f"      <div id=\"root\" data-composition-id=\"anim\" data-duration=\"{duration_sec}\" "
        f"data-width=\"{width}\" data-height=\"{height}\" style=\"position:relative;width:100%;height:100%;\">\n"
        "    Do NOT put data-composition-id on the <html> element — it must be on this div.\n"
        "    All visual content goes inside this root div.\n"
        f"  - Load GSAP from exactly: {_GSAP_CDN}\n"
        "  - GSAP timeline must be paused and registered:\n"
        "      const tl = gsap.timeline({ paused: true });\n"
        "      window.__timelines = window.__timelines || {};\n"
        "      window.__timelines[\"anim\"] = tl;\n"
        "  - All CSS and JS inline — no external files except the GSAP CDN URL above\n"
        "  - DO NOT use <img> tags unless a reference asset filename is provided\n"
        "\nDETERMINISM CONTRACT (mandatory — violating this is the #1 cause of broken output):\n"
        "  - ALL motion lives on the registered paused GSAP timeline. The seek IS the clock.\n"
        "  - DO NOT call tl.play(). Never auto-play.\n"
        "  - FORBIDDEN: Date.now(), performance.now(), requestAnimationFrame, setTimeout/setInterval\n"
        "    for animation, and any wall-clock or real-time loop.\n"
        "  - FORBIDDEN: unseeded Math.random(). If you need randomness, use a seeded PRNG so it is\n"
        "    reproducible, e.g.:\n"
        "      function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}\n"
        "      const rand = mulberry32(12345);\n"
        "  - FORBIDDEN: runtime network calls / fetch. Everything inline or via the GSAP CDN.\n"
        "\nALLOWED techniques (use them to make it slick, not just CSS transforms):\n"
        "  - Canvas 2D: allowed, but you MUST redraw inside a gsap timeline callback (onUpdate /\n"
        "    a tweened proxy object), driven by timeline progress — NEVER a requestAnimationFrame loop.\n"
        "  - SVG: allowed, including path drawing (stroke-dashoffset tweened on the timeline).\n"
        "  - Per-word / per-character typography, staggered reveals, counters, simple data-viz.\n"
        "  - FORBIDDEN: WebGL, WebGPU (capture reliability).\n"
        "\nQuality bar: use the design system's colors/fonts/ease for everything; every element\n"
        "gets a deliberate entrance and exit on the timeline; respect the design system's\n"
        "safe-area padding; make it relevant to the concept and visually polished.\n"
        "\nOutput raw HTML only. No markdown fences, no explanation, no preamble.\n"
        "Start your response with <!doctype html> immediately."
    )


def _strip_trailing_commas(s: str) -> str:
    """Remove trailing commas before } or ] to fix common LLM JSON output."""
    return re.sub(r",\s*([}\]])", r"\1", s)


def _extract_json_object(text: str) -> dict:
    """Extract the first JSON object from an LLM reply (for the design-system call)."""
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()
    stripped = _strip_trailing_commas(stripped)
    start = stripped.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    obj, _ = json.JSONDecoder().raw_decode(stripped, start)
    if not isinstance(obj, dict):
        raise ValueError("JSON response is not an object")
    return obj


def _extract_placements_json(text: str) -> list[dict]:
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()
    stripped = _strip_trailing_commas(stripped)
    start = stripped.find("[")
    if start == -1:
        raise ValueError(f"no JSON array in response: {text[:200]!r}")
    obj, _ = json.JSONDecoder().raw_decode(stripped, start)
    if not isinstance(obj, list):
        raise ValueError("JSON response is not an array")
    return obj


def _design_to_md(design: dict) -> str:
    """Render the design-system JSON as a DESIGN.md for workspace provenance."""
    pal = design.get("palette", {}) or {}
    scale = design.get("type_scale", {}) or {}
    lines = [
        "# DESIGN.md — shared motion-graphics design system",
        "",
        f"- **Mood:** {design.get('mood', '')}",
        f"- **Font family:** {design.get('font_family', '')}",
        f"- **Motion feel:** {design.get('motion_feel', '')}",
        f"- **GSAP ease:** {design.get('gsap_ease', '')}",
        f"- **Safe-area:** {design.get('safe_area_pct', '')}%",
        "",
        "## Palette",
        *(f"- `{k}`: {v}" for k, v in pal.items()),
        "",
        "## Type scale (px)",
        *(f"- `{k}`: {v}" for k, v in scale.items()),
        "",
    ]
    return "\n".join(lines)


def _save_workspace(
    html: str, project_name: str, idx: int, design: dict | None
) -> Path:
    """Write a per-beat Hyperframes workspace and return the composition HTML path.

    Layout:
      <ts>_custom_<idx>/
        DESIGN.md          (when a design system was derived — provenance/reuse)
        composition.html   (the beat; rendered standalone by the renderer)
    """
    safe = re.sub(r"[^\w\-]", "_", project_name or "unknown")
    ts = int(time.time())
    folder = _GRAPHICS_ROOT / safe / f"{ts}_custom_{idx}"
    folder.mkdir(parents=True, exist_ok=True)
    if design:
        try:
            (folder / "DESIGN.md").write_text(_design_to_md(design), encoding="utf-8")
            (folder / "design.json").write_text(json.dumps(design, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug("[creative] could not persist design system: %s", e)
    html_path = folder / "composition.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def generate(
    transcript_words: list[dict],
    settings: Any,
    provider: str | None = None,
    timeline_dims: tuple[int, int] | None = None,
    user_instructions: str | None = None,
    ref_assets: list[str] | None = None,
    project_name: str = "",
) -> tuple[list[GraphicPlacement], str]:
    """Generate custom HTML animations for placement on the timeline.

    Returns:
        (placements, error_str). error_str is "" on success.
        Each placement has block="_custom" and params["_html_path"] set.
    """
    if not transcript_words:
        return [], "No transcript available. Generate one in the Subtitles tab first."

    from src.utils.llm_providers import resolve_provider

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        return [], "No cloud API key set. Add OpenAI, Gemini, Minimax, NVIDIA, or Ollama key in Settings (⚙)."

    if chosen == "NVIDIA" and not str(settings.get("llm_nvidia_model", "") or "").strip():
        return [], "Set an NVIDIA model ID in Settings (⚙ → LLM Models)."

    if chosen == "Ollama" and not str(settings.get("llm_ollama_model", "") or "").strip():
        return [], "Set an Ollama model name in Settings (⚙ → LLM Models)."

    transcript_text = " ".join(
        w["word"] for w in transcript_words if w.get("type") == "word"
    )

    segments: list[tuple[str, float]] = []
    buf_words: list[str] = []
    buf_start = 0.0
    for entry in transcript_words:
        if entry.get("type") != "word":
            continue
        word = entry.get("word", "").strip()
        if not word:
            continue
        if not buf_words:
            buf_start = entry.get("start_sec", 0.0)
        buf_words.append(word)
        if re.search(r"[.!?]$", word) or len(buf_words) >= 15:
            segments.append((" ".join(buf_words), buf_start))
            buf_words = []
    if buf_words:
        segments.append((" ".join(buf_words), buf_start))

    total_duration_sec = segments[-1][1] + 5.0 if segments else 0.0

    max_tokens_placement = int(settings.get("llm_max_tokens", 1500) or 1500)
    temperature = float(settings.get("llm_temperature", 0.1) or 0.1)

    # ── Call 0: shared design system (cohesion across all placements) ──
    design_system: dict | None = None
    try:
        design_reply = _call_llm(
            _build_design_prompt(transcript_text, timeline_dims, user_instructions),
            "You are an art director. Respond with ONLY a valid JSON object — no prose, no markdown.",
            settings, chosen, 600, temperature,
        )
        design_system = _extract_json_object(design_reply)
        log.info("[creative] design system: %s", json.dumps(design_system)[:300])
    except Exception as e:
        # Non-fatal — proceed without a shared system (each beat then self-directs).
        log.warning("[creative] design-system call failed (continuing without): %s", e)

    # ── Call 1: placement / storyboard decisions ──────────────────────
    placement_prompt = _build_placement_prompt(
        transcript_text, segments, total_duration_sec,
        timeline_dims, user_instructions, ref_assets,
        design_system=design_system,
    )
    try:
        placement_reply = _call_llm(
            placement_prompt,
            "You are an expert motion graphics director. Respond with ONLY valid JSON arrays — no explanations, no markdown, no prose.",
            settings, chosen, max_tokens_placement, temperature,
        )
        log.debug("[creative] placement reply (500 chars): %s", placement_reply[:500])
        raw_placements = _extract_placements_json(placement_reply)
    except Exception as e:
        log.warning("[creative] placement call failed: %s", e)
        return [], f"Creative mode placement LLM call failed: {e}"

    if not raw_placements:
        return [], "Creative mode LLM returned no placements."

    # ── Call 2: HTML generation per placement ─────────────────────────
    default_w, default_h = timeline_dims if timeline_dims else (1920, 1080)
    placements: list[GraphicPlacement] = []

    for idx, item in enumerate(raw_placements[:3]):
        if not isinstance(item, dict):
            continue
        try:
            start_sec = float(item.get("start_sec", 0.0))
            duration_sec = max(1.0, float(item.get("duration_sec", 8.0)))
            concept = str(item.get("concept", "animated motion graphic")).strip()
            screen_position = str(item.get("screen_position", "center")).strip()
            dims = item.get("dimensions") or {}
            w = int(dims.get("width", default_w))
            h = int(dims.get("height", default_h))
        except (TypeError, ValueError) as e:
            log.debug("[creative] skipping malformed placement item %r: %s", item, e)
            continue

        beat = {
            "technique": str(item.get("technique", "")).strip(),
            "entrance": str(item.get("entrance", "")).strip(),
            "exit": str(item.get("exit", "")).strip(),
            "layout": str(item.get("layout", "")).strip(),
        }

        html_prompt = _build_html_prompt(
            concept, duration_sec, screen_position, w, h,
            user_instructions, ref_assets,
            design_system=design_system,
            beat=beat,
        )
        try:
            html_reply = _call_llm(
                html_prompt,
                "You are a code editor. Output raw HTML only. No markdown, no explanation.",
                settings, chosen, 8192, 0.3,
                for_codegen=True,
            )
            # Strip think tags and markdown fences
            html_reply = re.sub(r"<think>.*?</think>", "", html_reply, flags=re.DOTALL).strip()
            html_reply = re.sub(r"^```(?:html)?\s*", "", html_reply, flags=re.IGNORECASE).strip()
            html_reply = re.sub(r"\s*```$", "", html_reply).strip()

            if not html_reply.startswith(("<!doctype", "<!DOCTYPE", "<!--", "<html", "<HTML", "<!")):
                log.warning("[creative] HTML generation non-HTML for idx=%d (starts: %r) — skipping", idx, html_reply[:80])
                continue

            html_path = _save_workspace(html_reply, project_name, idx, design_system)
            log.info("[creative] saved custom workspace for idx=%d → %s", idx, html_path)

            placements.append(GraphicPlacement(
                block="_custom",
                start_sec=max(0.0, start_sec),
                duration_sec=duration_sec,
                params={
                    "_html_path": str(html_path),
                    "_concept": concept,
                    "_width": w,
                    "_height": h,
                },
            ))
        except Exception as e:
            log.warning("[creative] HTML generation failed for idx=%d: %s", idx, e)
            continue

    if not placements:
        return [], "Creative mode could not generate any valid HTML animations. Check logs for details."

    log.info("[creative] generated %d custom placement(s)", len(placements))
    return placements, ""
