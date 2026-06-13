"""Provider-specific HTTP callers for the LLM B-roll director.

Each function takes a prompt + key + model + sampling params and returns the
raw text reply. Extracted from llm_director.py so the decision/prompt logic
stays separate from the per-provider request boilerplate. Add a new provider
here and wire it into ``llm_director._dispatch_call`` / ``direct``.
"""

from __future__ import annotations

from src.utils.logger import get_logger

log = get_logger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_TIMEOUT = 90

_JSON_SYSTEM_PROMPT = (
    "You are an expert video editor. Respond with ONLY valid JSON arrays — "
    "no explanations, no markdown, no prose."
)


def call_openai(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_gemini(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    url = _GEMINI_URL.replace("gemini-2.0-flash", model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    resp = requests.post(
        f"{url}?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_minimax(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _JSON_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(
        _MINIMAX_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise ValueError(f"Minimax returned empty content (finish_reason={finish!r})")
    return content


def call_nvidia(prompt: str, api_key: str, model: str, max_tokens: int, temperature: float) -> str:
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _JSON_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Many NVIDIA-hosted models are reasoning models; suppress <think> blocks
        # so the reply is clean JSON. Ignored by non-reasoning models.
        "chat_template_kwargs": {"thinking": False},
    }
    resp = requests.post(
        _NVIDIA_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        finish = data["choices"][0].get("finish_reason", "unknown")
        raise ValueError(f"NVIDIA returned empty content (finish_reason={finish!r})")
    return content
