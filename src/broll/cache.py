"""On-disk JSON cache for B-Roll search results.

Honours Pixabay's ToS requirement to cache results for 24h. Pexels doesn't
require it but cheap to share. Cache lives at ``~/.clutter/broll_cache/``
as one JSON file per query.
"""

from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

from src.broll.providers.base import ClipResult
from src.constants import PATHS
from src.utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_TTL_SEC = 24 * 60 * 60


class BrollCache:
    """24h JSON cache keyed by (provider, query, per_page)."""

    def __init__(self, root: Path | None = None, ttl_sec: int = _DEFAULT_TTL_SEC) -> None:
        self._root = root or PATHS.BROLL_CACHE
        self._ttl = ttl_sec
        self._root.mkdir(parents=True, exist_ok=True)

    def _key(self, provider: str, query: str, per_page: int) -> str:
        raw = f"{provider.lower()}:{query.strip().lower()}:{per_page}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _path_for(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def get(self, provider: str, query: str, per_page: int) -> list[ClipResult] | None:
        path = self._path_for(self._key(provider, query, per_page))
        if not path.exists():
            return None
        try:
            age = time.time() - path.stat().st_mtime
            if age > self._ttl:
                log.debug("Cache miss (expired) %s", path.name)
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return [ClipResult.from_dict(d) for d in data]
        except Exception as e:
            log.warning("BrollCache read failed for %s: %s", path.name, e)
            return None

    def put(self, provider: str, query: str, per_page: int, results: list[ClipResult]) -> None:
        path = self._path_for(self._key(provider, query, per_page))
        try:
            payload = [r.to_dict() for r in results]
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("BrollCache write failed for %s: %s", path.name, e)

    def clear(self) -> None:
        for p in self._root.glob("*.json"):
            try:
                p.unlink()
            except Exception as e:
                log.warning("BrollCache clear failed for %s: %s", p.name, e)
