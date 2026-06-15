"""Fill-frame (cover-zoom) helpers for the B-roll placer.

Extracted from placer.py so the timeline-placement logic stays separate from
the aspect-ratio cover math. Reuses the Fusion zoom primitives from
src.zooms.applier_fusion (zoom readback + static Fusion fallback) so the
free-edition no-op workaround lives in exactly one place.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger
from src.zooms.applier_fusion import _zoom_took, apply_fusion_static_zoom

log = get_logger(__name__)

# Cap fill-frame zoom. CSS-cover math (zoom = cover/fit) is mathematically correct
# for a clean aspect mismatch, but B-roll footage is often a wide picture with black
# bars BAKED INTO the pixels inside a nominal 16:9 file — so the file resolution
# reports 16:9 while the visible content is wider. Covering on the file aspect then
# over-crops massively (e.g. 16:9 file → 9:16 timeline computes 3.16x, but the real
# picture only needs ~1.4x). We can't measure the baked-in bars from metadata, so we
# clamp the zoom: cover what we can up to the cap, and accept residual bars beyond it
# rather than crop the subject to oblivion.
_MAX_FILL_ZOOM = 1.5


def _video_track1_end_sec(timeline: Any, fps: float) -> float | None:
    """Return the end time (seconds) of the last item on video track 1, or None.

    Used to cap B-roll duration so clips don't overhang the main video clip.
    """
    try:
        tl_start = timeline.GetStartFrame()
        items = timeline.GetItemListInTrack("video", 1) or []
        if not items:
            return None
        end_frame = max(item.GetEnd() for item in items)
        return (end_frame - tl_start) / fps
    except Exception as e:
        log.debug("[placer] _video_track1_end_sec failed (non-fatal): %s", e)
        return None


def _apply_fill_frame(timeline_item: Any, mpi: Any, project: Any) -> None:
    """Zoom-crop clip to fill the timeline frame with no black bars (CSS cover math).

    Resolve places clips with ZoomX/ZoomY=1.0 meaning "fit" (letterboxed/pillarboxed).
    To cover, we need zoom = cover_scale / fit_scale, where:
      fit_scale   = min(tl_w/clip_w, tl_h/clip_h)  (how Resolve fits the clip)
      cover_scale = max(tl_w/clip_w, tl_h/clip_h)  (what fills the frame)
    This relative zoom works for any orientation pair (portrait←landscape, etc.).
    Silently skips if resolution data is unavailable.
    """
    try:
        tl_w = int(project.GetSetting("timelineResolutionWidth") or 1920)
        tl_h = int(project.GetSetting("timelineResolutionHeight") or 1080)
        props = mpi.GetClipProperty() or {}
        res_str = props.get("Resolution", "")
        if not res_str or "x" not in res_str:
            log.debug("[placer] fill_frame: no Resolution property — skipping")
            return
        parts = res_str.lower().split("x")
        clip_w, clip_h = int(parts[0].strip()), int(parts[1].strip())
        if clip_w == 0 or clip_h == 0:
            return
        if abs((tl_w / tl_h) - (clip_w / clip_h)) < 0.01:
            return
        scale_x = tl_w / clip_w
        scale_y = tl_h / clip_h
        fit_scale = min(scale_x, scale_y)
        cover_scale = max(scale_x, scale_y)
        zoom = cover_scale / fit_scale
        if zoom > _MAX_FILL_ZOOM:
            log.debug("[placer] fill_frame: capping zoom %.3f → %.3f", zoom, _MAX_FILL_ZOOM)
            zoom = _MAX_FILL_ZOOM
        timeline_item.SetProperty("ZoomX", zoom)
        timeline_item.SetProperty("ZoomY", zoom)
        timeline_item.SetProperty("ZoomGang", True)
        # SetProperty("ZoomX") silently no-ops on Resolve free — verify it took,
        # and fall back to a wired Fusion Transform (the proven-rendering path) if
        # not, so the bars are actually removed on the free edition.
        if not _zoom_took(timeline_item, zoom):
            apply_fusion_static_zoom(timeline_item, zoom)
            log.info("[placer] fill_frame: ZoomX no-op (free edition?) — used Fusion static zoom")
        log.debug("[placer] fill_frame: %dx%d → %dx%d zoom=%.4f", clip_w, clip_h, tl_w, tl_h, zoom)
    except Exception as e:
        log.warning("[placer] fill_frame failed (non-fatal): %s", e)
