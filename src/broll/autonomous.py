"""Autonomous B-roll agent — end-to-end pipeline without user interaction.

Orchestrates: keyword extraction → candidate collection (local + online)
→ semantic ranking → optional scenedetect boundary validation →
optional cloud LLM re-rank → Resolve V2 placement.

Called from _broll_workers.autonomous_thread() on a daemon thread.
All Resolve / UI side effects go through app.resolve / placer.place_clip().
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.broll.placer import PlacerResult, place_clip
from src.broll.reranker import rerank
from src.utils.logger import get_logger

log = get_logger(__name__)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SegmentResult:
    """One placed (or failed) clip per transcript segment."""
    segment_text: str
    segment_start_sec: float
    chosen_clip: dict | None        # suggestion dict from matcher, or None
    placer_result: PlacerResult | None = None
    reranked: bool = False


@dataclass
class AutonomousResult:
    segments: list[SegmentResult] = field(default_factory=list)
    placed_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)


# ── Scene boundary validation (optional scenedetect) ─────────────────────────

def _clean_in_point(clip_path: str, desired_sec: float) -> float:
    """Return a scene-boundary-aligned in-point near *desired_sec*.

    Uses scenedetect if available; otherwise returns *desired_sec* unchanged.
    Only searches for boundaries within the clip itself (local files only).
    For online clips that were just downloaded we use 0.0 as the in-point.
    """
    try:
        from scenedetect import open_video, SceneManager  # type: ignore[import]
        from scenedetect.detectors import ContentDetector  # type: ignore[import]
    except ImportError:
        return desired_sec

    try:
        video = open_video(clip_path)
        sm = SceneManager()
        sm.add_detector(ContentDetector())
        sm.detect_scenes(video, show_progress=False)
        scenes = sm.get_scene_list()
        if not scenes:
            return desired_sec

        # Pick the scene boundary closest to desired_sec
        boundaries = [s[0].get_seconds() for s in scenes]
        closest = min(boundaries, key=lambda b: abs(b - desired_sec))
        log.debug("[autonomous] scene boundary %.2fs → %.2fs for %s",
                  desired_sec, closest, Path(clip_path).name)
        return closest
    except Exception as e:
        log.warning("[autonomous] scenedetect failed for %s: %s", clip_path, e)
        return desired_sec


# ── Candidate collection ──────────────────────────────────────────────────────

def _collect_local(local_folder: str) -> list[dict]:
    from src.broll.scanner import scan_folder
    clips = scan_folder(local_folder)
    log.info("[autonomous] local scan: %d clip(s) in %s", len(clips), local_folder)
    return clips


def _collect_online(
    keywords: list[str],
    providers: list[tuple[str, str]],
    download_folder: str,
    app: Any,
    on_progress: Callable[[str, float], None],
    max_clips: int = 10,
) -> list[dict]:
    """Search providers for each keyword, download top hit, return clip dicts."""
    from src.broll.cache import BrollCache
    from src.broll.downloader import BrollDownloader
    from src.broll.providers.base import AuthError, EmptyResultsError, NetworkError, RateLimitError
    from src.broll.providers.pexels import PexelsClient
    from src.broll.providers.pixabay import PixabayClient

    cache = BrollCache()
    slots: list[tuple[str, Any]] = []
    for name, key in providers:
        if name == "Pixabay":
            slots.append(("Pixabay", PixabayClient(key, cache=cache)))
        elif name == "Pexels":
            slots.append(("Pexels", PexelsClient(key, cache=cache)))

    downloader = BrollDownloader(Path(download_folder), app)
    collected: list[dict] = []
    total = len(keywords) * len(slots)
    done = 0

    for kw in keywords:
        for slot_name, client in slots:
            done += 1
            on_progress(f"Searching {slot_name} for '{kw}'…", done / max(total, 1) * 0.4)
            try:
                hits = client.search(kw, per_page=3)
            except (AuthError, RateLimitError, NetworkError, EmptyResultsError) as e:
                log.warning("[autonomous] %s/%s: %s", slot_name, kw, e)
                continue
            except Exception as e:
                log.error("[autonomous] unexpected search error %s/%s: %s", slot_name, kw, e)
                continue

            for hit in hits[:1]:   # download only top result per keyword per provider
                if len(collected) >= max_clips:
                    log.info("[autonomous] online cap reached (%d clips)", max_clips)
                    break
                try:
                    on_progress(f"Downloading {hit.title[:40]}…", done / max(total, 1) * 0.4)
                    result = downloader.download_and_import(hit)
                    path = result["path"]
                    # Build a clip dict compatible with matcher input
                    collected.append({
                        "name": hit.title,
                        "path": path,
                        "keywords": [kw],
                        "duration_sec": float(hit.duration_sec),
                        "source": hit.source,
                    })
                except Exception as e:
                    log.warning("[autonomous] download failed for %s: %s", hit.title, e)
            if len(collected) >= max_clips:
                break

    log.info("[autonomous] online: %d clip(s) downloaded", len(collected))
    return collected


# ── Optional visual re-rank (OpenCLIP/Torch) ─────────────────────────────────

def _visual_rerank_if_available(
    segment_text: str,
    candidates: list[dict],
) -> list[dict]:
    """Re-rank candidates visually using OpenCLIP if torch+open_clip are present."""
    try:
        import torch  # type: ignore[import]
        import open_clip  # type: ignore[import]
    except ImportError:
        return candidates

    try:
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        model.eval()

        from PIL import Image
        import cv2  # type: ignore[import]

        text_tokens = tokenizer([segment_text])
        with torch.no_grad():
            text_feat = model.encode_text(text_tokens)
            text_feat /= text_feat.norm(dim=-1, keepdim=True)

        scores: list[float] = []
        for c in candidates:
            path = c.get("path", "")
            try:
                cap = cv2.VideoCapture(str(path))
                ok, frame = cap.read()
                cap.release()
                if not ok:
                    scores.append(0.0)
                    continue
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img_tensor = preprocess(img).unsqueeze(0)
                with torch.no_grad():
                    img_feat = model.encode_image(img_tensor)
                    img_feat /= img_feat.norm(dim=-1, keepdim=True)
                score = float((img_feat @ text_feat.T).squeeze())
                scores.append(score)
            except Exception:
                scores.append(0.0)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        log.debug("[autonomous] OpenCLIP visual re-rank applied")
        return [c for _, c in ranked]
    except Exception as e:
        log.warning("[autonomous] OpenCLIP re-rank failed: %s", e)
        return candidates


# ── Pacing gate ───────────────────────────────────────────────────────────────

def _should_place(
    seg_start: float,
    last_placed_end_sec: float,
    natural_placement: bool,
    no_start_broll: bool,
    intro_skip_sec: float,
    min_gap_sec: float,
) -> tuple[bool, str]:
    """Return (True, '') if segment is eligible for B-roll, else (False, reason)."""
    if not natural_placement:
        return True, ""
    if no_start_broll and seg_start < intro_skip_sec:
        return False, f"intro skip ({seg_start:.1f}s < {intro_skip_sec:.1f}s)"
    if last_placed_end_sec > 0.0 and (seg_start - last_placed_end_sec) < min_gap_sec:
        return False, f"gap too small ({seg_start - last_placed_end_sec:.1f}s < {min_gap_sec:.1f}s)"
    return True, ""


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_autonomous(
    app: Any,
    local_folder: str | None,
    providers: list[tuple[str, str]],
    download_folder: str,
    cloud_rerank: bool,
    clips_per_segment: int,
    on_progress: Callable[[str, float], None],
    max_clips: int = 10,
    llm_director_mode: bool = False,
    llm_provider: str | None = None,
    fill_frame: bool = False,
    natural_placement: bool = True,
    no_start_broll: bool = True,
    intro_skip_sec: float = 8.0,
    min_gap_sec: float = 5.0,
    max_broll_duration: float = 5.0,
) -> AutonomousResult:
    """Run the full autonomous B-roll pipeline.

    Args:
        app:               AIEditorApp with .transcript, .project, .timeline, .settings.
        local_folder:      Path to local B-roll folder, or None to skip.
        providers:         [(name, api_key), ...] for online search, or [] to skip.
        download_folder:   Where to save downloaded clips.
        cloud_rerank:      Whether to call cloud LLM for final pick per segment.
        clips_per_segment: How many clips to place per segment (usually 1).
        on_progress:       Callback(msg: str, fraction: float 0-1) for UI updates.
        fill_frame:        Zoom-crop placed clips to eliminate black bars.
        natural_placement: Apply pacing rules (intro skip, gap enforcement, duration cap).
        no_start_broll:    Skip B-roll in the intro window when natural_placement=True.
        intro_skip_sec:    Seconds at start of video reserved for speaker face.
        min_gap_sec:       Minimum face-time gap between consecutive B-roll clips.
        max_broll_duration: Cap on placed clip duration in seconds.

    Returns:
        AutonomousResult with per-segment outcomes.
    """
    result = AutonomousResult()

    # ── Guard: transcript required ────────────────────────────────────
    if not app.transcript:
        result.warnings.append("No transcript — generate one in the Subtitles tab first.")
        on_progress("No transcript.", 1.0)
        return result

    # ── 1. Extract keywords / LLM-generated search terms ──────────────
    from src.broll.keywords import extract_top_keywords
    method = str(app.settings.get("broll_keyword_method", "spacy"))
    keywords: list[str] = []

    # Full LLM-directed workflow: when an online search will run, let the LLM
    # produce the Pixabay/Pexels search terms from the transcript. Fall back to
    # heuristic extraction on any failure / no key.
    if llm_director_mode and providers:
        on_progress("Asking LLM for B-roll search terms…", 0.05)
        from src.broll.llm_director import generate_search_terms
        transcript_text = " ".join(
            w["word"] for w in app.transcript if w.get("type") == "word"
        )
        terms, err = generate_search_terms(
            transcript_text, app.settings, provider=llm_provider, max_terms=10,
        )
        if terms:
            keywords = terms
        else:
            log.warning("[autonomous] LLM search terms unavailable (%s) — "
                        "falling back to heuristic keywords", err)

    if not keywords:
        on_progress("Extracting keywords from transcript…", 0.05)
        keywords = extract_top_keywords(app.transcript, top_n=10, method=method)
    if not keywords:
        result.warnings.append("No keywords extracted from transcript.")
        on_progress("No keywords found.", 1.0)
        return result
    log.info("[autonomous] keywords: %s", keywords)

    # ── 2. Build transcript segments ──────────────────────────────────
    on_progress("Segmenting transcript…", 0.08)
    from src.broll.matcher import _build_segments, _semantic_suggest, _overlap_suggest
    words = app.transcript
    segments = _build_segments(words)
    log.info("[autonomous] %d transcript segment(s)", len(segments))

    # ── 3. Collect candidates ─────────────────────────────────────────
    all_clips: list[dict] = []

    if local_folder:
        on_progress("Scanning local B-roll folder…", 0.10)
        all_clips.extend(_collect_local(local_folder))

    if providers:
        online_clips = _collect_online(
            keywords, providers, download_folder, app,
            on_progress=on_progress,
            max_clips=max_clips,
        )
        all_clips.extend(online_clips)

    if not all_clips:
        result.warnings.append("No candidate clips found (empty folder and/or no search results).")
        on_progress("No clips found.", 1.0)
        return result

    log.info("[autonomous] total candidates: %d", len(all_clips))

    # ── 4. LLM Director mode — LLM decides everything ────────────────
    if llm_director_mode:
        on_progress("Asking LLM director to plan placements…", 0.55)
        from src.broll.llm_director import direct as llm_direct
        decisions, llm_err = llm_direct(
            transcript_words=words,
            segments=segments,
            keywords=keywords,
            candidates=all_clips,
            settings=app.settings,
            provider=llm_provider,
            max_placements=max_clips,
            intro_skip_sec=intro_skip_sec,
            min_gap_sec=min_gap_sec,
            max_clip_sec=max_broll_duration,
        )
        if not decisions:
            result.warnings.append(llm_err or "LLM director returned no placements.")
            on_progress(llm_err or "LLM director returned nothing.", 1.0)
            return result

        # Build a lookup: canonical name → clip dict (case-insensitive, with/without ext)
        def _name_variants(c: dict) -> list[str]:
            n = c.get("name", Path(c.get("path", "")).name)
            stem = Path(n).stem
            return [n.lower(), stem.lower()]

        name_index: dict[str, dict] = {}
        for c in all_clips:
            for variant in _name_variants(c):
                name_index.setdefault(variant, c)

        for d_idx, decision in enumerate(decisions):
            progress = 0.60 + (d_idx / max(len(decisions), 1)) * 0.30
            on_progress(
                f"Placing {decision.clip_name[:40]} at {decision.timeline_sec:.1f}s…",
                progress,
            )
            # Fuzzy lookup: exact name → stem → first partial match
            key = decision.clip_name.lower()
            match = (
                name_index.get(key)
                or name_index.get(Path(key).stem)
                or next(
                    (c for c in all_clips
                     if key in c.get("name", "").lower()
                     or key in Path(c.get("path", "")).stem.lower()),
                    None,
                )
            )
            if match is None:
                result.warnings.append(
                    f"LLM director: clip '{decision.clip_name}' not found in candidates "
                    f"(available: {[c.get('name','?') for c in all_clips[:5]]}…)"
                )
                result.skipped_count += 1
                result.segments.append(SegmentResult(decision.clip_name, decision.timeline_sec, None))
                continue

            if natural_placement and no_start_broll and decision.timeline_sec < intro_skip_sec:
                log.info(
                    "[autonomous] LLM placement at %.1fs rejected (intro skip %.1fs)",
                    decision.timeline_sec, intro_skip_sec,
                )
                result.skipped_count += 1
                result.segments.append(SegmentResult(decision.clip_name, decision.timeline_sec, None))
                continue

            raw_dur = decision.clip_end_sec - decision.clip_start_sec
            duration = (
                min(raw_dur, max_broll_duration)
                if max_broll_duration > 0 and raw_dur > 0
                else raw_dur
            )
            duration = max(duration, 0.0) or match.get("duration_sec", 0.0)
            placer_res = place_clip(
                app,
                match["path"],
                segment_start_sec=decision.timeline_sec,
                clip_duration_sec=duration,
                clip_start_sec=decision.clip_start_sec,
                fill_frame=fill_frame,
            )
            seg_result = SegmentResult(
                decision.clip_name, decision.timeline_sec, match,
                placer_result=placer_res,
                reranked=True,
            )
            result.segments.append(seg_result)
            if placer_res.placed:
                result.placed_count += 1
            else:
                result.skipped_count += 1
                result.warnings.append(f"Placement {d_idx + 1}: {placer_res.reason}")

        on_progress("Done.", 1.0)
        log.info("[autonomous] LLM director finished: %d placed, %d skipped",
                 result.placed_count, result.skipped_count)
        return result

    # ── 4. Semantic rank across all candidates ────────────────────────
    on_progress("Ranking clips against transcript…", 0.55)
    transcript_text = " ".join(w["word"] for w in words if w.get("type") == "word")
    semantic = _semantic_suggest(all_clips, words, top_k=len(all_clips))
    if semantic is None:
        # sentence-transformers unavailable — word-overlap fallback
        ranked_global = _overlap_suggest(all_clips, transcript_text, top_k=len(all_clips))
    else:
        ranked_global = semantic

    # ── 5. Per-segment matching + optional re-ranking ─────────────────
    on_progress("Matching clips to timeline segments…", 0.65)

    # Deduplicate placed clips across segments (don't use same clip twice)
    used_paths: set[str] = set()
    last_placed_end_sec: float = 0.0

    for seg_idx, (seg_text, seg_start) in enumerate(segments):
        progress = 0.65 + (seg_idx / max(len(segments), 1)) * 0.25
        on_progress(f"Segment {seg_idx + 1}/{len(segments)}: {seg_text[:40]}…", progress)

        # Filter already-used clips
        available = [c for c in ranked_global if c["path"] not in used_paths]
        if not available:
            result.segments.append(SegmentResult(seg_text, seg_start, None))
            result.skipped_count += 1
            continue

        # Optionally re-rank top candidates with OpenCLIP
        top_candidates = available[:10]
        top_candidates = _visual_rerank_if_available(seg_text, top_candidates)

        # Cloud LLM re-rank
        reranked_flag = False
        if cloud_rerank:
            before = [c.get("clip_name", c.get("name", "")) for c in top_candidates[:3]]
            top_candidates = rerank(seg_text, top_candidates, app.settings)
            after = [c.get("clip_name", c.get("name", "")) for c in top_candidates[:3]]
            reranked_flag = before != after

        chosen = top_candidates[0] if top_candidates else None

        if chosen is None:
            result.segments.append(SegmentResult(seg_text, seg_start, None))
            result.skipped_count += 1
            continue

        # ── Pacing gate ───────────────────────────────────────────────
        ok, skip_reason = _should_place(
            seg_start, last_placed_end_sec,
            natural_placement, no_start_broll, intro_skip_sec, min_gap_sec,
        )
        if not ok:
            log.debug("[autonomous] pacing skip seg %d (%.1fs): %s",
                      seg_idx + 1, seg_start, skip_reason)
            result.segments.append(SegmentResult(seg_text, seg_start, None))
            result.skipped_count += 1
            continue

        used_paths.add(chosen["path"])

        # ── 6. Scene boundary alignment ───────────────────────────────
        in_point = _clean_in_point(chosen["path"], 0.0)

        # ── 7. Place on B-Roll track ──────────────────────────────────
        raw_duration = chosen.get("duration_sec", 0.0)
        placed_duration = (
            min(raw_duration - in_point, max_broll_duration)
            if raw_duration > 0 and max_broll_duration > 0
            else raw_duration
        )
        placed_duration = max(placed_duration, 0.0)

        placer_res = place_clip(
            app,
            chosen["path"],
            segment_start_sec=seg_start,
            clip_duration_sec=placed_duration,
            clip_start_sec=in_point,
            fill_frame=fill_frame,
        )

        seg_result = SegmentResult(
            seg_text, seg_start, chosen,
            placer_result=placer_res,
            reranked=reranked_flag,
        )
        result.segments.append(seg_result)

        if placer_res.placed:
            result.placed_count += 1
            last_placed_end_sec = seg_start + (placed_duration if placed_duration > 0 else 5.0)
        else:
            result.skipped_count += 1
            result.warnings.append(
                f"Segment {seg_idx + 1}: {placer_res.reason}"
            )

    on_progress("Done.", 1.0)
    log.info("[autonomous] finished: %d placed, %d skipped",
             result.placed_count, result.skipped_count)
    return result
