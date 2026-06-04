"""ElevenLabs Speech-to-Text (Scribe) API client.

Endpoint:  POST https://api.elevenlabs.io/v1/speech-to-text
Docs:      https://elevenlabs.io/docs/api-reference/speech-to-text
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
_DEFAULT_MODEL = "scribe_v1"

# Maximum file size the API accepts (100 MB)
_MAX_FILE_BYTES = 100 * 1024 * 1024


@dataclass
class WordEntry:
    word: str
    start_sec: float
    end_sec: float
    type: str = "word"  # "word" | "spacing" | "audio_event"

    def to_dict(self) -> dict:
        return {
            "word": self.word,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "type": self.type,
        }


class ElevenLabsClient:
    """Thin client for ElevenLabs Speech-to-Text API."""

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("ElevenLabs API key is empty.")
        self._api_key = api_key.strip()

    def transcribe(
        self,
        file_path: str,
        language: str = "",
        model_id: str = _DEFAULT_MODEL,
    ) -> list[dict]:
        """Transcribe an audio/video file using ElevenLabs STT.

        Args:
            file_path: Path to the media file. Video files are accepted directly —
                       ElevenLabs extracts the audio server-side.
            language:  BCP-47 language code (e.g. "en", "de"). Empty = auto-detect.
            model_id:  ElevenLabs STT model to use.

        Returns:
            List of dicts with keys: word, start_sec, end_sec, type.

        Raises:
            FileNotFoundError, ValueError, RuntimeError on various error conditions.
        """
        try:
            import requests  # type: ignore
        except ImportError:
            raise RuntimeError(
                "requests is not installed.\n"
                "Run: pip install requests"
            )

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found: {file_path}")

        file_size = path.stat().st_size
        if file_size > _MAX_FILE_BYTES:
            raise ValueError(
                f"File is {file_size / 1e6:.1f} MB — ElevenLabs STT limit is 100 MB.\n"
                "Consider extracting just the audio track first (e.g. with ffmpeg)."
            )

        log.info("Sending to ElevenLabs STT: %s (%.1f MB)", path.name, file_size / 1e6)

        headers = {"xi-api-key": self._api_key}

        # Detect MIME type for the upload
        suffix = path.suffix.lower()
        mime_map = {
            ".mp4": "video/mp4", ".mov": "video/quicktime",
            ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
            ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".flac": "audio/flac", ".ogg": "audio/ogg",
        }
        mime = mime_map.get(suffix, "application/octet-stream")

        data: dict[str, Any] = {"model_id": model_id}
        if language:
            data["language_code"] = language

        with open(file_path, "rb") as f:
            files = {"file": (path.name, f, mime)}
            try:
                resp = requests.post(
                    _STT_URL,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300,  # 5-minute timeout for large files
                )
            except requests.exceptions.Timeout:
                raise RuntimeError("ElevenLabs request timed out after 5 minutes.")
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(f"Network error connecting to ElevenLabs: {e}")

        if resp.status_code == 401:
            raise RuntimeError(
                "ElevenLabs API key invalid or expired (HTTP 401).\n"
                "Check your key at elevenlabs.io."
            )
        if resp.status_code == 422:
            raise RuntimeError(
                f"ElevenLabs rejected the request (HTTP 422).\n"
                f"Response: {resp.text[:300]}"
            )
        if not resp.ok:
            raise RuntimeError(
                f"ElevenLabs API error (HTTP {resp.status_code}).\n"
                f"Response: {resp.text[:300]}"
            )

        body = resp.json()
        words_raw: list[dict] = body.get("words", [])

        if not words_raw:
            log.warning("ElevenLabs returned empty word list — checking 'text' fallback")
            text = body.get("text", "")
            if text:
                # Fall back to a single entry with no timing
                return [{"word": text, "start_sec": 0.0, "end_sec": 0.0, "type": "word"}]
            raise RuntimeError("ElevenLabs returned no words in the transcript.")

        log.info("Received %d word entries from ElevenLabs", len(words_raw))

        result = []
        for w in words_raw:
            result.append({
                "word": w.get("text", ""),
                "start_sec": float(w.get("start", 0.0)),
                "end_sec": float(w.get("end", 0.0)),
                "type": w.get("type", "word"),
            })

        return result
