"""Cloud LLM re-ranking for autonomous B-roll mode.

Given a transcript segment and top-N candidate clip dicts, asks an
OpenAI-compatible or Gemini API to pick the best match. Falls back to
returning candidates as-is if no API key is configured or if the call fails.

This module has zero required deps beyond ``requests`` (already in requirements.txt).
"""

from __future__ import annotations
import json
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_MINIMAX_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_TIMEOUT = 15


def _build_prompt(segment_text: str, candidates: list[dict]) -> str:
    clip_lines = "\n".join(
        f"  {i + 1}. {c['clip_name']} (keywords: {', '.join(c.get('matched_keywords', [])[:5])})"
        for i, c in enumerate(candidates)
    )
    return (
        "You are a video editor choosing B-roll footage.\n\n"
        f"Transcript segment:\n\"{segment_text}\"\n\n"
        f"Candidate clips:\n{clip_lines}\n\n"
        "Reply with only the number (1, 2, or 3) of the best matching clip. "
        "No explanation."
    )


def _parse_index(text: str, n: int) -> int:
    """Return 0-based index from model reply, clamped to valid range."""
    for tok in text.strip().split():
        try:
            idx = int(tok) - 1
            if 0 <= idx < n:
                return idx
        except ValueError:
            continue
    return 0


def _call_openai(prompt: str, api_key: str) -> str:
    import requests
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "temperature": 0,
    }
    resp = requests.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, api_key: str) -> str:
    import requests
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(
        f"{_GEMINI_URL}?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_minimax(prompt: str, api_key: str) -> str:
    import requests
    payload = {
        "model": "MiniMax-Text-01",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "temperature": 0,
    }
    resp = requests.post(
        _MINIMAX_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_nvidia(prompt: str, api_key: str, model: str) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "temperature": 0,
        "chat_template_kwargs": {"thinking": False},
    }
    resp = requests.post(
        _NVIDIA_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def rerank(
    segment_text: str,
    candidates: list[dict],
    settings: Any,
    provider: str | None = None,
) -> list[dict]:
    """Re-rank *candidates* using a cloud LLM if an API key is available.

    Args:
        segment_text: The transcript segment text for context.
        candidates:   Clip dicts from matcher, already sorted by semantic score.
                      Only the top-3 are sent to the LLM; the rest are appended.
        settings:     SettingsManager instance for reading API keys.

    Returns:
        Re-ordered candidates list (best first). Returns *candidates* unchanged
        on any error or if no API key is present.
    """
    if not candidates or not segment_text.strip():
        return candidates

    top = candidates[:3]
    rest = candidates[3:]

    from src.utils.llm_providers import api_key_for, resolve_provider

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        log.debug("[reranker] no cloud API key — skipping re-rank")
        return candidates
    if chosen == "NVIDIA" and not (settings.get("llm_nvidia_model", "") or "").strip():
        log.debug("[reranker] NVIDIA selected but no model id set — skipping re-rank")
        return candidates

    prompt = _build_prompt(segment_text, top)
    key = api_key_for(settings, chosen)
    source = chosen

    try:
        if chosen == "OpenAI":
            reply = _call_openai(prompt, key)
        elif chosen == "Gemini":
            reply = _call_gemini(prompt, key)
        elif chosen == "NVIDIA":
            reply = _call_nvidia(prompt, key, str(settings.get("llm_nvidia_model", "")).strip())
        else:
            reply = _call_minimax(prompt, key)

        best_idx = _parse_index(reply, len(top))
        log.info("[reranker] %s picked candidate %d for segment %r",
                 source, best_idx + 1, segment_text[:60])

        # Move winner to front, preserve rest of top, append tail
        reranked = [top[best_idx]] + [c for i, c in enumerate(top) if i != best_idx] + rest
        return reranked

    except Exception as e:
        log.warning("[reranker] cloud re-rank failed (%s) — using semantic order", e)
        return candidates
