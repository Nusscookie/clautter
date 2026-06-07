"""Provider interface and common types for B-Roll search.

Both Pixabay and Pexels return very different JSON shapes; this module
defines the normalised result type and a Protocol that every provider
(real or mock) implements. Errors are translated into a small exception
hierarchy so the UI worker can show user-friendly messages.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Protocol


@dataclass
class ClipResult:
    """A single stock video, normalised across providers."""

    source: str            # "pixabay" | "pexels" | "mock"
    external_id: str
    title: str
    page_url: str
    duration_sec: int
    width: int
    height: int
    download_url: str
    thumbnail_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClipResult":
        return cls(**data)


class BrollProvider(Protocol):
    """Common interface for stock-footage search providers."""

    name: str

    def search(self, query: str, per_page: int = 15) -> list[ClipResult]:
        """Return up to ``per_page`` results for the given query."""
        ...

    def best_download_url(self, hit: ClipResult, prefer_width: int = 1920) -> str:
        """Pick the best rendition for ``hit``. Most providers fill this in
        at search time; this is here for parity / future use."""
        ...


# ──────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────

class BrollProviderError(Exception):
    """Base class for all provider-level errors."""


class AuthError(BrollProviderError):
    """API key missing, malformed, or rejected (401/403)."""


class RateLimitError(BrollProviderError):
    """Provider returned 429. Carries optional retry-after seconds."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(BrollProviderError):
    """Connection failure, timeout, DNS error, etc."""


class EmptyResultsError(BrollProviderError):
    """Provider returned 200 with no hits for the query."""
