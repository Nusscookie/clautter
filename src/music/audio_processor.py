"""Pre-process audio files with pydub before placing in DaVinci Resolve.

DaVinci Resolve's Python API has no per-clip volume or fade controls for audio
TimelineItems, so we bake volume reduction and fades into the file itself.
Processed copies are cached in a 'processed/' subfolder of the download folder.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Union

from src.utils.logger import get_logger

log = get_logger(__name__)

SFX_GAIN_DB: float = -10.0
SUPPORTED_EXTS: frozenset[str] = frozenset({".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"})


def process_audio(
    input_path: str,
    output_path: str,
    volume_pct: int,
    fade_in_ms: int,
    fade_out_ms: int,
) -> str:
    """Load audio, apply volume reduction and fades, export as MP3.

    Args:
        input_path:  Source audio file (any pydub-supported format).
        output_path: Destination MP3 path.
        volume_pct:  Target volume as % of original (1–100). 35 → -4.56 dB.
        fade_in_ms:  Fade-in duration in milliseconds; 0 = no fade.
        fade_out_ms: Fade-out duration in milliseconds; 0 = no fade.

    Returns:
        output_path as string.
    """
    from pydub import AudioSegment  # lazy — pydub is heavy

    audio: AudioSegment = AudioSegment.from_file(input_path)

    gain_db = 10.0 * math.log10(max(volume_pct, 1) / 100.0)
    audio = audio + gain_db

    clip_len = len(audio)
    if fade_in_ms > 0:
        eff_fi = min(fade_in_ms, clip_len // 3)
        if eff_fi > 0:
            audio = audio.fade_in(eff_fi)
    if fade_out_ms > 0:
        eff_fo = min(fade_out_ms, clip_len // 3)
        if eff_fo > 0:
            audio = audio.fade_out(eff_fo)

    audio.export(output_path, format="mp3")
    return output_path


def apply_sfx_gain(
    input_path: str,
    output_path: str,
    gain_db: float,
) -> str:
    """Load audio, apply dB gain (negative = quieter), export as MP3."""
    from pydub import AudioSegment

    audio: AudioSegment = AudioSegment.from_file(input_path)
    audio = audio + gain_db
    audio.export(output_path, format="mp3")
    return output_path


def _music_cache_path(input_path: str, processed_dir: Path, volume_pct: int,
                      fade_in_ms: int, fade_out_ms: int) -> Path:
    stem = Path(input_path).stem
    return processed_dir / f"{stem}_v{volume_pct}_fi{fade_in_ms}_fo{fade_out_ms}.mp3"


def _sfx_cache_path(input_path: str, processed_dir: Path, gain_db: float) -> Path:
    stem = Path(input_path).stem
    gain_tag = f"{abs(gain_db):.0f}"
    return processed_dir / f"{stem}_db{gain_tag}.mp3"


def get_or_process_music(
    input_path: str,
    processed_dir: Union[Path, str],
    volume_pct: int,
    fade_in_ms: int,
    fade_out_ms: int,
) -> str:
    """Return path to a processed music copy, creating it if necessary.

    Falls back to returning input_path unchanged if pydub fails.
    """
    processed_dir = Path(processed_dir)
    out_path = _music_cache_path(input_path, processed_dir, volume_pct, fade_in_ms, fade_out_ms)

    if out_path.exists():
        log.debug("[audio_processor] cache hit: %s", out_path.name)
        return str(out_path)

    processed_dir.mkdir(parents=True, exist_ok=True)
    try:
        process_audio(input_path, str(out_path), volume_pct, fade_in_ms, fade_out_ms)
        log.info("[audio_processor] processed music → %s", out_path.name)
        return str(out_path)
    except Exception as e:
        log.warning("[audio_processor] pydub failed for %s: %s — using original",
                    Path(input_path).name, e)
        return input_path


def get_or_process_sfx(
    input_path: str,
    processed_dir: Union[Path, str],
    gain_db: float = SFX_GAIN_DB,
) -> str:
    """Return path to a gain-adjusted SFX copy, creating it if necessary.

    Falls back to returning input_path unchanged if pydub fails.
    """
    processed_dir = Path(processed_dir)
    out_path = _sfx_cache_path(input_path, processed_dir, gain_db)

    if out_path.exists():
        log.debug("[audio_processor] SFX cache hit: %s", out_path.name)
        return str(out_path)

    processed_dir.mkdir(parents=True, exist_ok=True)
    try:
        apply_sfx_gain(input_path, str(out_path), gain_db)
        log.info("[audio_processor] processed SFX → %s", out_path.name)
        return str(out_path)
    except Exception as e:
        log.warning("[audio_processor] pydub failed for SFX %s: %s — using original",
                    Path(input_path).name, e)
        return input_path
