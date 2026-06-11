"""Apply zoom cuts to a DaVinci Resolve timeline.

Strategy (same non-destructive new-timeline approach as Smart Cuts):
  1. For each clip, split it into sub-segments at zoom boundaries.
  2. On zoom segments, apply the zoom. With "Smooth Zoom" (fade=True) this is a
     true animated ease via a Fusion Transform node keyframed Size 1.0 → zoom →
     hold → 1.0, optionally tracking Center toward the detected face. With a hard
     cut (fade=False) — or if the Fusion path fails — it falls back to static
     ZoomX/ZoomY/Pan/Tilt via SetProperty.
  3. Create a new timeline containing the reconstructed segments.

Why Fusion keyframes now work: an earlier probe added a Transform tool but never
connected it into the comp's render graph (MediaIn → Transform → MediaOut), so
`SetInput("Size", …)` was a silent no-op and the code fell back to static
SetProperty (a hard cut). The fix — proven by docs/autocut_templates/zoom.comp —
is to wire the Transform's `Input` to MediaIn's Output and route MediaOut's
`Input` from the Transform. Once wired, Size/Center keyframes animate and render,
giving a real eased zoom. Static SetProperty remains the per-segment fallback.

Clip segmentation logic lives in applier_props.py.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.utils.logger import get_logger
from src.utils.timeline_utils import _unique_timeline_name
from src.zooms.applier_props import _segment_clips
from src.zooms.analyzer import ZoomPoint

log = get_logger(__name__)

_DYNAMIC_ZOOM_EASE_IN_OUT = 3  # Resolve DynamicZoomEase value for ease in & out
_EASE_SECONDS = 0.4            # ramp-in / ramp-out duration for the Fusion Size keyframes
_ZOOM_MAX = 1.6                # hard cap so black-edge compensation never over-zooms


def _safe_zoom(
    user_zoom: float, pan: float, tilt: float, fusion: bool = False
) -> tuple[float, float, float]:
    """Raise zoom to fully cover the pan/tilt shift, or drop the shift if it can't.

    A center-shifted clip exposes a black edge unless it is zoomed enough to cover
    the shift. The minimum covering zoom for a normalized offset o (per axis)
    differs by path:

      * static (clip-property Pan/Tilt in pixels):  zoom_to_cover(o) = 1 + 2*|o|
      * fusion (normalized Transform Center):        zoom_to_cover(o) = 1 / (1 - 2*|o|)
        — inverting o_max(Z) = (Z-1)/(2Z), the largest Center offset Z can cover.

    We take the largest of the user's zoom and what each axis needs. If that fits
    under _ZOOM_MAX, keep the full pan/tilt (a fully-covered face-centered zoom).
    If it would exceed the cap, we do NOT scale the pan down to a half-follow with a
    visible border — instead we discard the face follow entirely: plain center zoom
    at the user's amount. So every zoom is either fully covered + centered, or a
    clean center zoom. pan/tilt are normalized offsets in [-0.5, 0.5].
    """
    def cover(o: float) -> float:
        a = min(abs(o), 0.499)  # guard the fusion 1/(1-2o) singularity at o→0.5
        return 1.0 / (1.0 - 2.0 * a) if fusion else 1.0 + 2.0 * a

    need = max(user_zoom, cover(pan), cover(tilt))
    if need <= _ZOOM_MAX:
        return need, pan, tilt
    # Cannot cover the requested offset within the cap → drop the follow.
    return user_zoom, 0.0, 0.0


def _zoom_took(item: Any, expected: float) -> bool:
    """True if a SetProperty("ZoomX") actually applied (read it back).

    On Resolve free, the static zoom property can silently no-op, leaving ZoomX at
    ~1.0. Treat a missing/unchanged value as "did not take" so the caller can fall
    back to Fusion. Conservatively returns True if the value can't be read (don't
    double-apply when the property API simply doesn't expose a getter).
    """
    try:
        got = item.GetProperty("ZoomX")
        if got is None:
            return True
        return abs(float(got) - float(expected)) < 0.01
    except Exception:
        return True


def _wire_transform(item: Any) -> tuple[Any, Any]:
    """Acquire the clip's Fusion comp and return (comp, Transform tool) with the
    Transform wired into the render graph (MediaIn → Transform → MediaOut).

    Wiring the Transform's Input to MediaIn and routing MediaOut's Input from the
    Transform is the step that makes a scripted Transform actually render — without
    it SetInput("Size", …) is a silent no-op. Raises on any failure so the caller
    can fall back to static SetProperty. Shared by the animated zoom path and the
    static (free-edition) fallback used by zooms and B-Roll fill-frame.
    """
    comp = item.GetFusionCompByIndex(1) or item.AddFusionComp()
    if comp is None:
        raise RuntimeError("could not acquire or create a Fusion comp on the clip")

    mediain = comp.FindTool("MediaIn1")
    mediaout = comp.FindTool("MediaOut1")
    if mediain is None or mediaout is None:
        raise RuntimeError("clip comp is missing MediaIn1/MediaOut1")

    xf = comp.FindTool("Transform1") or comp.AddTool("Transform", -32768, -32768)
    if xf is None:
        raise RuntimeError("could not add a Transform tool")

    xf.SetInput("Input", mediain)
    mediaout.SetInput("Input", xf)
    return comp, xf


def apply_fusion_static_zoom(
    item: Any,
    zoom_amount: float,
    center_x: float = 0.5,
    center_y: float = 0.5,
) -> None:
    """Set a static (non-animated) Size + Center on a wired Fusion Transform.

    The free-edition-safe equivalent of SetProperty("ZoomX"/"ZoomY") — used as a
    fallback when the static clip-property path silently no-ops (it does on Resolve
    free). center is a point in Resolve's normalized [0,1] space. Raises on failure.
    """
    _comp, xf = _wire_transform(item)
    xf.SetInput("Size", float(zoom_amount))
    xf.SetInput("Center", {1: center_x, 2: center_y})


def _apply_fusion_zoom(
    item: Any,
    zoom_amount: float,
    pan: float,
    tilt: float,
    seg_len_frames: int,
    fps: float,
) -> None:
    """Apply an animated ease-in/hold/ease-out zoom via a Fusion Transform node.

    Wires MediaIn → Transform → MediaOut (the step the old probe missed) so the
    Transform renders, then animates Size 1.0 → zoom → hold → 1.0 by connecting a
    BezierSpline modifier to the Size input and keyframing the spline. Inline
    `SetInput("Size", value, frame)` does NOT animate in Resolve's Fusion API — it
    only overwrites a constant value (probe-confirmed); keyframes must live in a
    separate spline op, the same pattern AutoCut's caption comp uses
    (LINE_N_KEYFRAMES). The spline's default bezier handles give the ease for free.

    Center is *animated in lockstep with Size* so it sits at frame-center (0.5,0.5)
    whenever Size = 1.0 (the ease-in start and ease-out end) and reaches the
    face-centered target (0.5 - pan, 0.5 + tilt) only at the zoomed plateau. A
    static off-center Center would expose a black bar at the Size=1.0 endpoints —
    that was the old bug. pan/tilt are normalized subject offsets in [-0.5, 0.5];
    Resolve Pan>0 moves the image right (face at Center.X = 0.5 - pan), Tilt>0 up
    (Center.Y = 0.5 + tilt). _safe_zoom has already guaranteed the plateau Size
    covers the target offset, so no edge shows at the hold either.

    Comp frames are clip-local (0 .. seg_len_frames-1). Raises on any failure so
    the caller can fall back to the static SetProperty path.
    """
    comp, xf = _wire_transform(item)

    ramp = max(1, round(_EASE_SECONDS * fps))
    last = max(1, seg_len_frames - 1)
    # On short segments, clamp the ease points so they don't cross (single peak).
    if 2 * ramp >= last:
        ramp = max(1, last // 2)
    hold = last - ramp

    # Animated Size via a connected BezierSpline. Keyframes are {frame: {1: value}};
    # the spline interpolates with eased bezier handles by default.
    size_spline = comp.AddTool("BezierSpline", -32768, -32768)
    if size_spline is None:
        raise RuntimeError("could not add a BezierSpline for Size animation")
    xf.SetInput("Size", size_spline)
    size_spline.SetKeyFrames({
        0:    {1: 1.0},
        ramp: {1: zoom_amount},
        hold: {1: zoom_amount},
        last: {1: 1.0},
    })

    # Animated Center: a point that traces frame-center → face → face → frame-center
    # in lockstep with Size, via an XYPath modifier (the point-input analogue of the
    # Size BezierSpline). Only animate when there's an actual shift; a pure center
    # zoom leaves Center at its (0.5, 0.5) default.
    if pan or tilt:
        target_x = 0.5 - pan
        target_y = 0.5 + tilt
        path = comp.AddTool("XYPath", -32768, -32768)
        if path is None:
            raise RuntimeError("could not add an XYPath for Center animation")
        xf.SetInput("Center", path)
        # XYPath keyframes its X and Y displacement splines; {1: x, 2: y} per frame.
        path.SetKeyFrames({
            0:    {1: 0.5,      2: 0.5},
            ramp: {1: target_x, 2: target_y},
            hold: {1: target_x, 2: target_y},
            last: {1: 0.5,      2: 0.5},
        })


@dataclass
class ZoomResult:
    new_timeline_name: str
    zooms_applied: int
    total_clips_processed: int


def _apply_segment_zoom(
    item: Any,
    zoom_amount: float,
    pan: float,
    tilt: float,
    fade: bool,
    frame_w: int,
    frame_h: int,
) -> None:
    """Set static zoom + face-centered Pan/Tilt on a timeline item.

    pan/tilt are normalized subject offsets in [-0.5, 0.5]; they are scaled to
    project pixels here. fade enables Resolve's DynamicZoomEase so the zoom
    transition is eased rather than a hard cut.
    """
    item.SetProperty("ZoomX", zoom_amount)
    item.SetProperty("ZoomY", zoom_amount)
    item.SetProperty("ZoomGang", True)

    if pan:
        item.SetProperty("Pan", round(pan * frame_w, 2))
    if tilt:
        item.SetProperty("Tilt", round(tilt * frame_h, 2))

    if fade:
        item.SetProperty("DynamicZoomEase", _DYNAMIC_ZOOM_EASE_IN_OUT)


def apply_zooms(
    resolve: Any,
    timeline: Any,
    clips: list[Any],
    zoom_points: list[ZoomPoint],
    fade: bool = True,
    zoom_amount: float = 1.15,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    target_timeline: Optional[Any] = None,
) -> ZoomResult:
    """Create a timeline with zoom effects applied at the detected points.

    Non-destructive when creating a new timeline; appends to target_timeline if provided.

    Args:
        resolve:           DaVinci Resolve object.
        timeline:          Source timeline.
        clips:             TimelineItems from video track 1.
        zoom_points:       Detected zoom moments.
        fade:              If True, animate via Fusion keyframes (smooth ease in/out).
                           If False, static SetProperty zoom (hard cut).
        zoom_amount:       Scale factor for zoom segments (e.g. 1.15 = 115%).
        progress_callback: Optional progress fn(current, total, message).
        target_timeline:   If set, append clips here instead of creating a new timeline.

    Returns:
        ZoomResult with stats.
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()

    try:
        fps = float(project.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        fps = 25.0

    try:
        frame_w = int(project.GetSetting("timelineResolutionWidth") or 1920)
        frame_h = int(project.GetSetting("timelineResolutionHeight") or 1080)
    except Exception:
        frame_w, frame_h = 1920, 1080

    if target_timeline is not None:
        new_name = target_timeline.GetName()
        log.info("Appending zooms to existing timeline '%s' | %d zoom points", new_name, len(zoom_points))
    else:
        new_name = _unique_timeline_name(project, f"{timeline.GetName()}_zooms")
        log.info("Creating zoom timeline '%s' | %d zoom points", new_name, len(zoom_points))

    zoom_map: dict[int, tuple[int, float, float, float]] = {
        zp.timeline_frame: (
            zp.timeline_frame + zp.duration_frames, zp.zoom_amount, zp.pan, zp.tilt
        )
        for zp in zoom_points
    }

    clip_infos, zoom_meta, clips_processed, zooms_applied = _segment_clips(
        clips, fps, zoom_map, progress_callback, fade=fade,
    )

    if not clip_infos:
        raise RuntimeError("No clip segments found for zoom timeline.")

    if progress_callback:
        progress_callback(len(clips), len(clips), f"Building timeline '{new_name}'...")

    if target_timeline is not None:
        dest_timeline = target_timeline
        project.SetCurrentTimeline(dest_timeline)
        for _ttype in ("video", "audio"):
            try:
                _items = dest_timeline.GetItemListInTrack(_ttype, 1)
                if _items:
                    dest_timeline.DeleteClips(_items)
            except Exception as _e:
                log.warning("Could not clear %s track 1: %s", _ttype, _e)
    else:
        dest_timeline = media_pool.CreateEmptyTimeline(new_name)
        if dest_timeline is None:
            raise RuntimeError(f"Failed to create timeline '{new_name}'.")
        project.SetCurrentTimeline(dest_timeline)

    appended = media_pool.AppendToTimeline(clip_infos)

    if not appended or not isinstance(appended, (list, tuple)):
        raise RuntimeError(
            "AppendToTimeline returned no items — zoom timeline not built. "
            f"(got {type(appended).__name__})"
        )

    if progress_callback:
        progress_callback(len(clips), len(clips), "Applying zoom properties...")

    applied_ok = 0
    for i, (item, meta) in enumerate(zip(appended, zoom_meta)):
        if not meta.get("is_zoom"):
            continue

        raw_zoom = meta.get("zoom_amount", zoom_amount)
        raw_pan = meta.get("pan", 0.0)
        raw_tilt = meta.get("tilt", 0.0)
        seg_fade = meta.get("fade", fade)

        applied_via: Optional[str] = None
        if seg_fade:  # "Smooth Zoom" → animated Fusion ease (primary path)
            # Fusion Center model: cover the shift or drop it (see _safe_zoom).
            seg_zoom, seg_pan, seg_tilt = _safe_zoom(
                raw_zoom, raw_pan, raw_tilt, fusion=True
            )
            try:
                _apply_fusion_zoom(
                    item, seg_zoom, seg_pan, seg_tilt,
                    seg_len_frames=int(meta.get("seg_len", 1)), fps=fps,
                )
                applied_via = "fusion"
            except Exception as e:
                log.warning(
                    "Fusion zoom failed on segment %d, falling back to static: %s", i, e
                )

        if applied_via is None:  # hard cut requested, or Fusion failed → static
            # Static clip-property model uses the pixel cover math.
            seg_zoom, seg_pan, seg_tilt = _safe_zoom(
                raw_zoom, raw_pan, raw_tilt, fusion=False
            )
            try:
                _apply_segment_zoom(
                    item, seg_zoom, seg_pan, seg_tilt, seg_fade, frame_w, frame_h,
                )
                # SetProperty("ZoomX") silently no-ops on Resolve free — verify it
                # took, and fall back to a wired Fusion Transform if it didn't.
                if not _zoom_took(item, seg_zoom):
                    log.info(
                        "Static ZoomX no-op on segment %d (free edition?) — "
                        "applying Fusion static zoom", i,
                    )
                    apply_fusion_static_zoom(
                        item, seg_zoom,
                        center_x=0.5 - seg_pan, center_y=0.5 + seg_tilt,
                    )
                    applied_via = "fusion-static"
                else:
                    applied_via = "static"
            except Exception as e:
                log.warning("Zoom property failed on segment %d: %s", i, e)
                continue

        applied_ok += 1
        log.debug("Zoom applied to segment %d via %s: %.2f", i, applied_via, seg_zoom)

    if applied_ok == 0 and zooms_applied > 0:
        raise RuntimeError(
            "No zoom properties could be applied to any segment — "
            "the timeline was built but every SetProperty call failed."
        )

    log.info(
        "Created zoom timeline '%s': %d/%d zoom(s) applied, %d clip(s) processed",
        new_name, applied_ok, zooms_applied, clips_processed,
    )

    return ZoomResult(
        new_timeline_name=new_name,
        zooms_applied=applied_ok,
        total_clips_processed=clips_processed,
    )
