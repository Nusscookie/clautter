"""Transcript keyword extraction for B-Roll search.

Pure-Python: no widgets, no network. Consumes the same `app.transcript` shape
used by the rest of the app (list of {word, start_sec, end_sec, type}) and
returns ranked keywords for stock-footage search queries.

Extraction method is user-configurable via B-Roll tab → Advanced Settings:
  spacy     — NER entities + noun chunk heads (en_core_web_sm)
  yake      — statistical co-occurrence ranking
  keybert   — semantic keyphrases via KeyBERT + all-MiniLM-L6-v2
  frequency — raw word frequency (no deps, always available)
"""

from __future__ import annotations
import re
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

STOPWORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "was", "are", "be", "been",
    "being", "have", "has", "had", "do", "did", "does", "doing", "will",
    "would", "could", "should", "can", "shall", "may", "might", "must",
    "this", "that", "these", "those", "i", "we", "you", "he", "she", "they",
    "me", "us", "them", "my", "our", "your", "his", "her", "their", "its",
    "mine", "yours", "ours", "theirs", "so", "just", "really", "very", "also",
    "then", "there", "here", "up", "out", "about", "into", "over", "under",
    "more", "most", "some", "any", "all", "no", "not", "only", "own", "same",
    "than", "too", "very", "just", "like", "as", "if", "when", "what", "which",
    "who", "whom", "whose", "how", "why", "where", "because", "while", "until",
    "before", "after", "above", "below", "between", "through", "during", "each",
    "few", "many", "such", "now", "new", "one", "two", "get", "got", "go",
    "going", "went", "gone", "make", "made", "take", "took", "taken", "come",
    "came", "see", "saw", "seen", "know", "knew", "known", "think", "thought",
    "say", "said", "tell", "told", "give", "gave", "given", "find", "found",
    "want", "wanted", "use", "used", "using", "work", "worked", "way", "thing",
    "things", "people", "person", "man", "woman", "guy", "kind", "sort", "lot",
}

MIN_LEN: int = 4
TOP_N: int = 10

_TOKEN_RE = re.compile(r"[a-z]+")


def _normalize(token: str) -> str:
    return token.lower().strip()


def _is_valid(kw: str) -> bool:
    """True if kw passes length, stopword, and alpha checks."""
    kw = kw.lower()
    return (
        len(kw) >= MIN_LEN
        and kw not in STOPWORDS
        and bool(_TOKEN_RE.fullmatch(kw))
    )


# ── Extraction backends ───────────────────────────────────────────────────────

def _spacy_keywords(text: str, top_n: int) -> list[str]:
    """NER entities + noun chunk heads via spaCy en_core_web_sm. Returns [] if unavailable."""
    try:
        import spacy  # type: ignore[import]
    except ImportError:
        log.warning("[keywords] spacy not installed — pip install spacy && python -m spacy download en_core_web_sm")
        return []
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        log.warning("[keywords] en_core_web_sm missing — run: python -m spacy download en_core_web_sm")
        return []
    doc = nlp(text)
    candidates: list[str] = []
    for ent in doc.ents:
        kw = ent.root.lemma_.lower()
        if _is_valid(kw):
            candidates.append(kw)
    for chunk in doc.noun_chunks:
        kw = chunk.root.lemma_.lower()
        if _is_valid(kw) and kw not in candidates:
            candidates.append(kw)
    seen: set[str] = set()
    results: list[str] = []
    for kw in candidates:
        if kw not in seen:
            seen.add(kw)
            results.append(kw)
    return results[:top_n]


def _yake_keywords(text: str, top_n: int) -> list[str]:
    """Statistical co-occurrence ranking via YAKE. Returns [] if unavailable."""
    try:
        import yake  # type: ignore[import]
    except ImportError:
        log.warning("[keywords] yake not installed — pip install yake")
        return []
    extractor = yake.KeywordExtractor(lan="en", n=1, dedupLim=0.7, top=top_n * 3)
    raw = extractor.extract_keywords(text)  # [(kw, score), ...] lower = better
    return [kw for kw, _ in raw if _is_valid(kw)][:top_n]


def _keybert_keywords(text: str, top_n: int) -> list[str]:
    """Semantic keyphrase extraction via KeyBERT (all-MiniLM-L6-v2). Returns [] if unavailable."""
    try:
        from keybert import KeyBERT  # type: ignore[import]
    except ImportError:
        log.warning("[keywords] keybert not installed — pip install keybert")
        return []
    kw_model = KeyBERT()
    raw = kw_model.extract_keywords(
        text, keyphrase_ngram_range=(1, 2), stop_words="english", top_n=top_n * 2
    )
    return [kw for kw, _ in raw if _is_valid(kw.split()[0])][:top_n]


def _frequency_keywords(words: list[dict[str, Any]], top_n: int) -> list[str]:
    """Raw word frequency — no deps, always available."""
    counts: dict[str, int] = {}
    for entry in words:
        if entry.get("type") != "word":
            continue
        token = _normalize(str(entry.get("word", "")))
        m = _TOKEN_RE.fullmatch(token)
        if not m:
            continue
        token = m.group(0)
        if not _is_valid(token):
            continue
        counts[token] = counts.get(token, 0) + 1
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


# ── Public API ────────────────────────────────────────────────────────────────

def extract_top_keywords(
    words: list[dict[str, Any]],
    top_n: int = TOP_N,
    method: str = "spacy",
) -> list[str]:
    """Return up to ``top_n`` keywords using the chosen extraction method.

    ``method`` is ``"spacy"``, ``"yake"``, ``"keybert"``, or ``"frequency"``.
    If the chosen library is missing, logs a warning and falls back to frequency.
    """
    text = " ".join(
        str(e.get("word", "")) for e in words if e.get("type") == "word"
    )

    if method == "spacy":
        result = _spacy_keywords(text, top_n)
        if result:
            log.info("[keywords] spaCy → %s", result)
            return result
        log.info("[keywords] spaCy returned nothing — falling back to frequency")

    elif method == "yake":
        result = _yake_keywords(text, top_n)
        if result:
            log.info("[keywords] YAKE → %s", result)
            return result
        log.info("[keywords] YAKE returned nothing — falling back to frequency")

    elif method == "keybert":
        result = _keybert_keywords(text, top_n)
        if result:
            log.info("[keywords] KeyBERT → %s", result)
            return result
        log.info("[keywords] KeyBERT returned nothing — falling back to frequency")

    result = _frequency_keywords(words, top_n)
    log.info("[keywords] frequency → %s", result)
    return result


def keyword_occurrences(words: list[dict[str, Any]], keyword: str) -> list[float]:
    """Return ``start_sec`` for every whole-word case-insensitive match.

    Used by future Auto Place logic to decide where on V1 a clip should be
    inserted. Not consumed by the prototype search flow.
    """
    needle = keyword.lower()
    out: list[float] = []
    for entry in words:
        if entry.get("type") != "word":
            continue
        token = _normalize(str(entry.get("word", "")))
        if token == needle:
            try:
                out.append(float(entry.get("start_sec", 0.0)))
            except (TypeError, ValueError):
                continue
    return out
