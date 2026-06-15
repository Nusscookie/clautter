"""Transcript mood analysis for music search.

Two modes:
  keywords — map top transcript keywords to a mood bucket (fast, offline).
  llm      — send transcript to a cloud LLM for richer mood/search_term output.
             Falls back to keyword mode on any failure.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from src.broll.keywords import extract_top_keywords
from src.constants import SETTINGS_KEYS
from src.utils.llm_providers import call_llm, extract_json_array, resolve_provider
from src.utils.logger import get_logger

log = get_logger(__name__)

MOOD_BUCKETS: dict[str, str] = {
    "energetic": "energetic upbeat music",
    "calm":      "calm relaxing background music",
    "emotional": "emotional inspiring music",
    "corporate": "corporate background music",
    "dramatic":  "dramatic cinematic music",
    "upbeat":    "upbeat positive music",
}

# keyword stem → mood bucket
KEYWORD_MOOD_MAP: dict[str, str] = {
    # energetic
    "action": "energetic", "fast": "energetic", "energy": "energetic",
    "speed": "energetic", "power": "energetic", "intense": "energetic",
    "strong": "energetic", "fierce": "energetic", "pump": "energetic",
    "workout": "energetic", "sport": "energetic", "exercise": "energetic",
    "race": "energetic", "game": "energetic",
    # calm
    "relax": "calm", "peace": "calm", "quiet": "calm", "meditation": "calm",
    "sleep": "calm", "gentle": "calm", "soft": "calm", "slow": "calm",
    "breath": "calm", "mindful": "calm", "yoga": "calm", "nature": "calm",
    "forest": "calm", "rain": "calm", "ocean": "calm",
    # emotional
    "love": "emotional", "hope": "emotional", "inspire": "emotional",
    "heart": "emotional", "feel": "emotional", "dream": "emotional",
    "story": "emotional", "life": "emotional", "family": "emotional",
    "friend": "emotional", "memory": "emotional", "journey": "emotional",
    # corporate
    "business": "corporate", "office": "corporate", "work": "corporate",
    "product": "corporate", "brand": "corporate", "market": "corporate",
    "team": "corporate", "company": "corporate", "professional": "corporate",
    "success": "corporate", "strategy": "corporate", "growth": "corporate",
    "invest": "corporate", "finance": "corporate",
    # dramatic
    "danger": "dramatic", "war": "dramatic", "fear": "dramatic",
    "dark": "dramatic", "conflict": "dramatic", "crisis": "dramatic",
    "tension": "dramatic", "mystery": "dramatic", "thriller": "dramatic",
    "epic": "dramatic", "battle": "dramatic", "challenge": "dramatic",
    # upbeat (default bucket)
    "happy": "upbeat", "joy": "upbeat", "fun": "upbeat",
    "laugh": "upbeat", "smile": "upbeat", "positive": "upbeat",
    "cool": "upbeat", "awesome": "upbeat", "great": "upbeat",
    "party": "upbeat", "celebrate": "upbeat",
}

_DEFAULT_MOOD = "upbeat"


@dataclass
class MoodSection:
    start_sec: float
    end_sec:   float
    mood:      str
    search_term: str


def analyze_mood_keywords(
    transcript: list[dict],
    n_sections: int = 1,
    method: str = "spacy",
) -> list[MoodSection]:
    """Split transcript into n equal sections, extract keywords, map to mood."""
    if not transcript:
        mood = _DEFAULT_MOOD
        return [MoodSection(0.0, 0.0, mood, MOOD_BUCKETS[mood])]

    word_entries = [e for e in transcript if e.get("type") == "word"]
    if not word_entries:
        mood = _DEFAULT_MOOD
        return [MoodSection(0.0, 0.0, mood, MOOD_BUCKETS[mood])]

    total_start = float(word_entries[0].get("start_sec", 0.0))
    total_end   = float(word_entries[-1].get("end_sec", 0.0))
    n = max(1, n_sections)
    chunk_size = max(1, len(word_entries) // n)

    sections: list[MoodSection] = []
    for i in range(n):
        chunk_start = i * chunk_size
        chunk_end   = chunk_start + chunk_size if i < n - 1 else len(word_entries)
        chunk       = word_entries[chunk_start:chunk_end]
        if not chunk:
            continue

        sec_start = float(chunk[0].get("start_sec", total_start))
        sec_end   = float(chunk[-1].get("end_sec", total_end))

        keywords = extract_top_keywords(chunk, top_n=5, method=method)
        mood = _DEFAULT_MOOD
        for kw in keywords:
            kw_lower = kw.lower()
            # try exact match, then prefix match
            if kw_lower in KEYWORD_MOOD_MAP:
                mood = KEYWORD_MOOD_MAP[kw_lower]
                break
            for stem, m in KEYWORD_MOOD_MAP.items():
                if kw_lower.startswith(stem) or stem.startswith(kw_lower):
                    mood = m
                    break
            else:
                continue
            break

        sections.append(MoodSection(sec_start, sec_end, mood, MOOD_BUCKETS[mood]))
        log.debug("[mood] section %d: keywords=%s → mood=%s", i, keywords, mood)

    if not sections:
        mood = _DEFAULT_MOOD
        sections = [MoodSection(total_start, total_end, mood, MOOD_BUCKETS[mood])]

    return sections


def analyze_mood_llm(
    transcript: list[dict],
    settings: Any,
    n_sections: int = 1,
    provider: str | None = None,
    method: str = "spacy",
) -> list[MoodSection]:
    """Ask a cloud LLM for mood sections. Falls back to keyword mode on failure."""
    chosen = resolve_provider(settings, provider)
    if chosen is None:
        log.warning("[mood_llm] no cloud API key — falling back to keyword mode")
        return analyze_mood_keywords(transcript, n_sections, method=method)

    word_entries = [e for e in transcript if e.get("type") == "word"]
    if not word_entries:
        return analyze_mood_keywords(transcript, n_sections, method=method)

    text = " ".join(str(e.get("word", "")) for e in word_entries)[:3000]
    total_end = float(word_entries[-1].get("end_sec", 0.0))
    mood_list = list(MOOD_BUCKETS.keys())

    prompt = (
        f"You are a music supervisor for video production.\n\n"
        f"TRANSCRIPT:\n\"{text}\"\n\n"
        f"TOTAL DURATION: {total_end:.1f}s\n\n"
        f"Divide this video into exactly {n_sections} section(s) and suggest background music.\n"
        f"Available moods: {', '.join(mood_list)}\n\n"
        f"Respond with ONLY a valid JSON array:\n"
        f"[{{\"section\": 0, \"start_sec\": 0.0, \"end_sec\": {total_end:.1f}, "
        f"\"mood\": \"upbeat\", \"search_term\": \"upbeat positive music\"}}]\n"
        f"Use exactly {n_sections} item(s). No prose, no markdown."
    )

    max_tokens = int(settings.get(SETTINGS_KEYS.LLM_MAX_TOKENS, 500) or 500)

    if chosen == "NVIDIA" and not str(settings.get("llm_nvidia_model", "") or "").strip():
        log.warning("[mood_llm] NVIDIA selected but no model id set — falling back to keywords")
        return analyze_mood_keywords(transcript, n_sections, method=method)

    try:
        reply = call_llm(chosen, prompt, settings, max_tokens=max_tokens, temperature=0.1)
        raw = extract_json_array(reply)
        sections = _parse_sections(raw, total_end)
        if sections:
            log.info("[mood_llm] got %d section(s) from LLM", len(sections))
            return sections
        log.warning("[mood_llm] LLM returned no valid sections — falling back")
    except Exception as e:
        log.warning("[mood_llm] LLM call failed (%s) — falling back to keywords", e)

    return analyze_mood_keywords(transcript, n_sections, method=method)


def _parse_sections(raw: list[dict], total_end: float) -> list[MoodSection]:
    sections = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            mood = str(item.get("mood", _DEFAULT_MOOD)).lower()
            if mood not in MOOD_BUCKETS:
                mood = _DEFAULT_MOOD
            search_term = str(item.get("search_term", "") or MOOD_BUCKETS[mood])
            sections.append(MoodSection(
                start_sec=float(item.get("start_sec", 0.0)),
                end_sec=float(item.get("end_sec", total_end)),
                mood=mood,
                search_term=search_term,
            ))
        except (KeyError, TypeError, ValueError) as e:
            log.debug("[mood_llm] skip malformed section %r: %s", item, e)
    return sections
