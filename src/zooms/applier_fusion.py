"""Fusion-specific zoom math + keyframing for the zoom applier.

Extracted from applier.py so the timeline orchestration stays separate from
the Resolve Fusion node wiring. These functions touch the clip's Fusion comp
directly (Transform tool, BezierSpline/XYPath keyframes) and raise on any
failure so the orchestrator can fall back to static SetProperty.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_EASE_SECONDS = 0.4   # ramp-in / ramp-out duration for the Fusion Size keyframes
_ZOOM_MAX = 1.6       # hard cap so black-edge compensation never over-zooms


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
    If it would exceed the cap, scale pan/tilt down proportionally to the largest
    offset the cap can cover — partial face follow, never a black edge. pan/tilt
    are normalized offsets in [-0.5, 0.5].
    """
    def cover(o: float) -> float:
        a = min(abs(o), 0.499)  # guard the fusion 1/(1-2o) singularity at o→0.5
        return 1.0 / (1.0 - 2.0 * a) if fusion else 1.0 + 2.0 * a

    need = max(user_zoom, cover(pan), cover(tilt))
    if need <= _ZOOM_MAX:
        return need, pan, tilt
    # Cap exceeded: scale pan/tilt down to the largest offset the cap can cover
    # (partial face follow, no black edge) rather than dropping the follow entirely.
    # Fusion cover formula inverted: max_offset = (1 - 1/Z) / 2 at Z = _ZOOM_MAX.
    max_offset = (1.0 - 1.0 / _ZOOM_MAX) / 2.0 if fusion else (_ZOOM_MAX - 1.0) / 2.0
    largest = max(abs(pan), abs(tilt), 1e-9)
    scale = min(max_offset / largest, 1.0)
    return user_zoom, pan * scale, tilt * scale


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
    """Apply an animated ease-in/hold/ease-out zoom via Fusion scripting API.

    Wires a Transform into the clip's Fusion comp (MediaIn → Transform → MediaOut),
    then attaches BezierSpline keyframes to Size and an XYPath to Center.

    Keyframe layout (clip-local frames): 0 (neutral) → ramp (full zoom+offset)
    → hold (plateau) → last (ease out to neutral).
    pan/tilt are normalized subject offsets in [-0.5, 0.5].
    Raises on any failure so the caller can fall back to static SetProperty.
    """
    ramp = max(1, round(_EASE_SECONDS * fps))
    last = max(1, seg_len_frames - 1)
    if 2 * ramp >= last:
        ramp = max(1, last // 2)
    hold = last - ramp

    target_x = 0.5 - pan
    target_y = 0.5 + tilt

    log.info(
        "Fusion zoom scripting: clip=%s  size=%.3f  pan=%.3f tilt=%.3f  "
        "target_x=%.4f target_y=%.4f  ramp=%d hold=%d last=%d",
        item.GetName(), zoom_amount, pan, tilt, target_x, target_y,
        ramp, hold, last,
    )

    comp, xf = _wire_transform(item)

    # --- Size: BezierSpline (confirmed working) ---
    size_spline = comp.AddTool("BezierSpline", -32768, -32768)
    if size_spline is None:
        raise RuntimeError("could not add BezierSpline for Size")
    xf.SetInput("Size", size_spline)
    size_spline.SetKeyFrames({
        0:    {1: 1.0},
        ramp: {1: zoom_amount},
        hold: {1: zoom_amount},
        last: {1: 1.0},
    })
    log.info("Size spline keyframes set: 0→1.0, %d→%.3f, %d→%.3f, %d→1.0",
             ramp, zoom_amount, hold, zoom_amount, last)

    # --- Center: XYPath wired to two BezierSplines ---
    # Direct SetInput("Center.X", spline) returns None (sub-input not addressable).
    # XYPath connects to Center successfully. XYPath itself has X/Y sub-inputs that
    # accept BezierSplines — wire spline_x → XYPath.X, spline_y → XYPath.Y,
    # then XYPath → Transform.Center.
    if pan or tilt:
        path = comp.AddTool("XYPath", -32768, -32768)
        spline_x = comp.AddTool("BezierSpline", -32768, -32768)
        spline_y = comp.AddTool("BezierSpline", -32768, -32768)
        if path is None or spline_x is None or spline_y is None:
            log.warning("Could not add XYPath/BezierSpline tools — using static offset")
            xf.SetInput("Center", {1: target_x, 2: target_y})
        else:
            # Wire splines into XYPath sub-inputs, then XYPath into Center
            cx = path.SetInput("X", spline_x)
            cy = path.SetInput("Y", spline_y)
            cc = xf.SetInput("Center", path)
            log.info("Center wiring: path.X=%r path.Y=%r xf.Center=%r", cx, cy, cc)
            spline_x.SetKeyFrames({
                0:    {1: 0.5},
                ramp: {1: target_x},
                hold: {1: target_x},
                last: {1: 0.5},
            })
            spline_y.SetKeyFrames({
                0:    {1: 0.5},
                ramp: {1: target_y},
                hold: {1: target_y},
                last: {1: 0.5},
            })
            kf_x = spline_x.GetKeyFrames() if hasattr(spline_x, "GetKeyFrames") else None
            log.info("Center spline readback: X=%r", kf_x)
    else:
        xf.SetInput("Center", {1: 0.5, 2: 0.5})
