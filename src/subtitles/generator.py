"""Subtitle generation: word timings → SRT file + DaVinci subtitle track import."""

from __future__ import annotations
import os
import tempfile
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Style Presets
# ──────────────────────────────────────────────────────────────────────

class _Preset:
    """Configuration for a subtitle style."""
    words_per_line: int
    lines_per_block: int
    uppercase: bool
    word_by_word: bool        # one entry per word (Hormozi/TikTok style)
    highlight_color: str | None  # hex color for the active word; None = use primary_color

    def __init__(
        self,
        words_per_line: int = 8,
        lines_per_block: int = 2,
        uppercase: bool = False,
        word_by_word: bool = False,
        highlight_color: str | None = None,
    ) -> None:
        self.words_per_line = words_per_line
        self.lines_per_block = lines_per_block
        self.uppercase = uppercase
        self.word_by_word = word_by_word
        self.highlight_color = highlight_color


_PRESETS: dict[str, _Preset] = {
    "Standard":           _Preset(words_per_line=8, lines_per_block=2),
    "YouTube":            _Preset(words_per_line=7, lines_per_block=2),
    "TikTok":             _Preset(words_per_line=5, lines_per_block=1, uppercase=True,
                                  word_by_word=True,  highlight_color="#FF0000"),
    "Alex Hormozi Style": _Preset(words_per_line=3, lines_per_block=1, uppercase=True,
                                  word_by_word=True,  highlight_color="#FFFF00"),
}


# ──────────────────────────────────────────────────────────────────────
# SRT formatting helpers
# ──────────────────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    ms = int(round(seconds * 1000))
    h = ms // 3_600_000;  ms %= 3_600_000
    m = ms // 60_000;     ms %= 60_000
    s = ms // 1_000;      ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_timestamp(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.cc"""
    cs = int(round(seconds * 100))
    h  = cs // 360000; cs %= 360000
    m  = cs // 6000;   cs %= 6000
    s  = cs // 100;    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &H00BBGGRR format."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _build_blocks(
    word_entries: list[dict],
    words_per_line: int,
    lines_per_block: int,
    uppercase: bool,
    word_by_word: bool = False,
) -> list[dict]:
    """Build timed subtitle blocks from a flat word list.

    Returns list of {start: float, end: float, text: str} dicts.
    """
    if not word_entries:
        return []
    blocks: list[dict] = []
    if word_by_word:
        for wd in word_entries:
            text = wd["word"].upper() if uppercase else wd["word"]
            blocks.append({"start": wd["start_sec"], "end": wd["end_sec"], "text": text})
    else:
        max_words = words_per_line * lines_per_block
        for i in range(0, len(word_entries), max_words):
            chunk = word_entries[i : i + max_words]
            text_words = [(wd["word"].upper() if uppercase else wd["word"]) for wd in chunk]
            line_chunks = [
                " ".join(text_words[j : j + words_per_line])
                for j in range(0, len(text_words), words_per_line)
            ]
            blocks.append({
                "start": chunk[0]["start_sec"],
                "end":   chunk[-1]["end_sec"],
                "text":  "\n".join(line_chunks),
            })
    return blocks


def words_to_srt(
    words: list[dict],
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
) -> str:
    """Convert word-timing entries to an SRT subtitle file string.

    Args:
        words:         List of {word, start_sec, end_sec, type} dicts.
        preset_name:   One of the _PRESETS keys (sets defaults).
        words_per_line: Override preset's words-per-line (1–12).
        lines_per_block: Override preset's lines-per-block (1–3).
        uppercase:     Override preset's uppercase flag.

    Returns:
        SRT file content as a string.
    """
    preset = _PRESETS.get(preset_name, _PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("words_to_srt: no word entries to format")
        return ""

    blocks = _build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)
    lines: list[str] = []
    for idx, block in enumerate(blocks, 1):
        start = _format_timestamp(block["start"])
        end   = _format_timestamp(block["end"])
        lines.extend([str(idx), f"{start} --> {end}", block["text"], ""])

    log.debug("Generated %d SRT subtitle entries (%s style)", len(blocks), preset_name)
    return "\n".join(lines)


def words_to_ass(
    words: list[dict],
    style: dict,
    preset_name: str = "YouTube",
    *,
    words_per_line: int | None = None,
    lines_per_block: int | None = None,
    uppercase: bool | None = None,
) -> str:
    """Convert word-timing entries to an ASS subtitle file string with visual styling.

    Args:
        words:         List of {word, start_sec, end_sec, type} dicts.
        style:         Style dict: font_family, font_size, bold, italic, underline,
                       primary_color (#RRGGBB), outline_color, outline_width, shadow.
        preset_name:   Layout preset (words_per_line, lines_per_block, word_by_word).
        words_per_line/lines_per_block/uppercase: Override layout preset values.

    Returns:
        ASS file content as a string.
    """
    preset = _PRESETS.get(preset_name, _PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("words_to_ass: no word entries to format")
        return ""

    blocks = _build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)

    bold_flag      = -1 if style.get("bold",      False) else 0
    italic_flag    = -1 if style.get("italic",    False) else 0
    underline_flag = -1 if style.get("underline", False) else 0
    primary_col    = _to_ass_color(style.get("primary_color",  "#FFFFFF"))
    outline_col    = _to_ass_color(style.get("outline_color",  "#000000"))
    font_name      = style.get("font_family",    "Arial")
    font_size      = int(style.get("font_size",    36))
    outline_w      = int(style.get("outline_width", 3))
    shadow_depth   = int(style.get("shadow",        1))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "Timer: 100.0000\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_col},{primary_col},{outline_col},"
        f"&H80000000,{bold_flag},{italic_flag},{underline_flag},0,100,100,0,0,1,"
        f"{outline_w},{shadow_depth},2,10,10,30,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for block in blocks:
        start = _format_ass_timestamp(block["start"])
        end   = _format_ass_timestamp(block["end"])
        text  = block["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    log.debug("Generated %d ASS entries (font=%s, size=%d)", len(blocks), font_name, font_size)
    return header + "\n".join(events) + "\n"


# ──────────────────────────────────────────────────────────────────────
# Timeline timestamp remapping
# ──────────────────────────────────────────────────────────────────────

def remap_words_to_timeline(
    words: list[dict],
    clips: list[Any],
    fps: float,
    tl_start_frame: int = 0,
) -> list[dict]:
    """Remap word timestamps from source-file time to cut-timeline time.

    ElevenLabs timestamps are relative to the source video file start.
    After smart cuts, each timeline clip covers a sub-range of the source.
    This function converts timestamps so subtitles align with the cut timeline.

    Words that fall entirely in a removed (silence) region are dropped.
    On an uncut timeline, clips cover the full source → identity mapping.
    """
    result: list[dict] = []
    for word in words:
        if word.get("type", "word") != "word":
            continue
        t_start = word["start_sec"]
        t_end = word["end_sec"]
        for clip in clips:
            src_start = clip.GetSourceStartFrame() / fps
            src_end = clip.GetSourceEndFrame() / fps
            if src_start <= t_start < src_end:
                clip_tl_sec = (clip.GetStart() - tl_start_frame) / fps
                new_start = clip_tl_sec + (t_start - src_start)
                new_end = clip_tl_sec + (min(t_end, src_end) - src_start)
                result.append({**word, "start_sec": new_start, "end_sec": new_end})
                break
        # word in a cut region → drop
    log.debug("remap_words_to_timeline: %d/%d words kept", len(result), len(words))
    return result


# ──────────────────────────────────────────────────────────────────────
# Fusion Title placement (primary subtitle path)
# ──────────────────────────────────────────────────────────────────────

# Localized "Fusion Title" type strings from DaVinci Resolve's Media Pool.
# Matches AutoSubs' titleStrings list so we recognise templates in any locale.
_FUSION_TITLE_TYPES: frozenset[str] = frozenset({
    "Fusion Title", "Generator",          # en (+ older en)
    "Fusion Titles",                       # th
    "Título – Fusion", "Título Fusion",    # es, pt
    "Titre Fusion",                        # fr
    "Титры на стр. Fusion",               # ru
    "Fusion Titel",                        # de
    "Titolo Fusion",                       # it
    "Fusionタイトル",                      # ja
    "Fusion标题",                          # zh
    "퓨전 타이틀",                         # ko
    "Tiêu đề Fusion",                     # vi
})


def _walk_media_pool(folder: Any):
    """Yield all MediaPoolItem objects in folder tree."""
    try:
        for clip in (folder.GetClipList() or []):
            yield clip
    except Exception:
        pass
    try:
        for sub in (folder.GetSubFolderList() or []):
            yield from _walk_media_pool(sub)
    except Exception:
        pass


def _find_fusion_title_template(media_pool: Any) -> Any | None:
    """Return first Fusion Title item from Media Pool.

    If none found, imports the bundled subtitle_template.drb from Clutter's
    own assets folder (no external dependency). Falls back to AutoSubs' DRB
    if the bundled asset is somehow absent.
    """
    import pathlib

    def _scan():
        for clip in _walk_media_pool(media_pool.GetRootFolder()):
            try:
                props = clip.GetClipProperty()
                clip_name = props.get("Clip Name", "").lower()
                if (props.get("Type") in _FUSION_TITLE_TYPES
                        or "text+" in clip_name
                        or "clutter" in clip_name):
                    log.debug("Fusion Title template: %s (type=%s)",
                              props.get("Clip Name"), props.get("Type"))
                    return clip
            except Exception:
                pass
        return None

    def _import_drb(drb: str) -> None:
        for attempt in (
            lambda: media_pool.ImportFolderFromFile(drb, ""),
            lambda: media_pool.ImportFolderFromFile(drb),
        ):
            try:
                attempt()
                return
            except Exception:
                pass

    result = _scan()
    if result:
        log.info("Reusing Fusion Title template from Media Pool: %s",
                 result.GetClipProperty().get("Clip Name", "?"))
        return result

    # Try Clutter's own bundled template (one-time import per Resolve project).
    _own_drb = str(
        pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "subtitle_template.drb"
    )
    if os.path.exists(_own_drb):
        log.info("No Fusion Title in Media Pool — importing bundled template: %s", _own_drb)
        _import_drb(_own_drb)
        result = _scan()
        if result:
            return result

    log.warning(
        "place_fusion_titles: no Fusion Title template found and bundled DRB unavailable. "
        "Run assets/build_template.py inside Resolve Studio to regenerate subtitle_template.drb."
    )
    return None


def _apply_fusion_text_style(
    item: Any,
    text: str,
    style: dict,
    highlight_color: str | None = None,
) -> None:
    """Set text content and visual style on a Fusion Title clip.

    Handles both plain TextPlus clips (tool ID "TextPlus", input "StyledText")
    and AutoSubs Caption macro clips (tool name "Template", input "Text").
    Each SetInput is individually guarded so a missing input doesn't abort styling.
    """
    try:
        comp = item.GetFusionCompByIndex(1)
        if not comp:
            return
        # Prefer the actual TextPlus tool (accessible inside macros via FindToolByID).
        # AutoSubs Caption macro wrapper ("Template") only publishes a subset of inputs;
        # BorderWidth/BorderRed/Green/Blue are NOT published, so SetInput on the wrapper
        # silently does nothing. FindToolByID searches the full comp incl. inside macros.
        tool = comp.FindToolByID("TextPlus") or comp.FindTool("Template")
        if not tool:
            log.debug("_apply_fusion_text_style: no TextPlus tool found in comp")
            return

        # Text content — AutoSubs Caption uses "Text", plain TextPlus uses "StyledText"
        for input_name in ("StyledText", "Text"):
            try:
                tool.SetInput(input_name, text)
                break
            except Exception:
                pass

        color_hex = (highlight_color or style.get("primary_color", "#FFFFFF")).lstrip("#")
        for attr, val in (
            ("Font",   style.get("font_family", "Open Sans")),
            ("Size",   style.get("font_size", 36) / 360.0),
            ("Red1",   int(color_hex[0:2], 16) / 255.0),
            ("Green1", int(color_hex[2:4], 16) / 255.0),
            ("Blue1",  int(color_hex[4:6], 16) / 255.0),
        ):
            try:
                tool.SetInput(attr, val)
            except Exception:
                pass

        # Style selects the actual font face ("Bold", "Italic", "Bold Italic", "Regular").
        # The Bool inputs Bold/Italic apply a synthetic effect only; Style is authoritative.
        _b = style.get("bold", False)
        _i = style.get("italic", False)
        _style_str = ("Bold Italic" if _b and _i else "Bold" if _b else "Italic" if _i else "Regular")
        try:
            tool.SetInput("Style", _style_str)
        except Exception:
            pass
        for flag, attr in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
            try:
                tool.SetInput(attr, 1 if style.get(flag, False) else 0)
            except Exception:
                pass

        ow = style.get("outline_width", 0)
        try:
            tool.SetInput("BorderWidth", ow / 100.0)
        except Exception:
            pass

        # Fusion TextPlus element 2 = Outline. Color inputs follow {Key}{N} convention
        # matching element 1's Red1/Green1/Blue1 → element 2 is Red2/Green2/Blue2.
        # Enabled2 explicitly enables/disables — width=0 alone doesn't kill the element.
        _outline_on = style.get("outline_enabled", True) and ow > 0
        try:
            tool.SetInput("Enabled2", 1 if _outline_on else 0)
        except Exception:
            pass
        oc_hex = style.get("outline_color", "#000000").lstrip("#")
        for attr, val in (
            ("Red2",   int(oc_hex[0:2], 16) / 255.0),
            ("Green2", int(oc_hex[2:4], 16) / 255.0),
            ("Blue2",  int(oc_hex[4:6], 16) / 255.0),
        ):
            try:
                tool.SetInput(attr, val)
            except Exception:
                pass

        # Element 3 = Shadow.
        try:
            tool.SetInput("Enabled3", 1 if style.get("shadow", 0) else 0)
        except Exception:
            pass

    except Exception as e:
        log.debug("_apply_fusion_text_style: %s", e)


def _set_comp_text(comp: Any, text: str) -> bool:
    """Set the StyledText/Text input on a Fusion comp's TextPlus. Returns True if set."""
    if not comp:
        return False
    try:
        tool = comp.FindTool("Template") or comp.FindToolByID("TextPlus")
        if not tool:
            return False
        for input_name in ("StyledText", "Text"):
            try:
                tool.SetInput(input_name, text)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _bootstrap_textplus_template(
    resolve: Any, timeline: Any, style: dict, media_pool: Any
) -> Any | None:
    """Insert Resolve's stock Text+, apply our style, return MediaPoolItem.

    Returns the template MediaPoolItem to be used as the source for
    AppendToTimeline. Returns None on any failure.
    """
    try:
        # 1. Insert stock Text+ onto the timeline (Resolve gives us a plain,
        #    unstyled Text+ — no baked red outline, no OpenSans baked-in).
        bootstrap_clip = timeline.InsertFusionTitleIntoTimeline("Text+")
        if not bootstrap_clip:
            log.warning("Bootstrap: InsertFusionTitleIntoTimeline returned None")
            return None

        template_mp = bootstrap_clip.GetMediaPoolItem()
        if not template_mp:
            log.info("Bootstrap: GetMediaPoolItem returned None (Resolve Free) — scanning Media Pool")
            for candidate in _walk_media_pool(media_pool.GetRootFolder()):
                try:
                    if candidate.GetClipProperty().get("Type") in _FUSION_TITLE_TYPES:
                        template_mp = candidate
                        log.info("Bootstrap: found %s in Media Pool via scan",
                                 candidate.GetClipProperty().get("Clip Name"))
                        break
                except Exception:
                    continue
        if not template_mp:
            log.warning("Bootstrap: Media Pool scan also failed")
            try:
                timeline.DeleteClips([bootstrap_clip])
            except Exception:
                pass
            return None

        # 2. Apply our style to the TEMPLATE'S comp (not the placed clone).
        #    Every AppendToTimeline clone inherits the mutated state.
        try:
            comp = template_mp.GetFusionCompByIndex(1)
            tool = comp.FindToolByID("TextPlus") if comp else None
            if tool:
                color_hex = style.get("primary_color", "#FFFFFF").lstrip("#")
                _b = style.get("bold", False)
                _i = style.get("italic", False)
                _style_str = (
                    "Bold Italic" if _b and _i else
                    "Bold" if _b else
                    "Italic" if _i else
                    "Regular"
                )
                for attr, val in (
                    ("Font",     style.get("font_family", "Open Sans")),
                    ("Style",    _style_str),
                    ("Size",     style.get("font_size", 36) / 360.0),
                    ("Red1",     int(color_hex[0:2], 16) / 255.0),
                    ("Green1",   int(color_hex[2:4], 16) / 255.0),
                    ("Blue1",    int(color_hex[4:6], 16) / 255.0),
                    ("Bold",     1 if _b else 0),
                    ("Italic",   1 if _i else 0),
                    ("Underline", 1 if style.get("underline", False) else 0),
                ):
                    try:
                        tool.SetInput(attr, val)
                    except Exception as e:
                        log.debug("template SetInput %s: %s", attr, e)
                ow = style.get("outline_width", 0)
                try:
                    tool.SetInput("BorderWidth", ow / 100.0)
                except Exception:
                    pass
                # Enabled2/Red2/Green2/Blue2 — element 2 (Outline) inputs.
                _outline_on = style.get("outline_enabled", True) and ow > 0
                try:
                    tool.SetInput("Enabled2", 1 if _outline_on else 0)
                except Exception:
                    pass
                oc_hex = style.get("outline_color", "#000000").lstrip("#")
                for attr, val in (
                    ("Red2",   int(oc_hex[0:2], 16) / 255.0),
                    ("Green2", int(oc_hex[2:4], 16) / 255.0),
                    ("Blue2",  int(oc_hex[4:6], 16) / 255.0),
                ):
                    try:
                        tool.SetInput(attr, val)
                    except Exception:
                        pass
                try:
                    tool.SetInput("Enabled3", 1 if style.get("shadow", 0) else 0)
                except Exception:
                    pass
                # Comp.Save() is not a public Resolve API; ignore.
                log.info(
                    "Bootstrap template styled: font=%s size=%.3f bold=%s",
                    style.get("font_family", "Open Sans"),
                    style.get("font_size", 36) / 360.0,
                    style.get("bold", False),
                )
        except Exception as e:
            log.debug("Bootstrap style apply: %s", e)

        # 3. Delete the visible bootstrap clip — we have the MediaPoolItem,
        #    that's all we needed.
        try:
            timeline.DeleteClips([bootstrap_clip])
            log.debug("Bootstrap clip deleted; template MP kept for cloning")
        except Exception as e:
            log.warning("Bootstrap clip delete failed: %s", e)

        return template_mp

    except Exception as e:
        log.warning("Bootstrap template failed: %s", e)
        return None


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
) -> bool:
    """Place subtitle blocks as Fusion Title clips on a new video track.

    Finds a Fusion Title template in the Media Pool (auto-importing AutoSubs'
    caption-bin.drb if needed), then uses AppendToTimeline(mediaType=1) to place
    one clip per subtitle block. Style and text are applied via the Fusion comp
    after placement. Returns False on any failure so the caller can fall back to SRT.
    """
    if not timeline:
        log.warning("place_fusion_titles: no timeline")
        return False

    preset = _PRESETS.get(preset_name, _PRESETS["YouTube"])
    effective_wpl   = words_per_line  if words_per_line  is not None else preset.words_per_line
    effective_lpb   = lines_per_block if lines_per_block is not None else preset.lines_per_block
    effective_upper = uppercase       if uppercase       is not None else preset.uppercase

    word_entries = [w for w in words if w.get("type", "word") == "word" and w.get("word", "").strip()]
    if not word_entries:
        log.warning("place_fusion_titles: no word entries")
        return False

    blocks = _build_blocks(word_entries, effective_wpl, effective_lpb, effective_upper, preset.word_by_word)
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

    # ── Bootstrap stock Text+ template (plain, no baked styling) ──
    # SetInput on the template comp BEFORE AppendToTimeline so every clone
    # inherits the mutated state. Bundled DRB is only a fallback — its
    # CompositionBA bakes in red outline / OpenSans that overrides per-clip
    # SetInput calls.
    template_mp = _bootstrap_textplus_template(resolve, timeline, style, media_pool)
    if not template_mp:
        log.info("Bootstrap failed; trying bundled DRB / existing template")
        template_mp = _find_fusion_title_template(media_pool)
    if not template_mp:
        log.warning(
            "place_fusion_titles: no Fusion Title template found. "
            "Drag a Text+ title from the Titles panel into the Media Pool, or install AutoSubs."
        )
        return False

    # Template FPS for endFrame calculation (may differ from timeline FPS)
    template_fps = fps
    try:
        _fps_str = template_mp.GetClipProperty().get("FPS")
        if _fps_str:
            template_fps = float(_fps_str)
    except Exception:
        pass

    # ── Add new video track for subtitle clips ──
    try:
        existing_tracks = timeline.GetTrackCount("video")
        timeline.AddTrack("video")
        subtitle_track = existing_tracks + 1
        # Name the track "Subtitle" so it shows up by name in Resolve (was missing).
        try:
            timeline.SetTrackName("video", subtitle_track, "Subtitle")
        except Exception as e:
            log.debug("SetTrackName failed: %s", e)
        log.info("place_fusion_titles: subtitle clips on video track %d", subtitle_track)
    except Exception as e:
        log.warning("place_fusion_titles: AddTrack failed: %s", e)
        return False

    # ── Build clip list and place ──
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

    # ── Apply per-clip overrides — base style already lives on the template. ──
    # AppendToTimeline clones inherit font/color/size/outline from the template's
    # mutated comp. Per-clip work is limited to:
    #   - Setting the StyledText/Text to the block's text
    #   - Overriding the color when this clip is the "highlighted" word
    highlight = preset.highlight_color if preset.word_by_word else None
    if style.get("highlight_color") and preset.word_by_word:
        highlight = style["highlight_color"]

    for block, item in zip(blocks, placed):
        # Always re-apply full user style on every placed clip. This guards
        # against the bundled-DRB fallback leaking baked font/outline values
        # (was previously only run for word_by_word presets).
        if highlight:
            _apply_fusion_text_style(item, block["text"], style, highlight_color=highlight)
        else:
            _apply_fusion_text_style(item, block["text"], style)

    log.info(
        "place_fusion_titles: done — %d clips, preset=%s, highlight=%s",
        min(len(blocks), len(placed)), preset_name, highlight,
    )
    return True


# ──────────────────────────────────────────────────────────────────────
# DaVinci Resolve import
# ──────────────────────────────────────────────────────────────────────

def import_srt_to_timeline(resolve: Any, srt_path: str, timeline: Any, style: dict | None = None) -> bool:
    """Import an SRT file and attach it to the timeline as a subtitle track.

    DaVinci Resolve does not have a direct scripting API for SRT import as of v20.
    Best available approach:
      1. Import SRT as a Media Pool item.
      2. Add a subtitle track if none exists.
      3. Append the SRT item to the subtitle track.

    Falls back gracefully and logs the SRT path so the user can import manually.

    Returns True if the operation was attempted without errors.
    """
    if not os.path.exists(srt_path):
        log.error("SRT file not found: %s", srt_path)
        return False

    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        media_pool = project.GetMediaPool()

        # Import subtitle file into media pool
        imported = media_pool.ImportMedia([srt_path])
        srt_item = imported[0] if imported else None
        if not srt_item:
            ext = os.path.splitext(srt_path)[1].lower()
            log.warning(
                "ImportMedia returned empty for %s file: %s — "
                "Resolve may not support this format via the Python API.",
                ext, srt_path,
            )
            return False

        # Ensure a subtitle track exists and clear any old subtitle clips
        if timeline:
            if timeline.GetTrackCount("subtitle") == 0:
                timeline.AddTrack("subtitle")
                log.info("Added subtitle track to timeline")
            else:
                for _i in range(1, timeline.GetTrackCount("subtitle") + 1):
                    _items = timeline.GetItemListInTrack("subtitle", _i)
                    if _items:
                        try:
                            timeline.DeleteClips(_items)
                            log.debug("Cleared %d subtitle clip(s) from track %d", len(_items), _i)
                        except Exception as _e:
                            log.warning("Could not clear subtitle track %d: %s", _i, _e)

        # Get the timeline's real start frame. DaVinci timelines start at 01:00:00:00
        # (~frame 90000), not frame 0. recordFrame: 0 is before the timeline exists
        # and gets silently ignored. Use GetStartFrame() — same method AutoSubs uses.
        tl_start = 0
        try:
            if timeline:
                tl_start = timeline.GetStartFrame()
        except Exception as _e:
            log.debug("GetStartFrame failed, falling back to first clip: %s", _e)
            try:
                _v = timeline.GetItemListInTrack("video", 1)
                if _v:
                    tl_start = _v[0].GetStart()
            except Exception:
                pass
        log.info("Placing SRT at timeline frame %d", tl_start)

        # Place SRT clip on the timeline.
        # trackType/trackIndex are undocumented keys — Resolve detects SRT media
        # type automatically and places on the subtitle track. Omitting them avoids
        # potential conflicts with recordFrame handling.
        if srt_item:
            appended = media_pool.AppendToTimeline([{
                "mediaPoolItem": srt_item,
                "recordFrame": tl_start,
            }])
            if not appended:
                log.warning(
                    "AppendToTimeline returned empty — drag '%s' from Media Pool to subtitle track",
                    srt_path,
                )
            else:
                try:
                    _placed = timeline.GetItemListInTrack("subtitle", 1)
                    if _placed:
                        actual = _placed[0].GetStart()
                        log.info("Subtitle clip landed at frame %d (wanted %d)", actual, tl_start)
                        if actual != tl_start:
                            log.warning(
                                "recordFrame ignored by Resolve for subtitle clips — "
                                "drag subtitle clip to frame %d manually", tl_start
                            )
                        # Attempt to apply font/size style via SetProperty on each placed clip.
                        # Resolve subtitle clips may or may not expose these properties;
                        # failures are silently ignored so the import still succeeds.
                        if style:
                            _styled = 0
                            for _item in _placed:
                                try:
                                    _cc = 0
                                    try:
                                        _cc = _item.GetFusionCompCount()
                                    except Exception:
                                        pass
                                    if _cc:
                                        _comp = _item.GetFusionCompByIndex(1)
                                        _tt = _comp.FindToolByID("TextPlus") if _comp else None
                                        if not _tt and _comp:
                                            try:
                                                _tools = _comp.GetToolList()
                                                log.info("Subtitle comp tools: %s", list(_tools.keys()) if _tools else "none")
                                            except Exception:
                                                pass
                                        if _tt:
                                            _tt.SetInput("Font", style.get("font_family", "Arial"))
                                            _tt.SetInput("Size", style.get("font_size", 36) / 360.0)
                                            _pc = style.get("primary_color", "#FFFFFF").lstrip("#")
                                            _tt.SetInput("Red1",   int(_pc[0:2], 16) / 255.0)
                                            _tt.SetInput("Green1", int(_pc[2:4], 16) / 255.0)
                                            _tt.SetInput("Blue1",  int(_pc[4:6], 16) / 255.0)
                                            if style.get("bold"):
                                                _tt.SetInput("Bold", 1)
                                            if style.get("italic"):
                                                _tt.SetInput("Italic", 1)
                                            _styled += 1
                                    else:
                                        try:
                                            _item.SetProperty("Font", style.get("font_family", "Arial"))
                                            _item.SetProperty("FontSize", str(int(style.get("font_size", 36))))
                                        except Exception as _sp:
                                            log.debug("SetProperty fallback failed: %s", _sp)
                                except Exception as _se:
                                    log.warning("Style on subtitle clip %d: %s", _styled, _se)
                            log.info("Applied style to %d/%d subtitle clips", _styled, len(_placed))
                except Exception as _e:
                    log.debug("Post-placement check failed: %s", _e)

        log.info("Subtitle file imported to media pool: %s", srt_path)
        return True

    except Exception as e:
        log.error("import_srt_to_timeline failed: %s", e)
        log.info("Manual import: drag '%s' from Media Pool to the subtitle track.", srt_path)
        return False
