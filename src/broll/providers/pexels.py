"""Pexels video search provider.

Endpoint: GET https://api.pexels.com/v1/videos/search?query=TERM&per_page=N&page=1
Auth:     ``Authorization: KEY`` header.
Rate limit: 200 req / hour, 20k / month.

Response shape (truncated):
    {
      "page": 1, "per_page": 15, "total_results": 20475,
      "videos": [
        {
          "id": 1448735,
          "width": 4096, "height": 2160,
          "url": "https://www.pexels.com/video/...",
          "image": "https://static-videos.pexels.com/.../preview.jpg",
          "duration": 15,
          "user": { "id": 319098, "name": "Daria", "url": "..." },
          "video_files": [
            { "id": 58650, "quality": "hd", "width": 2048, "height": 1080,
              "fps": 30, "link": "https://player.vimeo.com/external/.../...mp4" }
          ]
        }
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

_ENDPOINT = "https://api.pexels.com/v1/videos/search"
_TIMEOUT_SEC = 15


class PexelsClient:
    name = "pexels"
    _prefer_width = 1920

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache: BrollCache | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AuthError("Pexels API key is empty.")
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
                log.debug("Pexels cache hit for %r", query)
                return cached

        headers = {"Authorization": self._api_key}
        params = {
            "query": query,
            "per_page": max(1, min(per_page, 80)),
            "page": 1,
        }

        try:
            resp = self._session.get(_ENDPOINT, headers=headers, params=params, timeout=_TIMEOUT_SEC)
        except requests.RequestException as e:
            raise NetworkError(f"Pexels request failed: {e}") from e

        if resp.status_code == 429:
            retry = int(resp.headers.get("X-Ratelimit-Reset", "60") or 60)
            raise RateLimitError("Pexels rate limit exceeded.", retry_after=retry)
        if resp.status_code in (401, 403):
            raise AuthError("Pexels rejected the API key.")
        if not resp.ok:
            raise NetworkError(f"Pexels returned HTTP {resp.status_code}.")

        try:
            data = resp.json()
        except ValueError as e:
            raise NetworkError(f"Pexels returned non-JSON: {e}") from e

        videos = data.get("videos") or []
        results = [self._normalise(v, self._prefer_width) for v in videos if v]

        if self._cache is not None:
            self._cache.put(self.name, query, per_page, results)

        log.info("Pexels: %d hit(s) for %r", len(results), query)
        return results

    def best_download_url(self, hit: ClipResult, prefer_width: int = 1920) -> str:
        return hit.download_url

    @staticmethod
    def _normalise(video: dict, prefer_width: int = 1920) -> ClipResult:
        files = video.get("video_files") or []
        chosen: dict | None = None
        best_delta = None
        for f in files:
            if not f.get("link"):
                continue
            w = int(f.get("width", 0) or 0)
            delta = abs(w - prefer_width) if w else 10**9
            if best_delta is None or delta < best_delta:
                best_delta = delta
                chosen = f
        # Fallback: first file with a link
        if chosen is None:
            for f in files:
                if f.get("link"):
                    chosen = f
                    break

        user = video.get("user") or {}
        title = user.get("name") or f"Pexels #{video.get('id', '?')}"

        return ClipResult(
            source="pexels",
            external_id=str(video.get("id", "")),
            title=title,
            page_url=video.get("url", ""),
            duration_sec=int(video.get("duration", 0) or 0),
            width=int((chosen or {}).get("width", 0) or 0),
            height=int((chosen or {}).get("height", 0) or 0),
            download_url=(chosen or {}).get("link", ""),
            thumbnail_url=video.get("image", ""),
            extra={"user_url": user.get("url", "")},
        )
