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

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
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
) -> str:
    seg_lines = "\n".join(
        f"  [{i+1}] {start:.1f}s — \"{text[:120]}\""
        for i, (text, start) in enumerate(segments)
    )
    return (
        "You are an expert motion graphics editor enhancing a talking-head video.\n\n"
        f"TRANSCRIPT (full, first 3000 chars):\n\"{transcript_text[:3000]}\"\n\n"
        f"TOTAL VIDEO DURATION: {total_duration_sec:.1f}s\n\n"
        "TRANSCRIPT SEGMENTS (index, start_time_seconds, spoken text):\n"
        f"{seg_lines}\n\n"
        "AVAILABLE HYPERFRAMES BLOCKS:\n"
        f"{blocks_summary}\n\n"
        "Decide which motion graphics to add. Rules:\n"
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


def _call_openai(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert motion graphics editor. Respond with ONLY valid JSON arrays — no explanations, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    url = _GEMINI_URL.replace("gemini-2.0-flash", model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    resp = requests.post(
        f"{url}?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_minimax(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert motion graphics editor. Respond with ONLY valid JSON arrays — no explanations, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(
        _MINIMAX_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise ValueError(f"Minimax returned empty content (finish_reason={finish!r})")
    return content


def _call_nvidia(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert motion graphics editor. Respond with ONLY valid JSON arrays — no explanations, no markdown, no prose."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"thinking": False},
    }
    resp = requests.post(
        _NVIDIA_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise ValueError(f"NVIDIA returned empty content (finish_reason={finish!r})")
    return content


def analyze(
    transcript_words: list[dict],
    blocks: list[dict],
    settings: Any,
    provider: str | None = None,
) -> tuple[list[GraphicPlacement], str]:
    """Ask LLM which Hyperframes blocks to place and when.

    Args:
        transcript_words: Raw transcript word dicts from app.transcript.
        blocks:           Catalog blocks from catalog_client.list_blocks().
        settings:         SettingsManager for API keys.
        provider:         Preferred provider name or None (auto-select).

    Returns:
        (placements, error_str). error_str is "" on success.
    """
    if not transcript_words:
        return [], "No transcript available. Generate one in the Subtitles tab first."
    if not blocks:
        return [], "No Hyperframes blocks found. Check Node.js and network access."

    from src.utils.llm_providers import api_key_for, resolve_provider
    from src.graphics.catalog_client import block_summary

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        return [], "No cloud API key set. Add OpenAI, Gemini, Minimax, or NVIDIA key in Settings (⚙)."

    if chosen == "NVIDIA" and not str(settings.get("llm_nvidia_model", "") or "").strip():
        return [], "Set an NVIDIA model ID in Settings (⚙ → LLM Models)."

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
    prompt = _build_prompt(transcript_text, segments, total_duration_sec, block_summary(blocks))

    openai_model = str(settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini")
    gemini_model = str(settings.get("llm_gemini_model", "gemini-2.0-flash") or "gemini-2.0-flash")
    minimax_model = str(settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01")
    nvidia_model = str(settings.get("llm_nvidia_model", "") or "").strip()
    max_tokens = int(settings.get("llm_max_tokens", 1500) or 1500)
    temperature = float(settings.get("llm_temperature", 0.1) or 0.1)

    key = api_key_for(settings, chosen)
    try:
        if chosen == "OpenAI":
            reply = _call_openai(prompt, key, openai_model, max_tokens, temperature)
        elif chosen == "Gemini":
            reply = _call_gemini(prompt, key, gemini_model, max_tokens, temperature)
        elif chosen == "NVIDIA":
            reply = _call_nvidia(prompt, key, nvidia_model, max_tokens, temperature)
        else:
            reply = _call_minimax(prompt, key, minimax_model, max_tokens, temperature)

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
