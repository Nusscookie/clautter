"""Cloud LLM re-ranking for autonomous B-roll mode.

Given a transcript segment and top-N candidate clip dicts, asks an
OpenAI-compatible or Gemini API to pick the best match. Falls back to
returning candidates as-is if no API key is configured or if the call fails.

This module has zero required deps beyond ``requests`` (already in requirements.txt).
"""

from __future__ import annotations
from typing import Any

from src.utils.llm_providers import call_llm, resolve_provider
from src.utils.logger import get_logger

log = get_logger(__name__)


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

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        log.debug("[reranker] no cloud API key — skipping re-rank")
        return candidates
    if chosen == "NVIDIA" and not (settings.get("llm_nvidia_model", "") or "").strip():
        log.debug("[reranker] NVIDIA selected but no model id set — skipping re-rank")
        return candidates

    prompt = _build_prompt(segment_text, top)
    source = chosen

    try:
        # No system prompt — this call wants a single number, not JSON.
        reply = call_llm(chosen, prompt, settings, max_tokens=8, temperature=0, system=None)

        best_idx = _parse_index(reply, len(top))
        log.info("[reranker] %s picked candidate %d for segment %r",
                 source, best_idx + 1, segment_text[:60])

        # Move winner to front, preserve rest of top, append tail
        reranked = [top[best_idx]] + [c for i, c in enumerate(top) if i != best_idx] + rest
        return reranked

    except Exception as e:
        log.warning("[reranker] cloud re-rank failed (%s) — using semantic order", e)
        return candidates
