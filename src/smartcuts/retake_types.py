"""Types, constants, and text-normalization helpers for retake detection.

Extracted from retake_detector.py so that cutter.py can import SegmentRecord
without pulling in the full Whisper dependency at import time.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

_WIN_WORDS            = 4        # sliding window size (content words)
_SIMILARITY_THRESHOLD = 0.70     # SequenceMatcher ratio to call two windows retakes
_PROXIMITY_WINDOW_MS  = 120_000  # only compare windows within 2 minutes of each other
_FULL_RETAKE_COVERAGE = 0.90     # retake region covering >= 90% of a segment -> full retake

# "so" is intentionally absent: it is a meaningful word in German (the primary
# language here) and stripping it hurt retake matching more than it helped.
_FILLERS = frozenset({
    "um", "uh", "like", "okay", "ok", "well", "right",
    "actually", "basically", "you", "know", "now", "alright", "hmm",
})


@dataclass
class SegmentRecord:
    """One non-silent segment, enriched with source metadata and transcript text."""

    clip_idx:      int
    media_item:    Any
    file_path:     str
    start_ms:      float   # absolute position in source file
    end_ms:        float
    start_frame:   int
    end_frame:     int
    text:           str = field(default="", compare=False)
    is_retake:      bool = field(default=False, compare=False)
    retake_regions: list[tuple[float, float]] = field(default_factory=list, compare=False)
    # retake_regions: source-time (start_ms, end_ms) sub-ranges within this segment that
    # are superseded retakes. Empty when is_retake is False. A segment may hold several
    # (few big silence segments can contain multiple retakes). cutter_retakes.py splits
    # the clip at every range. A single range covering the whole segment = full retake.


@dataclass
class _WordEntry:
    """One content word (filler-stripped) with its timestamp and owning segment index."""
    word:    str    # normalized: lowercase, no punctuation, not a filler
    time_ms: float  # word start, ms (absolute in source file)
    seg_idx: int


def _words_in_range(words: list[dict], start_ms: float, end_ms: float) -> str:
    """Return space-joined text of words whose timestamps fall inside [start_ms, end_ms]."""
    return " ".join(
        w["word"]
        for w in words
        if w["start_sec"] * 1000.0 >= start_ms and w["end_sec"] * 1000.0 <= end_ms
    )


def _normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove fillers. Returns word list for comparison."""
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return [w for w in words if w not in _FILLERS]


def _normalize_word(raw: str) -> str | None:
    """Normalize a single word. Returns None if it's a filler or empty after stripping."""
    cleaned = re.sub(r"[^\w]", "", raw.lower())
    if not cleaned or cleaned in _FILLERS:
        return None
    return cleaned


def _normalize_word_with_extras(raw: str, extra_fillers: frozenset[str]) -> str | None:
    """Normalize a single word, also stripping spaCy-detected interjections."""
    cleaned = re.sub(r"[^\w]", "", raw.lower())
    if not cleaned or cleaned in _FILLERS or cleaned in extra_fillers:
        return None
    return cleaned


_NLP: Any = None  # cached spaCy model — loaded once per process
_NLP_TRIED: bool = False  # avoid repeated failed imports


def _load_spacy_nlp() -> Any:
    """Load en_core_web_sm once. Returns None if spaCy or the model isn't available."""
    global _NLP, _NLP_TRIED
    if _NLP_TRIED:
        return _NLP
    _NLP_TRIED = True
    try:
        import spacy  # type: ignore
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None
    return _NLP


def _build_spacy_intj_set(segment_texts: list[str]) -> frozenset[str]:
    """Run spaCy over segment text to find INTJ-tagged tokens beyond the hardcoded list.

    Args:
        segment_texts: List of plain-text segment transcripts (may be empty strings).

    Returns:
        Frozenset of lowercased word forms tagged as INTJ by spaCy.
    """
    from src.utils.logger import get_logger as _get_logger
    _log = _get_logger(__name__)

    nlp = _load_spacy_nlp()
    if nlp is None:
        _log.warning("spaCy not available — retake detection uses hardcoded fillers only")
        return frozenset()

    combined = " ".join(t for t in segment_texts if t)
    if not combined.strip():
        return frozenset()

    doc = nlp(combined)
    intj_words: set[str] = {
        re.sub(r"[^\w]", "", token.lemma_.lower())
        for token in doc
        if token.pos_ == "INTJ"
    }
    intj_words.discard("")
    _log.debug("spaCy INTJ extras detected: %s", sorted(intj_words))
    return frozenset(intj_words)
