"""Motion graphics suggestion engine — V1 is rule-based, no AI.

Scans transcript for patterns and suggests appropriate graphic types.
Full AI integration (Minimax / Gemini / OpenAI) is planned for V2.
"""

from __future__ import annotations
import re
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# Patterns that trigger graphic suggestions
_RULES: list[tuple[str, str, str]] = [
    # (regex pattern, graphic type, description template)
    (r"\b\d[\d,\.]*\s*(?:%|percent|k|million|billion)\b",
     "Statistic Callout",
     "Highlight statistic: \"{match}\""),

    (r"\b(?:step|first|second|third|next|then|finally|lastly)\b",
     "Process Diagram",
     "Step-by-step breakdown at this point"),

    (r'"[^"]{10,80}"',
     "Quote Card",
     "Pull quote: {match}"),

    (r"\b(?:i am|i\'m|my name is|welcome to|this is)\b",
     "Lower Third",
     "Speaker / intro lower third"),

    (r"\b\d+\s*(?:tips|steps|ways|reasons|things|mistakes|secrets)\b",
     "Number Counter",
     "Number counter graphic: {match}"),

    (r"\b(?:before|after|vs\.?|versus|compared to|comparison)\b",
     "Before/After Split",
     "Before/after or comparison graphic"),

    (r"\b(?:website|link|url|instagram|youtube|twitter|follow|subscribe)\b",
     "CTA Overlay",
     "Call-to-action / social link overlay"),
]


def suggest_graphics(
    transcript: list[dict],
    style: str = "Minimal",
) -> list[dict]:
    """Scan transcript word entries for graphic opportunities.

    Args:
        transcript: List of {word, start_sec, end_sec, type} dicts.
        style:      Graphic style (informational only in V1).

    Returns:
        List of suggestion dicts: {type, description, timestamp_sec, style}.
    """
    if not transcript:
        return []

    # Rebuild sentences with timing
    sentences: list[tuple[str, float]] = []
    buffer_words: list[str] = []
    buffer_start: float = 0.0

    for entry in transcript:
        if entry.get("type") != "word":
            continue
        word = entry.get("word", "").strip()
        if not word:
            continue
        if not buffer_words:
            buffer_start = entry.get("start_sec", 0.0)
        buffer_words.append(word)
        # Commit on sentence-ending punctuation or every 15 words
        if re.search(r"[.!?]$", word) or len(buffer_words) >= 15:
            sentences.append((" ".join(buffer_words), buffer_start))
            buffer_words = []

    if buffer_words:
        sentences.append((" ".join(buffer_words), buffer_start))

    suggestions: list[dict] = []

    for sentence_text, timestamp_sec in sentences:
        text_lower = sentence_text.lower()
        for pattern, gfx_type, desc_template in _RULES:
            match = re.search(pattern, text_lower)
            if match:
                desc = desc_template.replace("{match}", match.group(0))
                suggestions.append({
                    "type": gfx_type,
                    "description": desc,
                    "timestamp_sec": timestamp_sec,
                    "style": style,
                    "source_text": sentence_text[:80],
                })
                break  # one suggestion per sentence

    log.info("Generated %d graphic suggestion(s)", len(suggestions))
    return suggestions
