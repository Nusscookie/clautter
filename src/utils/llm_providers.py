"""Shared cloud-LLM provider selection.

All three LLM call sites (B-roll director, B-roll reranker, music mood analyzer)
support the same set of providers and the same "use a key if present" logic.
This module centralizes that so the call sites don't each duplicate the priority
chain, and so the B-roll provider-picker UI and the call sites agree on names.

Each provider maps to a ``<name>_api_key`` setting; ``NVIDIA`` is OpenAI-compatible
(same request/response shape, different endpoint).
"""

from __future__ import annotations
from typing import Any

# Priority order — first available wins when no explicit preference is given.
PROVIDERS: list[str] = ["OpenAI", "Gemini", "Minimax", "NVIDIA", "Anthropic"]

_KEY_FOR: dict[str, str] = {
    "OpenAI": "openai_api_key",
    "Gemini": "gemini_api_key",
    "Minimax": "minimax_api_key",
    "NVIDIA": "nvidia_api_key",
    "Anthropic": "anthropic_api_key",
}


def api_key_for(settings: Any, provider: str) -> str:
    """Return the (stripped) API key configured for *provider*, or ""."""
    key_name = _KEY_FOR.get(provider, "")
    if not key_name:
        return ""
    return (settings.get(key_name, "") or "").strip()


def available_providers(settings: Any) -> list[str]:
    """Providers (in priority order) that currently have a non-empty API key."""
    return [p for p in PROVIDERS if api_key_for(settings, p)]


def resolve_provider(settings: Any, preferred: str | None = None) -> str | None:
    """Pick which provider to call.

    If *preferred* is given and has a key, use it. Otherwise fall back to the
    first available provider (preserves the legacy priority chain). Returns
    ``None`` when no provider has a key.
    """
    if preferred and api_key_for(settings, preferred):
        return preferred
    avail = available_providers(settings)
    return avail[0] if avail else None
