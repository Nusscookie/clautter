"""Place subtitle blocks as Fusion Title clips on a new DaVinci Resolve video track."""

from __future__ import annotations
from typing import Any

from src.subtitles.formatter import build_blocks
from src.subtitles.fusion_style import apply_fusion_text_style
from src.subtitles.fusion_template import bootstrap_textplus_template, find_fusion_title_template
from src.subtitles.presets import PRESETS
from src.utils.logger import get_logger
from src.utils.resolve_utils import ensure_video_track_order

log = get_logger(__name__)


def place_fusion_titles(
    resolve: Any,
    words: list[dict],
    fps: float,
    timeline: Any,
    style: dict,
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
    subtitle_track_index: int | None = None,
) -> bool:
    """Place subtitle blocks as Fusion Title clips on a new video track.

    Finds a Fusion Title template in the Media Pool (auto-importing bundled DRB
    if needed), then uses AppendToTimeline(mediaType=1) to place one clip per
    subtitle block. Returns False on any failure so the caller can fall back to SRT.
    """
    if not timeline:
        log.warning("place_fusion_titles: no timeline")
        return False

    preset = PRESETS.get(preset_name, PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("place_fusion_titles: no word entries")
        return False

    blocks = build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)
    if not blocks:
        return False

    try:
        tl_start = timeline.GetStartFrame()
    except Exception:
        tl_start = 0

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = project.GetMediaPool()
    except Exception as e:
        log.warning("place_fusion_titles: cannot get media pool: %s", e)
        return False

    # Bootstrap stock Text+ template (plain, no baked styling). SetInput on the
    # template comp BEFORE AppendToTimeline so every clone inherits the style.
    template_mp = bootstrap_textplus_template(resolve, timeline, style, media_pool)
    if not template_mp:
        log.info("Bootstrap failed; trying bundled DRB / existing template")
        template_mp = find_fusion_title_template(media_pool)
    if not template_mp:
        log.warning(
            "place_fusion_titles: no Fusion Title template found. "
            "Drag a Text+ title from the Titles panel into the Media Pool, or install AutoSubs."
        )
        return False

    template_fps = fps
    try:
        _fps_str = template_mp.GetClipProperty().get("FPS")
        if _fps_str:
            template_fps = float(_fps_str)
    except Exception:
        pass

    try:
        if subtitle_track_index is not None:
            subtitle_track = subtitle_track_index
            log.info("place_fusion_titles: reusing existing video track %d", subtitle_track)
        else:
            # Ensure B-Roll track exists first so Subtitle always lands above it.
            ordered = ensure_video_track_order(timeline)
            subtitle_track = ordered.get("Subtitle", -1)
            if subtitle_track <= 0:
                log.warning("place_fusion_titles: could not resolve Subtitle track")
                return False
            log.info("place_fusion_titles: subtitle clips on video track %d", subtitle_track)
    except Exception as e:
        log.warning("place_fusion_titles: track setup failed: %s", e)
        return False

    # Clear any existing subtitle clips so re-runs don't stack on top of old ones.
    try:
        existing = timeline.GetItemListInTrack("video", subtitle_track)
        if existing:
            timeline.DeleteClips(existing)
            log.info("place_fusion_titles: cleared %d existing clip(s) from subtitle track %d", len(existing), subtitle_track)
    except Exception as e:
        log.warning("place_fusion_titles: could not clear subtitle track: %s", e)

    clip_list = []
    for block in blocks:
        record_frame = tl_start + int(block["start"] * fps)
        end_frame    = max(1, int((block["end"] - block["start"]) * template_fps))
        clip_list.append({
            "mediaPoolItem": template_mp,
            "mediaType":     1,
            "startFrame":    0,
            "endFrame":      end_frame,
            "recordFrame":   record_frame,
            "trackIndex":    subtitle_track,
        })

    try:
        placed = media_pool.AppendToTimeline(clip_list)
        if not placed:
            log.warning("place_fusion_titles: AppendToTimeline returned empty")
            return False
        log.info("place_fusion_titles: placed %d clips on track %d", len(placed), subtitle_track)
    except Exception as e:
        log.warning("place_fusion_titles: AppendToTimeline failed: %s", e)
        return False

    highlight = preset.highlight_color if preset.word_by_word else None
    if style.get("highlight_color") and preset.word_by_word:
        highlight = style["highlight_color"]

    for block, item in zip(blocks, placed):
        if highlight:
            apply_fusion_text_style(item, block["text"], style, highlight_color=highlight)
        else:
            apply_fusion_text_style(item, block["text"], style)

    log.info(
        "place_fusion_titles: done — %d clips, preset=%s, highlight=%s",
        min(len(blocks), len(placed)), preset_name, highlight,
    )
    return True
