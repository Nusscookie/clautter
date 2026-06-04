"""B-Roll transcript keyword matcher.

V1: simple word-overlap scoring (no embeddings, no AI).
Future versions will use sentence embeddings for semantic matching.
"""

from __future__ import annotations
import re
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# Common stop words to exclude from keyword matching
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "was", "are", "be", "been",
    "have", "has", "had", "do", "did", "will", "would", "could", "should",
    "this", "that", "these", "those", "i", "we", "you", "he", "she", "they",
    "my", "our", "your", "his", "her", "their", "its", "so", "just", "really",
    "very", "also", "then", "there", "here", "up", "out", "about", "into",
    "more", "some", "all", "not", "no", "like", "as", "if", "when", "what",
    "which", "who", "how", "why", "where",
}


def _tokenize(text: str) -> set[str]:
    """Lower-case words, removing stop words and short tokens."""
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOP_WORDS}


def suggest_broll(
    clips: list[dict],
    transcript_text: str,
    top_k: int = 10,
) -> list[dict]:
    """Match B-roll clips to transcript keywords.

    Args:
        clips:           Clip dicts from scanner.scan_folder().
        transcript_text: Full transcript as a plain string.
        top_k:           Maximum suggestions to return.

    Returns:
        List of suggestion dicts sorted by confidence (descending):
        {clip_name, path, confidence, matched_keywords, suggested_time}.
    """
    if not clips or not transcript_text:
        return []

    transcript_tokens = _tokenize(transcript_text)
    if not transcript_tokens:
        return []

    # Build a rough time map: split transcript into ~5s chunks and find keyword positions.
    # This is a simplified approximation — real implementation would use word timings.
    words_in_order = [w for w in re.findall(r"[a-z]+", transcript_text.lower()) if len(w) > 2]
    total_words = len(words_in_order)

    suggestions: list[dict] = []

    for clip in clips:
        clip_keywords: set[str] = set(clip.get("keywords", []))
        if not clip_keywords:
            clip_keywords = _tokenize(clip.get("name", ""))

        matched = clip_keywords & transcript_tokens
        if not matched:
            continue

        confidence = len(matched) / max(len(clip_keywords), 1)

        # Find approximate timeline position of first keyword match
        suggested_time = 0.0
        for kw in matched:
            for i, w in enumerate(words_in_order):
                if w == kw:
                    # Rough time estimate: assume ~2 words per second
                    suggested_time = i / 2.0
                    break
            break

        suggestions.append({
            "clip_name": clip["name"],
            "path": clip["path"],
            "confidence": confidence,
            "matched_keywords": sorted(matched),
            "suggested_time": suggested_time,
            "duration_sec": clip.get("duration_sec", 0.0),
        })

    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    log.info("Generated %d B-roll suggestion(s)", len(suggestions[:top_k]))
    return suggestions[:top_k]
