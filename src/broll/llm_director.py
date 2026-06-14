"""Full LLM-directed B-roll placement.

Given the transcript (full text + segments with timestamps) and a candidate
clip list, asks a cloud LLM to return a complete placement plan as JSON:
which clip goes where on the timeline and which portion of the clip to use.

The LLM also receives extracted transcript keywords so it can reason about
relevance without seeing the actual video.

Returns an empty list on any API or parse failure so the caller degrades
gracefully. Distinguishes "no API key" from "API call failed" in logs.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.broll.llm_director_api import (
    call_anthropic,
    call_gemini,
    call_minimax,
    call_nvidia,
    call_openai,
)
from src.constants import SETTINGS_KEYS
from src.utils.logger import get_logger

log = get_logger(__name__)

# Returned when no API key is configured — caller can show a specific message
NO_KEY_SENTINEL = "__no_key__"


@dataclass
class PlacementDecision:
    """One clip placement as decided by the LLM."""
    clip_name: str
    timeline_sec: float    # where on timeline to place the clip
    clip_start_sec: float  # in-point within the clip
    clip_end_sec: float    # out-point within the clip


def _build_prompt(
    transcript_text: str,
    segments: list[tuple[str, float]],
    keywords: list[str],
    candidates: list[dict],
    max_placements: int,
    total_duration_sec: float = 0.0,
    intro_skip_sec: float = 4.0,
    min_gap_sec: float = 5.0,
    max_clip_sec: float = 6.0,
) -> str:
    seg_lines = "\n".join(
        f"  [{i+1}] {start:.1f}s — \"{text[:150]}\""
        for i, (text, start) in enumerate(segments)
    )
    # Normalise clip name: use full filename (with extension) as the canonical key
    clip_lines = "\n".join(
        f"  {i+1}. \"{c['_canon_name']}\" "
        f"keywords=[{', '.join(c.get('keywords') or [])}] "
        f"duration={c.get('duration_sec', 0.0):.1f}s"
        for i, c in enumerate(candidates)
    )
    kw_line = ", ".join(keywords) if keywords else "(none extracted)"
    duration_line = f"\nTOTAL VIDEO DURATION: {total_duration_sec:.1f}s\n" if total_duration_sec > 0 else ""
    return (
        "You are an expert video editor placing B-roll footage over a talking-head video.\n\n"
        f"TRANSCRIPT (full):\n\"{transcript_text[:3000]}\"\n"
        f"{duration_line}\n"
        f"KEY TOPICS FROM TRANSCRIPT: {kw_line}\n\n"
        "TRANSCRIPT SEGMENTS (index, start_time_seconds, spoken text):\n"
        f"{seg_lines}\n\n"
        "AVAILABLE B-ROLL CLIPS (canonical name, keywords, duration):\n"
        f"{clip_lines}\n\n"
        f"Create a B-roll placement plan with up to {max_placements} placements.\n"
        "For each placement choose:\n"
        "  - clip_name: EXACT canonical name from the list above (copy it exactly)\n"
        "  - timeline_sec: start time on the main timeline in seconds "
        "(use a value from the segment list above)\n"
        "  - clip_start_sec: in-point within the clip (0.0 to duration)\n"
        f"  - clip_end_sec: out-point within the clip (clip_start_sec + 2 to {max_clip_sec:.0f}s, <= duration)\n\n"
        "Rules:\n"
        "  - Use each clip at most once.\n"
        "  - Match clip content to what is being said at that moment.\n"
        "  - Prefer clips whose keywords overlap with the transcript topics.\n"
        "  - Only use clips from the list above — no invented names.\n"
        f"  - Do NOT place any B-roll in the first {intro_skip_sec:.0f} seconds "
        "(the speaker's face must be visible at the start).\n"
        f"  - Leave at least {min_gap_sec:.0f} seconds of face time between consecutive B-roll clips.\n"
        "  - Do not cover more than 40% of the total video with B-roll.\n\n"
        "Respond with ONLY a valid JSON array, nothing else:\n"
        "[\n"
        "  {\"clip_name\": \"exact_name.mp4\", \"timeline_sec\": 5.2, "
        "\"clip_start_sec\": 0.0, \"clip_end_sec\": 5.0},\n"
        "  ...\n"
        "]"
    )


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response, tolerating markdown fences, think blocks, trailing text."""
    original = text.strip()

    # Try stripping <think> blocks first; if JSON is outside, use that
    stripped = re.sub(r"<think>.*?</think>", "", original, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()

    # If JSON not found outside think block, search inside it as fallback
    # (M2.5 sometimes puts the answer inside <think> when temperature=0)
    think_match = re.search(r"<think>(.*?)</think>", original, flags=re.DOTALL)
    candidates = [stripped]
    if think_match:
        inner = re.sub(r"```(?:json)?", "", think_match.group(1)).strip()
        candidates.append(inner)

    for text in candidates:
        start = text.find("[")
        if start == -1:
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, start)
            if isinstance(obj, list):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    log.warning("[llm_director] full LLM reply (no JSON found): %r", original[:500])
    raise ValueError(f"no JSON array found in LLM response (first 200 chars): {original[:200]!r}")


def _parse_decisions(raw: list[dict]) -> list[PlacementDecision]:
    decisions = []
    for item in raw:
        if not isinstance(item, dict):
            log.debug("[llm_director] skipping non-dict item: %r", item)
            continue
        try:
            clip_name = str(item["clip_name"]).strip()
            timeline_sec = float(item["timeline_sec"])
            clip_start_sec = float(item.get("clip_start_sec", 0.0))
            clip_end_sec = float(item.get("clip_end_sec", 0.0))
            if not clip_name:
                continue
            if clip_end_sec <= clip_start_sec:
                clip_end_sec = clip_start_sec + 5.0
            decisions.append(PlacementDecision(
                clip_name=clip_name,
                timeline_sec=max(0.0, timeline_sec),
                clip_start_sec=max(0.0, clip_start_sec),
                clip_end_sec=clip_end_sec,
            ))
        except (KeyError, TypeError, ValueError) as e:
            log.debug("[llm_director] skipping malformed item %r: %s", item, e)
    return decisions


def direct(
    transcript_words: list[dict],
    segments: list[tuple[str, float]],
    keywords: list[str],
    candidates: list[dict],
    settings: Any,
    provider: str | None = None,
    max_placements: int = 10,
    intro_skip_sec: float = 4.0,
    min_gap_sec: float = 5.0,
    max_clip_sec: float = 6.0,
) -> tuple[list[PlacementDecision], str]:
    """Ask a cloud LLM to produce a full B-roll placement plan.

    Args:
        transcript_words: Raw transcript word dicts (for full text).
        segments:         List of (text, start_sec) transcript segments.
        keywords:         Top keywords extracted from transcript.
        candidates:       Clip dicts with 'name', 'keywords', 'duration_sec'.
        settings:         SettingsManager for reading API keys.
        max_placements:   Cap on number of placements to request.

    Returns:
        (decisions, error_str) — error_str is "" on success, human-readable
        message on failure so the UI can show a specific status.
    """
    if not segments or not candidates:
        return [], "No segments or candidates to send to LLM."

    from src.utils.llm_providers import api_key_for, resolve_provider

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        return [], "No cloud API key set. Add OpenAI, Gemini, Minimax, NVIDIA, or Anthropic key in Settings (⚙)."

    # Attach canonical name to each candidate for prompt + matching
    enriched: list[dict] = []
    for c in candidates:
        ec = dict(c)
        ec["_canon_name"] = ec.get("name", Path(ec.get("path", "clip")).name)
        enriched.append(ec)

    transcript_text = " ".join(
        w["word"] for w in transcript_words if w.get("type") == "word"
    )

    openai_model = str(settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini")
    gemini_model = str(settings.get("llm_gemini_model", "gemini-2.0-flash") or "gemini-2.0-flash")
    minimax_model = str(settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01")
    nvidia_model = str(settings.get("llm_nvidia_model", "") or "").strip()
    anthropic_model = str(settings.get("llm_anthropic_model", "claude-sonnet-4-6") or "claude-sonnet-4-6")
    if chosen == "NVIDIA" and not nvidia_model:
        return [], "Set an NVIDIA model id in Settings (⚙ → LLM Models)."
    max_tokens = int(settings.get(SETTINGS_KEYS.LLM_MAX_TOKENS, 1500) or 1500)
    temperature = float(settings.get(SETTINGS_KEYS.LLM_TEMPERATURE, 0.1) or 0.1)

    total_duration_sec = segments[-1][1] + 5.0 if segments else 0.0
    prompt = _build_prompt(
        transcript_text, segments, keywords, enriched, max_placements,
        total_duration_sec=total_duration_sec,
        intro_skip_sec=intro_skip_sec,
        min_gap_sec=min_gap_sec,
        max_clip_sec=max_clip_sec,
    )
    log.debug("[llm_director] prompt length: %d chars, %d candidates, %d segments",
              len(prompt), len(enriched), len(segments))

    key = api_key_for(settings, chosen)
    source = chosen
    try:
        if chosen == "OpenAI":
            reply = call_openai(prompt, key, openai_model, max_tokens, temperature)
        elif chosen == "Gemini":
            reply = call_gemini(prompt, key, gemini_model, max_tokens, temperature)
        elif chosen == "NVIDIA":
            reply = call_nvidia(prompt, key, nvidia_model, max_tokens, temperature)
        elif chosen == "Anthropic":
            reply = call_anthropic(prompt, key, anthropic_model, max_tokens, temperature)
        else:
            reply = call_minimax(prompt, key, minimax_model, max_tokens, temperature)

        log.debug("[llm_director] %s reply (first 600 chars): %s", source, reply[:600])
        if not reply or not reply.strip():
            return [], f"{source} returned an empty response. Check your API key and quota."
        raw = _extract_json(reply)
        decisions = _parse_decisions(raw)
        log.info("[llm_director] %s returned %d placement(s)", source, len(decisions))

        if not decisions:
            return [], (
                f"{source} responded but returned no valid placements. "
                "Check logs for raw reply."
            )
        return decisions, ""

    except Exception as e:
        log.warning("[llm_director] API call or parse failed: %s", e)
        return [], f"LLM call failed: {e}"


def _dispatch_call(
    chosen: str, prompt: str, settings: Any, max_tokens: int, temperature: float,
) -> str:
    """Route a prompt to the chosen provider. Caller resolves provider + model guard."""
    from src.utils.llm_providers import api_key_for
    key = api_key_for(settings, chosen)
    if chosen == "OpenAI":
        model = str(settings.get("llm_openai_model", "gpt-4o-mini") or "gpt-4o-mini")
        return call_openai(prompt, key, model, max_tokens, temperature)
    if chosen == "Gemini":
        model = str(settings.get("llm_gemini_model", "gemini-2.0-flash") or "gemini-2.0-flash")
        return call_gemini(prompt, key, model, max_tokens, temperature)
    if chosen == "NVIDIA":
        model = str(settings.get("llm_nvidia_model", "") or "").strip()
        return call_nvidia(prompt, key, model, max_tokens, temperature)
    if chosen == "Anthropic":
        model = str(settings.get("llm_anthropic_model", "claude-sonnet-4-6") or "claude-sonnet-4-6")
        return call_anthropic(prompt, key, model, max_tokens, temperature)
    model = str(settings.get("llm_minimax_model", "MiniMax-Text-01") or "MiniMax-Text-01")
    return call_minimax(prompt, key, model, max_tokens, temperature)


def _extract_str_array(text: str) -> list[str]:
    """Extract a JSON array of strings from an LLM reply, tolerating fences/think blocks."""
    raw = _extract_json(text)  # reuses the tolerant array parser
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def generate_search_terms(
    transcript_text: str,
    settings: Any,
    provider: str | None = None,
    max_terms: int = 10,
) -> tuple[list[str], str]:
    """Ask a cloud LLM for concrete, visual B-roll search queries from the transcript.

    Returns (terms, error_str). error_str is "" on success. Returns
    ([], NO_KEY_SENTINEL) when no provider key is configured so the caller can
    fall back to heuristic keyword extraction cleanly.
    """
    text = (transcript_text or "").strip()
    if not text:
        return [], "Empty transcript."

    from src.utils.llm_providers import resolve_provider

    chosen = resolve_provider(settings, provider)
    if chosen is None:
        return [], NO_KEY_SENTINEL
    if chosen == "NVIDIA" and not str(settings.get("llm_nvidia_model", "") or "").strip():
        return [], "Set an NVIDIA model id in Settings (⚙ → LLM Models)."

    max_tokens = int(settings.get(SETTINGS_KEYS.LLM_MAX_TOKENS, 1500) or 1500)
    temperature = float(settings.get(SETTINGS_KEYS.LLM_TEMPERATURE, 0.1) or 0.1)

    prompt = (
        "You are an expert video editor sourcing B-roll for a talking-head video.\n\n"
        f"TRANSCRIPT:\n\"{text[:3000]}\"\n\n"
        f"List up to {max_terms} concrete, visual B-roll search queries that a stock "
        "footage site (Pixabay / Pexels) could return clips for. Each query should be "
        "2-3 words, describe something filmable (objects, places, actions), and relate "
        "to what is being discussed. Avoid abstract terms.\n\n"
        "Respond with ONLY a valid JSON array of strings, nothing else:\n"
        "[\"city skyline\", \"typing keyboard\", \"ocean waves\"]"
    )

    try:
        reply = _dispatch_call(chosen, prompt, settings, max_tokens, temperature)
        if not reply or not reply.strip():
            return [], f"{chosen} returned an empty response."
        terms = _extract_str_array(reply)[:max_terms]
        log.info("[llm_director] %s search terms: %s", chosen, terms)
        if not terms:
            return [], f"{chosen} returned no usable search terms."
        return terms, ""
    except Exception as e:
        log.warning("[llm_director] search-term generation failed: %s", e)
        return [], f"LLM call failed: {e}"
