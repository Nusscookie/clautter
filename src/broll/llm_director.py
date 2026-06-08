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

from src.utils.logger import get_logger

log = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
_TIMEOUT = 45

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
    return (
        "You are an expert video editor placing B-roll footage over a talking-head video.\n\n"
        f"TRANSCRIPT (full):\n\"{transcript_text[:3000]}\"\n\n"
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
        "  - clip_end_sec: out-point within the clip (clip_start_sec + 2 to 8 seconds, <= duration)\n\n"
        "Rules:\n"
        "  - Use each clip at most once.\n"
        "  - Match clip content to what is being said at that moment.\n"
        "  - Prefer clips whose keywords overlap with the transcript topics.\n"
        "  - Only use clips from the list above — no invented names.\n\n"
        "Respond with ONLY a valid JSON array, nothing else:\n"
        "[\n"
        "  {\"clip_name\": \"exact_name.mp4\", \"timeline_sec\": 5.2, "
        "\"clip_start_sec\": 0.0, \"clip_end_sec\": 5.0},\n"
        "  ...\n"
        "]"
    )


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response, tolerating markdown fences, think blocks, trailing text."""
    text = text.strip()
    # Strip <think>...</think> reasoning blocks (Minimax M2.5+ emits these)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip all markdown code fences (``` or ```json)
    text = re.sub(r"```(?:json)?", "", text)
    text = text.strip()
    start = text.find("[")
    if start == -1:
        raise ValueError(f"no JSON array found in LLM response (first 200 chars): {text[:200]!r}")
    # raw_decode stops at end of first valid JSON value, ignores trailing text
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(obj, list):
        raise ValueError(f"LLM returned JSON but not an array: {type(obj)}")
    return obj


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


def _call_openai(prompt: str, api_key: str) -> str:
    import requests
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
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
        "model": "MiniMax-M2.5",
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 1500,
        "temperature": 0,
        "thinking": {"type": "disabled"},
    }
    resp = requests.post(
        _MINIMAX_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def direct(
    transcript_words: list[dict],
    segments: list[tuple[str, float]],
    keywords: list[str],
    candidates: list[dict],
    settings: Any,
    max_placements: int = 10,
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

    openai_key = (settings.get("openai_api_key", "") or "").strip()
    gemini_key = (settings.get("gemini_api_key", "") or "").strip()
    minimax_key = (settings.get("minimax_api_key", "") or "").strip()

    if not openai_key and not gemini_key and not minimax_key:
        return [], "No cloud API key set. Add OpenAI, Gemini, or Minimax key in Settings (⚙)."

    # Attach canonical name to each candidate for prompt + matching
    enriched: list[dict] = []
    for c in candidates:
        ec = dict(c)
        ec["_canon_name"] = ec.get("name", Path(ec.get("path", "clip")).name)
        enriched.append(ec)

    transcript_text = " ".join(
        w["word"] for w in transcript_words if w.get("type") == "word"
    )

    prompt = _build_prompt(transcript_text, segments, keywords, enriched, max_placements)
    log.debug("[llm_director] prompt length: %d chars, %d candidates, %d segments",
              len(prompt), len(enriched), len(segments))

    try:
        if openai_key:
            reply = _call_openai(prompt, openai_key)
            source = "OpenAI"
        elif gemini_key:
            reply = _call_gemini(prompt, gemini_key)
            source = "Gemini"
        else:
            reply = _call_minimax(prompt, minimax_key)
            source = "Minimax"

        log.debug("[llm_director] %s reply (first 600 chars): %s", source, reply[:600])
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
