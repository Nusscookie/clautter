"""Candidate collection + ranking helpers for the autonomous B-roll agent.

Extracted from autonomous.py so the orchestrator stays focused on the
decision/placement state machine. These functions gather clip candidates
(local scan, online provider search+download), align in-points to scene
boundaries, and optionally re-rank candidates visually with OpenCLIP. All
heavy/optional deps are imported lazily inside the functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)


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
