"""Pixabay video search provider.

Endpoint:  GET https://pixabay.com/api/videos/?key=KEY&q=TERM&per_page=N&page=1
Auth:      ``key`` query parameter.
Rate limit: 100 req / 60s.
24h cache: required by Pixabay ToS — handled by ``BrollCache``.

Response shape (truncated):
    {
      "totalHits": 42,
      "hits": [
        {
          "id": 125,
          "pageURL": "https://pixabay.com/videos/id-125/",
          "type": "film",
          "tags": "flowers, yellow, blossom",
          "duration": 12,
          "videos": {
            "large":  { "url": "...", "width": 1920, "height": 1080, ... },
            "medium": { "url": "...", "width": 1280, "height": 720,  ... },
            "small":  { ... }, "tiny": { ... }
          }
        }, ...
      ]
    }
"""

from __future__ import annotations
import requests

from src.broll.cache import BrollCache
from src.broll.providers.base import (
    AuthError, BrollProvider, ClipResult,
    NetworkError, RateLimitError,
)
from src.utils.logger import get_logger

log = get_logger(__name__)

_ENDPOINT = "https://pixabay.com/api/videos/"
_TIMEOUT_SEC = 15


class PixabayClient:
    name = "pixabay"
    _prefer_width = 1920

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache: BrollCache | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AuthError("Pixabay API key is empty.")
        self._api_key = api_key.strip()
        self._session = session or requests.Session()
        self._cache = cache

    def search(self, query: str, per_page: int = 15) -> list[ClipResult]:
        query = (query or "").strip()
        if not query:
            return []

        if self._cache is not None:
            cached = self._cache.get(self.name, query, per_page)
            if cached is not None:
                log.debug("Pixabay cache hit for %r", query)
                return cached

        params = {
            "key": self._api_key,
            "q": query,
            "per_page": max(3, min(per_page, 200)),
            "page": 1,
            "order": "popular",
            "video_type": "all",
            "safesearch": "true",
        }

        try:
            resp = self._session.get(_ENDPOINT, params=params, timeout=_TIMEOUT_SEC)
        except requests.RequestException as e:
            raise NetworkError(f"Pixabay request failed: {e}") from e

        if resp.status_code == 429:
            retry = int(resp.headers.get("X-RateLimit-Reset", "60") or 60)
            raise RateLimitError("Pixabay rate limit exceeded.", retry_after=retry)
        if resp.status_code in (401, 403):
            raise AuthError("Pixabay rejected the API key.")
        if not resp.ok:
            raise NetworkError(f"Pixabay returned HTTP {resp.status_code}.")

        try:
            data = resp.json()
        except ValueError as e:
            raise NetworkError(f"Pixabay returned non-JSON: {e}") from e

        hits = data.get("hits") or []
        results = [self._normalise(hit, self._prefer_width) for hit in hits if hit]

        if self._cache is not None:
            self._cache.put(self.name, query, per_page, results)

        log.info("Pixabay: %d hit(s) for %r", len(results), query)
        return results

    def best_download_url(self, hit: ClipResult, prefer_width: int = 1920) -> str:
        return hit.download_url

    @staticmethod
    def _normalise(hit: dict, prefer_width: int = 1920) -> ClipResult:
        videos = hit.get("videos") or {}
        # Prefer large (4K) if present and at least prefer_width; else medium.
        chosen: dict | None = None
        for variant in ("large", "medium", "small", "tiny"):
            v = videos.get(variant)
            if not v or not v.get("url"):
                continue
            if chosen is None:
                chosen = v
            if int(v.get("width", 0) or 0) >= prefer_width:
                chosen = v
                break
        if chosen is None:
            # Last resort: first variant with a URL
            for v in videos.values():
                if v and v.get("url"):
                    chosen = v
                    break

        tags = hit.get("tags", "")
        title = tags.split(",")[0].strip() if tags else f"Pixabay #{hit.get('id', '?')}"

        # Prefer tiny variant thumbnail; fall back to chosen variant's thumbnail.
        thumb = (
            (videos.get("tiny") or {}).get("thumbnail", "")
            or (chosen or {}).get("thumbnail", "")
        )

        return ClipResult(
            source="pixabay",
            external_id=str(hit.get("id", "")),
            title=title,
            page_url=hit.get("pageURL", ""),
            duration_sec=int(hit.get("duration", 0) or 0),
            width=int((chosen or {}).get("width", 0) or 0),
            height=int((chosen or {}).get("height", 0) or 0),
            download_url=(chosen or {}).get("url", ""),
            thumbnail_url=thumb,
            extra={"type": hit.get("type"), "tags": tags, "user": hit.get("user", "")},
        )
