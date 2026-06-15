"""Pure B-roll placement predicates shared by the manual tab and the
autonomous agent.

These were previously implemented 2–3 times with slightly different math.
Centralizing them guarantees the manual flow and the autonomous flow make
identical pacing decisions. No Resolve, no UI — just numbers in, decision out.
"""

from __future__ import annotations

# Face-time gap below which a visible cut back to the speaker looks like a
# glitch. Clips closer than this get merged: the previous clip's tracked end
# is extended to cover both, and the new clip is skipped.
MIN_FACE_SEC = 1.0

# Minimum spacing the manual collision-fixer enforces when bumping clips that
# would otherwise land on the same record frame (Resolve rejects duplicates).
MIN_COLLISION_GAP = 0.5


def cap_duration(
    raw: float,
    max_dur: float,
    *,
    in_point: float = 0.0,
    zero_means_full: bool = False,
) -> float:
    """Clamp a clip duration to ``max_dur``.

    Args:
        raw:        Source duration in seconds.
        max_dur:    Cap; ``<= 0`` disables capping.
        in_point:   Trim offset subtracted before capping (autonomous semantic
                    path trims into the clip). Default 0.
        zero_means_full: Manual path treats a ``raw <= 0`` (unknown) duration
                    as "use the full cap". Autonomous paths leave 0 as 0 and
                    fall back to a known source duration elsewhere.

    Returns:
        The capped, non-negative duration.
    """
    if zero_means_full and raw <= 0.0:
        return max(max_dur, 0.0)
    if max_dur > 0 and raw > 0:
        capped = min(raw - in_point, max_dur)
    else:
        # capping disabled / unknown duration: preserve raw untouched (matches
        # the original autonomous + manual behavior — no in_point subtraction)
        capped = raw
    return max(capped, 0.0)


def should_place(
    seg_start: float,
    last_placed_end_sec: float,
    *,
    natural_placement: bool,
    no_start_broll: bool,
    intro_skip_sec: float,
    min_gap_sec: float,
) -> tuple[bool, str]:
    """Return ``(True, '')`` if a segment is eligible for B-roll, else
    ``(False, reason)``.

    Enforces the two natural-placement rules: skip the intro window, and keep a
    minimum gap from the previously placed clip.
    """
    if not natural_placement:
        return True, ""
    if no_start_broll and seg_start < intro_skip_sec:
        return False, f"intro skip ({seg_start:.1f}s < {intro_skip_sec:.1f}s)"
    if last_placed_end_sec > 0.0 and (seg_start - last_placed_end_sec) < min_gap_sec:
        return False, f"gap too small ({seg_start - last_placed_end_sec:.1f}s < {min_gap_sec:.1f}s)"
    return True, ""


def check_gap(
    seg_start: float,
    seg_duration: float,
    last_placed_end_sec: float,
) -> tuple[bool, float]:
    """Return ``(should_extend, new_end_sec)``.

    should_extend=True  → gap is too short (< ``MIN_FACE_SEC``); extend the
                          previous clip's tracked end to ``seg_start +
                          seg_duration`` and skip this clip.
    should_extend=False → gap is fine, place normally.
    """
    if last_placed_end_sec <= 0.0:
        return False, 0.0
    gap = seg_start - last_placed_end_sec
    if gap < MIN_FACE_SEC:
        return True, seg_start + seg_duration
    return False, 0.0
