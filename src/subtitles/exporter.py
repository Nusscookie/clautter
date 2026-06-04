"""Export transcript as SRT or plain TXT."""

from __future__ import annotations
import os
from src.utils.logger import get_logger

log = get_logger(__name__)


def export_srt(srt_content: str, output_path: str) -> None:
    """Write SRT content to a file.

    Args:
        srt_content: SRT file string from generator.words_to_srt().
        output_path: Destination file path.

    Raises:
        OSError if the file cannot be written.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    log.info("SRT exported: %s", output_path)


def export_txt(text: str, output_path: str) -> None:
    """Write plain transcript text to a file.

    Args:
        text:        Plain text transcript.
        output_path: Destination file path.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    log.info("TXT exported: %s", output_path)
