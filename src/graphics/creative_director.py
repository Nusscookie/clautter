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

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
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
) -> str:
    import requests
    from src.utils.llm_providers import api_key_for

    key = api_key_for(settings, chosen)

    model_map = {
        "OpenAI": str(settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini"),
        "Gemini": str(settings.get("llm_gemini_model", "gemini-2.0-flash") or "gemini-2.0-flash"),
        "Minimax": str(settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01"),
        "NVIDIA": str(settings.get("llm_nvidia_model", "") or ""),
    }

    if chosen == "Gemini":
        url = _GEMINI_URL.replace("gemini-2.0-flash", model_map["Gemini"])
        resp = requests.post(
            f"{url}?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    url_map = {"OpenAI": _OPENAI_URL, "Minimax": _MINIMAX_URL, "NVIDIA": _NVIDIA_URL}
    payload: dict[str, Any] = {
        "model": model_map[chosen],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if chosen == "NVIDIA":
        payload["chat_template_kwargs"] = {"thinking": False}
    resp = requests.post(
        url_map[chosen],
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise ValueError(f"{chosen} returned empty content (finish_reason={finish!r})")
    return content


def _build_placement_prompt(
    transcript_text: str,
    segments: list[tuple[str, float]],
    total_duration_sec: float,
    timeline_dims: tuple[int, int] | None,
    user_instructions: str | None,
    ref_assets: list[str] | None,
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

    return (
        "You are a creative motion graphics director for a talking-head video.\n"
        "CREATIVE MODE: You will invent custom animations — do NOT reference any template library.\n\n"
        f"TRANSCRIPT (first 3000 chars):\n\"{transcript_text[:3000]}\"\n\n"
        f"TOTAL VIDEO DURATION: {total_duration_sec:.1f}s\n"
        + dims_block
        + "\nTRANSCRIPT SEGMENTS (index, start_time_seconds, spoken text):\n"
        + seg_lines + "\n"
        + ref_block
        + user_block
        + "\nDecide where to place custom motion graphics. Rules:\n"
        "  - Place at most 3 graphics total. Prefer fewer, higher-quality placements.\n"
        "  - Do NOT overlap graphics in time.\n"
        "  - Do NOT place anything in the first 5 seconds.\n"
        "  - Each graphic must fit within the video duration.\n"
        "  - For each placement, describe EXACTLY what to build in the `concept` field.\n"
        "    Be specific: visual style, what text/data to show, animation type.\n"
        "  - `screen_position`: where on canvas — center, bottom-left, top-right, bottom-center, etc.\n"
        + (f"  - Use dimensions matching the timeline ({timeline_dims[0]}x{timeline_dims[1]}).\n"
           if timeline_dims else "  - Use 1920x1080 dimensions.\n")
        + "\nRespond with ONLY a valid JSON array, nothing else:\n"
        "[\n"
        f"  {{\"start_sec\": 12.5, \"duration_sec\": 8.0, "
        f"\"concept\": \"detailed description of the animation\", "
        f"\"screen_position\": \"center\"{dims_str}}},\n"
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

    return (
        "You are an expert web animator. Build a single self-contained HTML animation.\n\n"
        f"CONCEPT: {concept}\n"
        f"DURATION: {duration_sec} seconds\n"
        f"SCREEN POSITION: {screen_position}\n"
        f"CANVAS SIZE: {width}x{height}px\n"
        + user_block
        + ref_block
        + "\nRequirements:\n"
        "  - Valid HTML5 starting with <!doctype html>\n"
        f"  - Root element must have: data-composition-id=\"anim\" data-duration=\"{duration_sec}\"\n"
        f"  - Body CSS: width:{width}px; height:{height}px; margin:0; overflow:hidden; background:transparent\n"
        f"  - For animations load GSAP from exactly: {_GSAP_CDN}\n"
        "  - GSAP timeline must be paused and registered:\n"
        "      const tl = gsap.timeline({ paused: true });\n"
        "      window.__timelines = window.__timelines || {};\n"
        "      window.__timelines[\"anim\"] = tl;\n"
        "  - All CSS and JS must be inline — no external files except the GSAP CDN URL above\n"
        "  - DO NOT use <img> tags unless a reference asset filename is provided\n"
        "  - Make the animation visually polished and relevant to the concept\n"
        "  - DO NOT use WebGL, WebGPU, or canvas-based rendering — pure HTML/CSS/GSAP only\n"
        "\nOutput raw HTML only. No markdown fences, no explanation, no preamble.\n"
        "Start your response with <!doctype html> immediately."
    )


def _extract_placements_json(text: str) -> list[dict]:
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()
    start = stripped.find("[")
    if start == -1:
        raise ValueError(f"no JSON array in response: {text[:200]!r}")
    obj, _ = json.JSONDecoder().raw_decode(stripped, start)
    if not isinstance(obj, list):
        raise ValueError("JSON response is not an array")
    return obj


def _save_html(html: str, project_name: str, idx: int) -> Path:
    safe = re.sub(r"[^\w\-]", "_", project_name or "unknown")
    ts = int(time.time())
    folder = _GRAPHICS_ROOT / safe / f"{ts}_custom_{idx}"
    folder.mkdir(parents=True, exist_ok=True)
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
        return [], "No cloud API key set. Add OpenAI, Gemini, Minimax, or NVIDIA key in Settings (⚙)."

    if chosen == "NVIDIA" and not str(settings.get("llm_nvidia_model", "") or "").strip():
        return [], "Set an NVIDIA model ID in Settings (⚙ → LLM Models)."

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

    # ── Call 1: placement decisions ───────────────────────────────────
    placement_prompt = _build_placement_prompt(
        transcript_text, segments, total_duration_sec,
        timeline_dims, user_instructions, ref_assets,
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

        html_prompt = _build_html_prompt(
            concept, duration_sec, screen_position, w, h,
            user_instructions, ref_assets,
        )
        try:
            html_reply = _call_llm(
                html_prompt,
                "You are a code editor. Output raw HTML only. No markdown, no explanation.",
                settings, chosen, 8192, 0.3,
            )
            # Strip think tags and markdown fences
            html_reply = re.sub(r"<think>.*?</think>", "", html_reply, flags=re.DOTALL).strip()
            html_reply = re.sub(r"^```(?:html)?\s*", "", html_reply, flags=re.IGNORECASE).strip()
            html_reply = re.sub(r"\s*```$", "", html_reply).strip()

            if not html_reply.startswith(("<!doctype", "<!DOCTYPE", "<!--", "<html", "<HTML", "<!")):
                log.warning("[creative] HTML generation non-HTML for idx=%d (starts: %r) — skipping", idx, html_reply[:80])
                continue

            html_path = _save_html(html_reply, project_name, idx)
            log.info("[creative] saved custom HTML for idx=%d → %s", idx, html_path)

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
