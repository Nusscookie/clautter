"""Quick test: verify cloud LLM API keys work for B-roll director mode.

Usage:
    py -3.12 test_llm_key.py

Reads keys from ~/.clutter/config.json (same as the app).
Tests each configured key with a minimal prompt and prints the result.
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".clutter" / "config.json"

OPENAI_URL  = "https://api.openai.com/v1/chat/completions"
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"

TEST_PROMPT = (
    'Reply with this JSON exactly, nothing else: '
    '[{"clip_name":"test.mp4","timeline_sec":1.0,"clip_start_sec":0.0,"clip_end_sec":5.0}]'
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[WARN] Config not found at {CONFIG_PATH}  — no keys to test.")
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Could not read config: {e}")
        return {}


def test_openai(key: str) -> None:
    import requests
    print(f"\n--- OpenAI (key: {key[:8]}…) ---")
    try:
        resp = requests.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_tokens": 80, "temperature": 0},
            timeout=20,
        )
        print(f"  HTTP {resp.status_code}")
        if resp.ok:
            content = resp.json()["choices"][0]["message"]["content"]
            print(f"  Reply: {content[:200]}")
            print("  ✅ OpenAI key works")
        else:
            print(f"  ❌ Error: {resp.text[:300]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")


def test_gemini(key: str) -> None:
    import requests
    print(f"\n--- Gemini (key: {key[:8]}…) ---")
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": TEST_PROMPT}]}]},
            timeout=20,
        )
        print(f"  HTTP {resp.status_code}")
        if resp.ok:
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"  Reply: {content[:200]}")
            print("  ✅ Gemini key works")
        else:
            print(f"  ❌ Error: {resp.text[:300]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")


def test_minimax(key: str) -> None:
    import requests
    print(f"\n--- Minimax (key: {key[:8]}…) ---")
    try:
        resp = requests.post(
            MINIMAX_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "MiniMax-M2.5",
                  "messages": [{"role": "user", "content": TEST_PROMPT}],
                  "max_completion_tokens": 80, "temperature": 0},
            timeout=20,
        )
        print(f"  HTTP {resp.status_code}")
        if resp.ok:
            content = resp.json()["choices"][0]["message"]["content"]
            print(f"  Reply: {content[:200]}")
            print("  ✅ Minimax key works")
        else:
            print(f"  ❌ Error: {resp.text[:300]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")


def main() -> None:
    cfg = load_config()
    tested = 0

    openai_key = (cfg.get("openai_api_key") or "").strip()
    gemini_key = (cfg.get("gemini_api_key") or "").strip()
    minimax_key = (cfg.get("minimax_api_key") or "").strip()

    if openai_key:
        test_openai(openai_key)
        tested += 1
    else:
        print("\n[SKIP] No openai_api_key in config.")

    if gemini_key:
        test_gemini(gemini_key)
        tested += 1
    else:
        print("[SKIP] No gemini_api_key in config.")

    if minimax_key:
        test_minimax(minimax_key)
        tested += 1
    else:
        print("[SKIP] No minimax_api_key in config.")

    if tested == 0:
        print("\nNo API keys found. Add them in the app Settings (⚙ top-right).")
        print(f"Config location: {CONFIG_PATH}")
        sys.exit(1)


if __name__ == "__main__":
    main()
