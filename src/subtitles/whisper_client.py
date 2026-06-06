"""Local Whisper transcription via faster-whisper (CTranslate2 backend).

faster-whisper is ~4x faster than openai-whisper on CPU, requires no PyTorch,
and auto-downloads quantized models from HuggingFace on first use.

Install: pip install faster-whisper
"""

from __future__ import annotations
from typing import Any, Optional

from src.utils.logger import get_logger

log = get_logger(__name__)

_DEVICE_AUTO = "auto"
_COMPUTE_TYPE = "int8"


class WhisperClient:
    """Local speech-to-text via faster-whisper. Returns same format as ElevenLabsClient."""

    def __init__(self, model_name: str = "base") -> None:
        self._model_name = model_name
        self._model: Optional[Any] = None

    def transcribe(self, file_path: str, language: str = "") -> list[dict]:
        """Transcribe a media file using local Whisper.

        Args:
            file_path: Path to audio or video file (ffmpeg handles decoding).
            language:  BCP-47 code (e.g. "en", "de"). Empty = auto-detect.

        Returns:
            List of {word, start_sec, end_sec, type} dicts — same shape as ElevenLabsClient.

        Raises:
            RuntimeError if faster-whisper is not installed.
        """
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed.\n"
                "Run: pip install faster-whisper"
            )

        if self._model is None:
            log.info(
                "Loading Whisper model '%s' (first run downloads to HuggingFace cache)",
                self._model_name,
            )
            self._model = WhisperModel(
                self._model_name,
                device=_DEVICE_AUTO,
                compute_type=_COMPUTE_TYPE,
            )
            log.info("Whisper model '%s' loaded", self._model_name)

        kwargs: dict[str, Any] = {"word_timestamps": True}
        if language:
            kwargs["language"] = language

        log.info("Transcribing with Whisper '%s': %s", self._model_name, file_path)
        segments, info = self._model.transcribe(file_path, **kwargs)

        result: list[dict] = []
        for segment in segments:
            for word in (segment.words or []):
                text = word.word.strip()
                if not text:
                    continue
                result.append({
                    "word": text,
                    "start_sec": float(word.start),
                    "end_sec": float(word.end),
                    "type": "word",
                })

        log.info(
            "Whisper transcription complete: %d words, language=%s",
            len(result), info.language,
        )
        return result
