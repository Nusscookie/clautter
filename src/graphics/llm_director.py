"""LLM-directed motion graphics placement.

Analyzes the transcript and available Hyperframes catalog blocks, then asks
a cloud LLM to decide which blocks to place and when. Returns a list of
placement dicts on success, empty list on any failure.

Follows the same provider-dispatch pattern as src/broll/llm_director.py.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_TIMEOUT = 90


@dataclass
class GraphicPlacement:
    """One motion graphic placement as decided by the LLM."""
    block: str               # Hyperframes block name (e.g. "data-chart")
    start_sec: float         # position on main timeline
    duration_sec: float      # how long to show it
    params: dict = field(default_factory=dict)  # block-specific parameters


def _build_prompt(
    transcript_text: str,
    segments: list[tuple[str, float]],
    total_duration_sec: float,
    blocks_summary: str,
    timeline_dims: tuple[int, int] | None = None,
    user_instructions: str | None = None,
    ref_assets: list[str] | None = None,
) -> str:
    seg_lines = "\n".join(
        f"  [{i+1}] {start:.1f}s — \"{text[:120]}\""
        for i, (text, start) in enumerate(segments)
    )

    if timeline_dims:
        tl_w, tl_h = timeline_dims
        is_portrait = tl_h > tl_w
        orientation = "PORTRAIT" if is_portrait else "LANDSCAPE"
        dims_rule = (
            f"\nTIMELINE: {tl_w}x{tl_h} ({orientation}). "
            "STRONGLY PREFER blocks whose native dimensions match this orientation. "
            "Only choose a block with a different orientation if no better match exists — "
            "in that case the HTML will be rewritten to fit, but it may look worse.\n"
        )
    else:
        dims_rule = ""

    if user_instructions:
        user_block = (
            "\nUSER INSTRUCTIONS (highest priority — follow these exactly):\n"
            f"{user_instructions}\n"
            "Use these to guide which blocks you choose, when and how many you place, "
            "what text/data you fill into params, and the overall visual style. "
            "They override the default rules below where they conflict.\n"
        )
    else:
        user_block = ""

    if ref_assets:
        asset_list = "\n".join(f"  {name}" for name in ref_assets)
        ref_block = (
            "\nREFERENCE ASSETS (user-supplied image files — prefer these for icons/logos/images):\n"
            f"{asset_list}\n"
            "When a block needs an icon, logo, profile picture, or image, reference one of "
            "these files by its exact filename in the params dict "
            "(e.g. \"icon\": \"profile_pic.png\", \"logo\": \"logo_white.svg\"). "
            "Do NOT invent filenames — only use names from the list above.\n"
        )
    else:
        ref_block = ""

    return (
        "You are an expert motion graphics editor enhancing a talking-head video.\n\n"
        f"TRANSCRIPT (full, first 3000 chars):\n\"{transcript_text[:3000]}\"\n\n"
        f"TOTAL VIDEO DURATION: {total_duration_sec:.1f}s\n"
        + dims_rule +
        "\nTRANSCRIPT SEGMENTS (index, start_time_seconds, spoken text):\n"
        f"{seg_lines}\n\n"
        "AVAILABLE HYPERFRAMES BLOCKS:\n"
        f"{blocks_summary}\n\n"
        "RENDERER NOTE: blocks tagged webgl, webgpu, gltf, shader, or "
        "liquid-glass-html-in-canvas require GPU rendering not available in this "
        "headless environment — they will fail to render. Avoid them.\n"
        + ref_block
        + user_block +
        "\nDecide which motion graphics to add. Rules:\n"
        "  - Only use blocks from the list above — exact name, no invented blocks.\n"
        "  - Place at most 3 graphics total. Prefer fewer, higher-quality placements.\n"
        "  - Do NOT overlap graphics in time (no two start_sec windows should overlap).\n"
        "  - Do NOT place anything in the first 5 seconds.\n"
        "  - Each graphic must fit within the video duration.\n"
        "  - Match the block to what is ACTUALLY SPOKEN:\n"
        "      data-chart → speaker mentions numbers, percentages, statistics, growth\n"
        "      flowchart → speaker explains a multi-step process or decision\n"
        "      instagram-follow/tiktok-follow/yt-lower-third → speaker references their social channel\n"
        "      x-post/reddit-post → speaker quotes or references a post/thread\n"
        "      spotify-card → speaker mentions a song, podcast, or audio content\n"
        "      macos-notification → speaker references an app notification or alert\n"
        "  - Fill `params` with REAL values extracted from the transcript — not placeholders.\n"
        "      For text blocks: channel name, handle, subscriber count, post text, notification message.\n"
        "      For data-chart: include 'title', 'labels' (array of category names), 'data' (array of numbers).\n"
        "      For any block: include every piece of text, number, or label the block might display.\n"
        "      Example: {\"channel_name\": \"TechTalk\", \"subscriber_count\": \"128K\", \"title\": \"Subscribe!\"}\n"
        "      Example: {\"title\": \"Monthly Revenue\", \"labels\": [\"Jan\",\"Feb\",\"Mar\"], \"data\": [12000,18500,24300]}\n"
        "  - Always return at least 1 placement. If no block is a perfect fit, pick the most relevant one.\n\n"
        "Respond with ONLY a valid JSON array, nothing else:\n"
        "[\n"
        "  {\"block\": \"block-name\", \"start_sec\": 12.5, \"duration_sec\": 8.0, "
        "\"params\": {\"title\": \"example\"}},\n"
        "  ...\n"
        "]"
    )


def _extract_json(text: str) -> list[dict]:
    original = text.strip()
    stripped = re.sub(r"<think>.*?</think>", "", original, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()

    think_match = re.search(r"<think>(.*?)</think>", original, flags=re.DOTALL)
    candidates = [stripped]
    if think_match:
        inner = re.sub(r"```(?:json)?", "", think_match.group(1)).strip()
        candidates.append(inner)

    for candidate in candidates:
        start = candidate.find("[")
        if start == -1:
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(candidate, start)
            if isinstance(obj, list):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    log.warning("[gfx_director] no JSON array in LLM reply: %r", original[:400])
    raise ValueError(f"no JSON array in LLM response: {original[:200]!r}")


def _parse_placements(raw: list[dict], valid_block_names: set[str]) -> list[GraphicPlacement]:
    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            block = str(item.get("block", "")).strip()
            if not block:
                continue
            if valid_block_names and block not in valid_block_names:
                log.debug("[gfx_director] unknown block %r — skipping", block)
                continue
            start_sec = float(item.get("start_sec", 0.0))
            duration_sec = float(item.get("duration_sec", 8.0))
            params = item.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            results.append(GraphicPlacement(
                block=block,
                start_sec=max(0.0, start_sec),
                duration_sec=max(1.0, duration_sec),
                params=params,
            ))
        except (KeyError, TypeError, ValueError) as e:
            log.debug("[gfx_director] skipping malformed item %r: %s", item, e)
    return results



def analyze(
    transcript_words: list[dict],
    blocks: list[dict],
    settings: Any,
    provider: str | None = None,
    timeline_dims: tuple[int, int] | None = None,
    user_instructions: str | None = None,
    ref_assets: list[str] | None = None,
) -> tuple[list[GraphicPlacement], str]:
    """Ask LLM which Hyperframes blocks to place and when.

    Args:
        transcript_words:  Raw transcript word dicts from app.transcript.
        blocks:            Catalog blocks from catalog_client.list_blocks().
        settings:          SettingsManager for API keys.
        provider:          Preferred provider name or None (auto-select).
        user_instructions: Optional free-text guidance from the user.
        ref_assets:        Filenames from the user's reference-assets folder.

    Returns:
        (placements, error_str). error_str is "" on success.
    """
    if not transcript_words:
        return [], "No transcript available. Generate one in the Subtitles tab first."
    if not blocks:
        return [], "No Hyperframes blocks found. Check Node.js and network access."

    from src.utils.llm_providers import api_key_for, call_llm, resolve_provider
    from src.graphics.catalog_client import block_summary

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

    # Build segments (15-word chunks with timestamps, same as suggester)
    segments: list[tuple[str, float]] = []
    buf_words: list[str] = []
    buf_start = 0.0
    import re as _re
    for entry in transcript_words:
        if entry.get("type") != "word":
            continue
        word = entry.get("word", "").strip()
        if not word:
            continue
        if not buf_words:
            buf_start = entry.get("start_sec", 0.0)
        buf_words.append(word)
        if _re.search(r"[.!?]$", word) or len(buf_words) >= 15:
            segments.append((" ".join(buf_words), buf_start))
            buf_words = []
    if buf_words:
        segments.append((" ".join(buf_words), buf_start))

    total_duration_sec = segments[-1][1] + 5.0 if segments else 0.0
    valid_names = {b.get("name", "") for b in blocks}
    prompt = _build_prompt(
        transcript_text, segments, total_duration_sec, block_summary(blocks),
        timeline_dims=timeline_dims, user_instructions=user_instructions,
        ref_assets=ref_assets,
    )

    max_tokens = int(settings.get("llm_max_tokens", 1500) or 1500)
    temperature = float(settings.get("llm_temperature", 0.1) or 0.1)
    _GFX_SYSTEM = (
        "You are an expert motion graphics editor. "
        "Respond with ONLY valid JSON arrays — no explanations, no markdown, no prose."
    )

    try:
        reply = call_llm(
            chosen, prompt, settings,
            max_tokens=max_tokens,
            temperature=temperature,
            system=_GFX_SYSTEM,
        )

        log.debug("[gfx_director] %s reply (first 500 chars): %s", chosen, reply[:500])
        if not reply or not reply.strip():
            return [], f"{chosen} returned an empty response. Check API key and quota."

        raw = _extract_json(reply)
        placements = _parse_placements(raw, valid_names)
        log.info("[gfx_director] %s returned %d placement(s)", chosen, len(placements))

        if not placements:
            return [], f"{chosen} found no suitable motion graphics for this transcript."
        return placements, ""

    except Exception as e:
        log.warning("[gfx_director] API call or parse failed: %s", e)
        return [], f"LLM call failed: {e}"
