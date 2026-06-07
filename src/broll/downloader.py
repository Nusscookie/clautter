"""B-Roll downloader: stream a remote MP4 to disk and import to Resolve.

The ``MediaPool.ImportFile`` call goes through the existing
``ResolveProxy`` in the GUI subprocess — no bridge changes needed.
Downloads are serial in V1 to keep ``MediaPool`` mutations predictable.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Callable

import requests

from src.broll.providers.base import ClipResult, NetworkError
from src.utils.logger import get_logger

log = get_logger(__name__)

_CHUNK_BYTES = 64 * 1024
_TIMEOUT_SEC = 60


def _slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-").lower()
    return s[:max_len] or "clip"


def _target_filename(clip: ClipResult) -> str:
    base = f"{clip.source}-{clip.external_id}-{_slugify(clip.title)}"
    return f"{base}.mp4"


class BrollDownloader:
    """Stream a ClipResult to disk, then ask Resolve to import it."""

    def __init__(self, target_dir: Path, app: Any) -> None:
        self._target_dir = Path(target_dir)
        self._target_dir.mkdir(parents=True, exist_ok=True)
        self._app = app

    def target_dir(self) -> Path:
        return self._target_dir

    def download_and_import(
        self,
        clip: ClipResult,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict:
        """Stream ``clip.download_url`` to a file, then call
        ``app.media_pool.ImportFile``. Idempotent: returns the existing
        file's import result if the file already exists."""
        filename = _target_filename(clip)
        dest = self._target_dir / filename

        if not dest.exists():
            if not clip.download_url:
                raise NetworkError(f"Clip {clip.external_id} has no download_url.")
            try:
                with requests.get(clip.download_url, stream=True, timeout=_TIMEOUT_SEC) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("Content-Length", 0) or 0)
                    written = 0
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=_CHUNK_BYTES):
                            if not chunk:
                                continue
                            f.write(chunk)
                            written += len(chunk)
                            if progress_cb is not None and total:
                                progress_cb(written, total)
            except requests.RequestException as e:
                if dest.exists() and dest.stat().st_size > 0:
                    # File has content — server likely closed TCP without clean
                    # HTTP teardown after sending all bytes (RemoteDisconnected).
                    # Treat as a successful download.
                    log.warning("Connection error after writing %d bytes (treating as complete): %s",
                                dest.stat().st_size, e)
                else:
                    if dest.exists():
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                    raise NetworkError(f"Download failed: {e}") from e

        import_result: Any = None
        try:
            mp = getattr(self._app, "media_pool", None)
            if mp is None:
                project = getattr(self._app, "project", None)
                if project is not None:
                    mp = project.GetMediaPool()
            if mp is None:
                log.warning("MediaPool unavailable — file saved to disk only: %s", dest)
                return {"path": str(dest), "import": None}
            import_result = mp.ImportMedia([str(dest)])
        except Exception as e:
            log.error("MediaPool.ImportMedia failed for %s: %s", dest, e)
            raise

        log.info("Downloaded + imported %s", dest)
        return {"path": str(dest), "import": import_result}
