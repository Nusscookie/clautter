"""Offline mock provider for development and end-to-end testing.

Returns canned ``ClipResult``s without any network access. Activated by
``broll_use_mock=True`` in settings (hidden in the UI; edit config.json
manually or set it in a debug REPL).
"""

from __future__ import annotations

from src.broll.providers.base import BrollProvider, ClipResult


_CANNED: list[ClipResult] = [
    ClipResult(
        source="mock",
        external_id="mock-001",
        title="Sunrise over mountain peaks",
        page_url="https://example.com/mock/001",
        duration_sec=12,
        width=1920,
        height=1080,
        download_url="https://example.com/mock/001.mp4",
    ),
    ClipResult(
        source="mock",
        external_id="mock-002",
        title="City traffic time-lapse",
        page_url="https://example.com/mock/002",
        duration_sec=8,
        width=1920,
        height=1080,
        download_url="https://example.com/mock/002.mp4",
    ),
    ClipResult(
        source="mock",
        external_id="mock-003",
        title="Person typing on a laptop keyboard",
        page_url="https://example.com/mock/003",
        duration_sec=15,
        width=1920,
        height=1080,
        download_url="https://example.com/mock/003.mp4",
    ),
    ClipResult(
        source="mock",
        external_id="mock-004",
        title="Aerial drone shot of coastline",
        page_url="https://example.com/mock/004",
        duration_sec=20,
        width=3840,
        height=2160,
        download_url="https://example.com/mock/004.mp4",
    ),
    ClipResult(
        source="mock",
        external_id="mock-005",
        title="Coffee being poured into a cup",
        page_url="https://example.com/mock/005",
        duration_sec=6,
        width=1280,
        height=720,
        download_url="https://example.com/mock/005.mp4",
    ),
]


class MockClient:
    """Canned BrollProvider. No network. No API key."""

    name = "mock"

    def __init__(self, canned: list[ClipResult] | None = None) -> None:
        self._canned = list(canned) if canned is not None else list(_CANNED)

    def search(self, query: str, per_page: int = 15) -> list[ClipResult]:
        # Slight variation per query so the UI looks alive.
        offset = sum(ord(c) for c in query) % len(self._canned)
        rotated = self._canned[offset:] + self._canned[:offset]
        return [ClipResult(**c.to_dict()) for c in rotated[:per_page]]

    def best_download_url(self, hit: ClipResult, prefer_width: int = 1920) -> str:
        return hit.download_url
