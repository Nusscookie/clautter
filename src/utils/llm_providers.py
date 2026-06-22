"""Shared cloud-LLM provider selection + a single call function.

All three LLM call sites (B-roll director, B-roll reranker, music mood
analyzer) support the same set of providers and the same "use a key if
present" logic. This module is the single source of truth for:

  * which providers exist and in what priority order (``PROVIDERS``),
  * how each maps to an API-key / model setting (``_SPECS``),
  * how to build the request and read the reply for each (``ProviderSpec``),
  * one ``call_llm`` that every call site uses instead of its own HTTP code,
  * one tolerant ``extract_json_array`` parser for JSON-array replies.

Adding a provider = one ``_SPECS`` entry + one settings field + one UI row.
Each provider maps to a ``<name>_api_key`` setting; ``NVIDIA`` is
OpenAI-compatible (same request/response shape, different endpoint).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)

# Priority order — first available wins when no explicit preference is given.
PROVIDERS: list[str] = ["OpenAI", "Gemini", "Minimax", "NVIDIA", "Ollama", "Anthropic"]

_TIMEOUT = 90
_ANTHROPIC_VERSION = "2023-06-01"

# Default system prompt for the JSON-producing call sites. Pass system=None to
# omit it (e.g. the reranker, which just wants a single number back).
_JSON_SYSTEM_PROMPT = (
    "You are an expert video editor. Respond with ONLY valid JSON arrays — "
    "no explanations, no markdown, no prose."
)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OLLAMA_DEFAULT_URL = "http://localhost:11434/v1/chat/completions"


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

# A request builder returns (url, headers, json_payload). An extractor reads
# the reply text out of the parsed response JSON.
Builder = Callable[[str, str, str, int, float, str | None], "tuple[str, dict, dict]"]
Extractor = Callable[[dict], str]


@dataclass(frozen=True)
class ProviderSpec:
    """Everything that differs between one cloud LLM and another."""
    name: str
    key_setting: str        # e.g. "openai_api_key"
    model_setting: str      # e.g. "llm_openai_model"
    default_model: str      # "" = required (NVIDIA), guarded by the caller
    build: Builder
    extract: Extractor


def _openai_compatible_url(url: str, *, system_role: bool, nvidia: bool = False) -> Builder:
    """Builder factory for the OpenAI chat-completions shape (OpenAI/Minimax/NVIDIA)."""
    def build(prompt, api_key, model, max_tokens, temperature, system):
        messages = []
        if system and system_role:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if nvidia:
            # Many NVIDIA-hosted models are reasoning models; suppress <think>
            # blocks so the reply is clean. Ignored by non-reasoning models.
            payload["chat_template_kwargs"] = {"thinking": False}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        return url, headers, payload
    return build


def _build_gemini(prompt, api_key, model, max_tokens, temperature, system):
    url = _GEMINI_URL.format(model=model) + f"?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    return url, {"Content-Type": "application/json"}, payload


def _build_anthropic(prompt, api_key, model, max_tokens, temperature, system):
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    return _ANTHROPIC_URL, headers, payload


def _extract_openai(data: dict) -> str:
    return data["choices"][0]["message"]["content"]


def _extract_gemini(data: dict) -> str:
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _extract_anthropic(data: dict) -> str:
    return data["content"][0]["text"]


_SPECS: dict[str, ProviderSpec] = {
    "OpenAI": ProviderSpec(
        "OpenAI", "openai_api_key", "llm_openai_model", "gpt-4o-mini",
        _openai_compatible_url(_OPENAI_URL, system_role=False), _extract_openai,
    ),
    "Gemini": ProviderSpec(
        "Gemini", "gemini_api_key", "llm_gemini_model", "gemini-2.0-flash",
        _build_gemini, _extract_gemini,
    ),
    "Minimax": ProviderSpec(
        "Minimax", "minimax_api_key", "llm_minimax_model", "MiniMax-Text-01",
        _openai_compatible_url(_MINIMAX_URL, system_role=True), _extract_openai,
    ),
    "NVIDIA": ProviderSpec(
        "NVIDIA", "nvidia_api_key", "llm_nvidia_model", "",
        _openai_compatible_url(_NVIDIA_URL, system_role=True, nvidia=True), _extract_openai,
    ),
    "Ollama": ProviderSpec(
        "Ollama", "ollama_base_url", "llm_ollama_model", "",
        _openai_compatible_url(_OLLAMA_DEFAULT_URL, system_role=True), _extract_openai,
    ),
    "Anthropic": ProviderSpec(
        "Anthropic", "anthropic_api_key", "llm_anthropic_model", "claude-sonnet-4-6",
        _build_anthropic, _extract_anthropic,
    ),
}


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def api_key_for(settings: Any, provider: str) -> str:
    """Return the (stripped) API key configured for *provider*, or ""."""
    spec = _SPECS.get(provider)
    if not spec:
        return ""
    return (settings.get(spec.key_setting, "") or "").strip()


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


def model_for(settings: Any, provider: str) -> str:
    """Configured model id for *provider*, or its default (may be "")."""
    spec = _SPECS[provider]
    return str(settings.get(spec.model_setting, spec.default_model) or spec.default_model).strip()


# ---------------------------------------------------------------------------
# The one call function
# ---------------------------------------------------------------------------

def call_llm(
    provider: str,
    prompt: str,
    settings: Any,
    *,
    max_tokens: int,
    temperature: float,
    system: str | None = _JSON_SYSTEM_PROMPT,
    model: str | None = None,
) -> str:
    """Send *prompt* to *provider* and return the raw text reply.

    Reads the API key and (unless *model* is given) the model id from
    *settings* via the provider spec. Raises on HTTP error or empty reply so
    callers can degrade with one ``except``.
    """
    import requests

    spec = _SPECS[provider]
    api_key = api_key_for(settings, provider)
    model = model or model_for(settings, provider)
    url, headers, payload = spec.build(prompt, api_key, model, max_tokens, temperature, system)

    # Ollama: key_setting stores the base URL; resolve the actual endpoint from it.
    if provider == "Ollama":
        url = f"{api_key.rstrip('/')}/v1/chat/completions"

    resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    text = spec.extract(resp.json())
    if not text or not text.strip():
        raise ValueError(f"{provider} returned empty content")
    return text


# ---------------------------------------------------------------------------
# JSON-array parsing (shared by all JSON-producing call sites)
# ---------------------------------------------------------------------------

def extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from an LLM reply.

    Tolerates markdown fences, ``<think>`` blocks, and trailing prose. If the
    array isn't found outside a ``<think>`` block, searches inside it (some
    reasoning models emit the answer there at temperature 0).
    """
    original = text.strip()

    stripped = re.sub(r"<think>.*?</think>", "", original, flags=re.DOTALL).strip()
    stripped = re.sub(r"```(?:json)?", "", stripped).strip()

    think_match = re.search(r"<think>(.*?)</think>", original, flags=re.DOTALL)
    candidates = [stripped]
    if think_match:
        inner = re.sub(r"```(?:json)?", "", think_match.group(1)).strip()
        candidates.append(inner)

    for candidate in candidates:
        start = candidate.find("[")
        if start == -1:
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(candidate, start)
            if isinstance(obj, list):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    log.warning("[llm_providers] no JSON array in reply: %r", original[:500])
    raise ValueError(f"no JSON array found in LLM response (first 200 chars): {original[:200]!r}")
