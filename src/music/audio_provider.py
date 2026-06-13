"""Audio API clients — Freesound (SFX) and Jamendo (music).

Freesound:  GET https://freesound.org/apiv2/search/text/?token=KEY&query=TERM
Jamendo:    GET https://api.jamendo.com/v3.0/tracks/?client_id=ID&namesearch=TERM

``previewURL`` on Freesound results is a 30s MP3 preview (full for short SFX).
Jamendo ``audio`` field is a full MP3 stream URL.
"""

from __future__ import annotations
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

from src.broll.providers.base import AuthError, NetworkError, RateLimitError
from src.constants import PATHS
from src.utils.logger import get_logger

log = get_logger(__name__)

_FREESOUND_SEARCH  = "https://freesound.org/apiv2/search/text/"
_JAMENDO_TRACKS    = "https://api.jamendo.com/v3.0/tracks/"
_TIMEOUT_SEC       = 15
_DEFAULT_TTL       = 24 * 60 * 60   # 24 h


@dataclass
class AudioResult:
    """A single audio clip normalised from any audio API."""

    source: str           # "freesound" | "jamendo"
    external_id: str
    title: str
    page_url: str
    duration_sec: int
    download_url: str     # direct MP3 URL
    tags: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class _AudioCache:
    """24h JSON cache for audio search results."""

    def __init__(self, root: Path | None = None, ttl_sec: int = _DEFAULT_TTL) -> None:
        self._root = root or PATHS.AUDIO_CACHE
        self._ttl  = ttl_sec
        self._root.mkdir(parents=True, exist_ok=True)

    def _key(self, provider: str, query: str, per_page: int) -> str:
        raw = f"{provider.lower()}:{query.strip().lower()}:{per_page}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _path_for(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def get(self, provider: str, query: str, per_page: int) -> list[AudioResult] | None:
        path = self._path_for(self._key(provider, query, per_page))
        if not path.exists():
            return None
        try:
            if time.time() - path.stat().st_mtime > self._ttl:
                log.debug("[audio_cache] expired: %s", path.name)
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return [AudioResult.from_dict(d) for d in data]
        except Exception as e:
            log.warning("[audio_cache] read failed %s: %s", path.name, e)
            return None

    def put(self, provider: str, query: str, per_page: int, results: list[AudioResult]) -> None:
        path = self._path_for(self._key(provider, query, per_page))
        try:
            path.write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("[audio_cache] write failed %s: %s", path.name, e)


_shared_cache = _AudioCache()


class FreesoundClient:
    """Search Freesound for short sound effects.

    Requires a Freesound API key (free account at freesound.org).
    """

    name = "freesound"

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache: _AudioCache | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AuthError("Freesound API key is empty.")
        self._api_key = api_key.strip()
        self._session = session or requests.Session()
        self._cache   = cache or _shared_cache

    def search_sfx(self, query: str, per_page: int = 5) -> list[AudioResult]:
        """Search Freesound for SFX. Returns up to per_page AudioResult items."""
        query = (query or "").strip()
        if not query:
            return []

        cached = self._cache.get(self.name, query, per_page)
        if cached is not None:
            log.debug("[audio_provider] freesound cache hit %r", query)
            return cached

        params: dict[str, Any] = {
            "token":    self._api_key,
            "query":    query,
            "fields":   "id,name,previews,duration,tags,url",
            "filter":   "duration:[0.5 TO 30]",
            "page_size": max(1, min(per_page, 15)),
            "sort":     "score",
        }

        try:
            resp = self._session.get(_FREESOUND_SEARCH, params=params, timeout=_TIMEOUT_SEC)
        except requests.RequestException as e:
            raise NetworkError(f"Freesound request failed: {e}") from e

        if resp.status_code == 429:
            raise RateLimitError("Freesound rate limit exceeded.", retry_after=60)
        if resp.status_code in (401, 403):
            raise AuthError("Freesound rejected the API key.")
        if not resp.ok:
            raise NetworkError(f"Freesound returned HTTP {resp.status_code}.")

        try:
            data = resp.json()
        except ValueError as e:
            raise NetworkError(f"Freesound returned non-JSON: {e}") from e

        results = [self._normalise(hit) for hit in (data.get("results") or []) if hit]
        # Filter out results with no usable download URL
        results = [r for r in results if r.download_url]

        self._cache.put(self.name, query, per_page, results)
        log.info("[audio_provider] freesound: %d hit(s) for %r", len(results), query)
        return results

    @staticmethod
    def _normalise(hit: dict) -> AudioResult:
        previews = hit.get("previews") or {}
        url = (
            previews.get("preview-hq-mp3")
            or previews.get("preview-lq-mp3")
            or ""
        )
        tags_list = hit.get("tags") or []
        tags = ", ".join(tags_list[:10]) if isinstance(tags_list, list) else str(tags_list)
        return AudioResult(
            source="freesound",
            external_id=str(hit.get("id", "")),
            title=hit.get("name", f"Freesound #{hit.get('id', '?')}"),
            page_url=hit.get("url", ""),
            duration_sec=int(float(hit.get("duration", 0) or 0)),
            download_url=url,
            tags=tags,
        )


class JamendoClient:
    """Search Jamendo for royalty-free background music.

    Requires a Jamendo client_id (free app registration at devportal.jamendo.com).
    """

    name = "jamendo"

    def __init__(
        self,
        client_id: str,
        *,
        session: requests.Session | None = None,
        cache: _AudioCache | None = None,
    ) -> None:
        if not client_id or not client_id.strip():
            raise AuthError("Jamendo client_id is empty.")
        self._client_id = client_id.strip()
        self._session   = session or requests.Session()
        self._cache     = cache or _shared_cache

    def search_music(self, query: str, per_page: int = 5) -> list[AudioResult]:
        """Search Jamendo for background music tracks."""
        query = (query or "").strip()
        if not query:
            return []

        cached = self._cache.get(self.name, query, per_page)
        if cached is not None:
            log.debug("[audio_provider] jamendo cache hit %r", query)
            return cached

        params: dict[str, Any] = {
            "client_id":   self._client_id,
            "format":      "json",
            "limit":       max(1, min(per_page, 20)),
            "namesearch":  query,
            "audioformat": "mp32",
            "order":       "downloads_total",
            "include":     "musicinfo",
        }

        try:
            resp = self._session.get(_JAMENDO_TRACKS, params=params, timeout=_TIMEOUT_SEC)
        except requests.RequestException as e:
            raise NetworkError(f"Jamendo request failed: {e}") from e

        if resp.status_code == 429:
            raise RateLimitError("Jamendo rate limit exceeded.", retry_after=60)
        if resp.status_code in (401, 403):
            raise AuthError("Jamendo rejected the client_id.")
        if not resp.ok:
            raise NetworkError(f"Jamendo returned HTTP {resp.status_code}.")

        try:
            data = resp.json()
        except ValueError as e:
            raise NetworkError(f"Jamendo returned non-JSON: {e}") from e

        results = [self._normalise(track) for track in (data.get("results") or []) if track]
        results = [r for r in results if r.download_url]

        self._cache.put(self.name, query, per_page, results)
        log.info("[audio_provider] jamendo: %d hit(s) for %r", len(results), query)
        return results

    @staticmethod
    def _normalise(track: dict) -> AudioResult:
        tags_list = (track.get("musicinfo") or {}).get("tags", {})
        if isinstance(tags_list, dict):
            all_tags: list[str] = []
            for v in tags_list.values():
                if isinstance(v, list):
                    all_tags.extend(v)
            tags = ", ".join(all_tags[:10])
        else:
            tags = ""
        return AudioResult(
            source="jamendo",
            external_id=str(track.get("id", "")),
            title=track.get("name", f"Jamendo #{track.get('id', '?')}"),
            page_url=track.get("shareurl", ""),
            duration_sec=int(track.get("duration", 0) or 0),
            download_url=track.get("audio", ""),
            tags=tags,
            extra={"artist": track.get("artist_name", ""), "album": track.get("album_name", "")},
        )
