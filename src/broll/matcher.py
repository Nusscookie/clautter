"""B-Roll transcript keyword matcher.

V1 fallback: word-overlap scoring (no deps).
V2: sentence-transformer cosine similarity with joblib embedding cache.
Automatically selects V2 when sentence-transformers is installed, else V1.
"""

from __future__ import annotations
import re
from typing import Any

import numpy as np

from src.constants import PATHS
from src.utils.logger import get_logger

log = get_logger(__name__)

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

_CACHE_DIR = PATHS.BROLL_EMBED_CACHE
_SIM_THRESHOLD = 0.35
_SEGMENT_SEC = 5.0

# Module-level singletons — loaded once per process, reused on subsequent calls.
_model: Any = None
_encode_fn: Any = None  # None = uninitialized, False = sentence-transformers unavailable


def _tokenize(text: str) -> set[str]:
    """Lower-case words, removing stop words and short tokens."""
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOP_WORDS}


def _build_segments(
    words: list[dict[str, Any]], segment_sec: float = _SEGMENT_SEC
) -> list[tuple[str, float]]:
    """Group transcript words into ~segment_sec windows. Returns [(text, start_sec)]."""
    segments: list[tuple[str, float]] = []
    current: list[str] = []
    current_start = 0.0

    for entry in words:
        if entry.get("type") != "word":
            continue
        t = float(entry.get("start_sec", 0.0))
        if not current:
            current_start = t
        if t - current_start >= segment_sec and current:
            segments.append((" ".join(current), current_start))
            current = []
            current_start = t
        current.append(str(entry.get("word", "")))

    if current:
        segments.append((" ".join(current), current_start))

    return segments or [("", 0.0)]


def _raw_encode(texts: tuple[str, ...]) -> np.ndarray:
    """Encode text strings using the module-level SentenceTransformer singleton.

    Defined at module level so joblib can derive a stable cache key from its
    qualified name + source hash (a closure would get a new identity each call).
    """
    return _model.encode(list(texts), convert_to_numpy=True, show_progress_bar=False)


def _get_encode_fn() -> Any:
    """Return an encode function (tuple[str] -> ndarray). Returns False if unavailable."""
    global _model, _encode_fn

    if _encode_fn is not None:
        return _encode_fn

    try:
        from sentence_transformers import SentenceTransformer as _ST
    except ImportError:
        log.debug("[matcher] sentence-transformers not installed — word-overlap active")
        _encode_fn = False
        return False

    if _model is None:
        log.info("[matcher] loading all-MiniLM-L6-v2 (downloads ~80MB on first use)")
        _model = _ST("all-MiniLM-L6-v2")

    try:
        import joblib
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        mem = joblib.Memory(_CACHE_DIR, verbose=0)
        _encode_fn = mem.cache(_raw_encode)
        log.debug("[matcher] joblib embedding cache at %s", _CACHE_DIR)
    except ImportError:
        _encode_fn = _raw_encode
        log.debug("[matcher] joblib not installed — embeddings not cached across runs")

    return _encode_fn


def _semantic_suggest(
    clips: list[dict],
    words: list[dict[str, Any]],
    top_k: int,
) -> list[dict] | None:
    """Cosine-similarity matching. Returns None when sentence-transformers is unavailable."""
    encode = _get_encode_fn()
    if encode is False:
        return None

    segments = _build_segments(words)
    seg_texts = tuple(t for t, _ in segments)
    seg_starts = [s for _, s in segments]

    clip_texts: list[str] = []
    for clip in clips:
        kws = clip.get("keywords") or list(_tokenize(clip.get("name", "")))
        clip_texts.append(" ".join(kws) if kws else clip.get("name", ""))

    seg_emb: np.ndarray = encode(seg_texts)
    clip_emb: np.ndarray = encode(tuple(clip_texts))

    # Normalise and compute cosine similarity matrix: (num_clips × num_segments)
    seg_n = seg_emb / np.maximum(np.linalg.norm(seg_emb, axis=1, keepdims=True), 1e-9)
    clip_n = clip_emb / np.maximum(np.linalg.norm(clip_emb, axis=1, keepdims=True), 1e-9)
    sim = clip_n @ seg_n.T

    suggestions: list[dict] = []
    for i, clip in enumerate(clips):
        best_idx = int(np.argmax(sim[i]))
        score = float(sim[i, best_idx])
        if score < _SIM_THRESHOLD:
            continue
        suggestions.append({
            "clip_name": clip["name"],
            "path": clip["path"],
            "confidence": score,
            "matched_keywords": clip.get("keywords", [])[:5],
            "suggested_time": seg_starts[best_idx],
            "duration_sec": clip.get("duration_sec", 0.0),
        })

    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    log.info("[matcher] semantic: %d/%d clips above %.2f threshold",
             len(suggestions), len(clips), _SIM_THRESHOLD)
    return suggestions[:top_k]


def _overlap_suggest(
    clips: list[dict],
    transcript_text: str,
    top_k: int,
) -> list[dict]:
    """Word-overlap fallback — no deps."""
    transcript_tokens = _tokenize(transcript_text)
    if not transcript_tokens:
        return []

    words_in_order = [w for w in re.findall(r"[a-z]+", transcript_text.lower()) if len(w) > 2]
    suggestions: list[dict] = []

    for clip in clips:
        clip_keywords: set[str] = set(clip.get("keywords", []))
        if not clip_keywords:
            clip_keywords = _tokenize(clip.get("name", ""))

        matched = clip_keywords & transcript_tokens
        if not matched:
            continue

        confidence = len(matched) / max(len(clip_keywords), 1)

        suggested_time = 0.0
        for kw in matched:
            for i, w in enumerate(words_in_order):
                if w == kw:
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
    log.info("[matcher] word-overlap: %d suggestion(s)", len(suggestions[:top_k]))
    return suggestions[:top_k]


def suggest_broll(
    clips: list[dict],
    transcript_text: str,
    top_k: int = 10,
    words: list[dict[str, Any]] | None = None,
) -> list[dict]:
    """Match B-roll clips to transcript keywords.

    Args:
        clips:           Clip dicts from scanner.scan_folder().
        transcript_text: Full transcript as a plain string.
        top_k:           Maximum suggestions to return.
        words:           app.transcript word list (enables real timestamp placement
                         and semantic matching without words falls back to overlap).

    Returns:
        List of suggestion dicts sorted by confidence (descending):
        {clip_name, path, confidence, matched_keywords, suggested_time, duration_sec}.
    """
    if not clips or not transcript_text:
        return []

    if words:
        result = _semantic_suggest(clips, words, top_k)
        if result is not None:
            return result

    return _overlap_suggest(clips, transcript_text, top_k)
