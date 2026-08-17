"""Google Gemini provider (https://ai.google.dev).

Supports multiple API keys via GEMINI_API_KEYS (comma-separated) for key
rotation. When one key hits the rate limit (429) or is rejected, the provider
automatically moves to the next key in the pool - the same pattern used by
the Serper/Exa/Groq providers. Gemini's per-key free tier is already larger
than Groq's, so pooling a few keys here goes a long way.

Configuration:
    Single key:   GEMINI_API_KEY=abc123
    Multi-key:    GEMINI_API_KEYS=abc123,def456,ghi789   (takes priority)
"""
from __future__ import annotations

import itertools
import logging
import threading

import httpx

from app.config import settings
from app.providers.llm.base import LLMError, LLMProvider, LLMResponse

log = logging.getLogger(__name__)

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Thread-safe round-robin key rotator shared across all provider instances.
_lock = threading.Lock()
_key_cycle: itertools.cycle | None = None
_all_keys: list[str] = []


def _build_key_pool() -> list[str]:
    """Collect all configured Gemini keys (deduped, non-empty)."""
    keys: list[str] = []
    # Multi-key env var takes priority
    multi = getattr(settings, "gemini_api_keys", "") or ""
    for k in multi.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    # Fall back to single key
    single = settings.gemini_api_key or ""
    if single and single not in keys:
        keys.append(single)
    return keys


def _get_next_key() -> str | None:
    """Return the next key in the round-robin rotation."""
    global _key_cycle, _all_keys
    with _lock:
        if _key_cycle is None:
            _all_keys = _build_key_pool()
            if not _all_keys:
                return None
            _key_cycle = itertools.cycle(_all_keys)
        return next(_key_cycle)


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, api_key: str | None = None):
        # If explicitly passed an api_key, use it (e.g. in tests).
        # Otherwise pull from the rotating pool.
        self._fixed_key = api_key

    @property
    def configured(self) -> bool:
        pool = _build_key_pool()
        return bool(pool or self._fixed_key)

    def complete(self, *, system: str, user: str, model: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None,
                 json_mode: bool = False) -> LLMResponse:
        """Try every key in the pool until one works or all fail."""
        pool = _build_key_pool() if not self._fixed_key else [self._fixed_key]
        if not pool:
            raise LLMError("No GEMINI_API_KEY configured")

        model = model or (settings.ai_model if settings.ai_provider == "gemini"
                          else self.default_model)
        gen_config = {
            "temperature": settings.ai_temperature if temperature is None else temperature,
            "maxOutputTokens": max_tokens or settings.ai_max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen_config,
        }
        url = f"{_BASE}/{model}:generateContent"

        last_error: Exception | None = None
        tried: set[str] = set()

        # Try keys in round-robin order, but try each key at most once.
        for _ in range(len(pool)):
            key = _get_next_key() if not self._fixed_key else self._fixed_key
            if key in tried:
                continue
            tried.add(key)
            try:
                with httpx.Client(timeout=settings.ai_timeout) as client:
                    resp = client.post(url, json=payload,
                                       headers={"x-goog-api-key": key})
                if resp.status_code in (401, 403):
                    log.warning("Gemini key ...%s rejected (%d), trying next key",
                                key[-6:], resp.status_code)
                    last_error = LLMError(f"Key ...{key[-6:]} rejected ({resp.status_code})")
                    continue
                if resp.status_code == 429:
                    log.warning("Gemini key ...%s rate-limited (429), trying next key", key[-6:])
                    last_error = LLMError(f"Key ...{key[-6:]} rate limited (429)")
                    continue
                if resp.status_code >= 400:
                    last_error = LLMError(f"Gemini {resp.status_code}: {resp.text[:400]}")
                    continue
                data = resp.json()
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("Gemini key ...%s error: %s", key[-6:], exc)
                continue

            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as exc:
                last_error = LLMError(f"Unexpected Gemini response shape: {data}")
                log.warning("Gemini key ...%s returned unexpected shape: %s", key[-6:], exc)
                continue

            usage = data.get("usageMetadata") or {}
            return LLMResponse(
                text=text, model=model, provider=self.name,
                tokens_in=usage.get("promptTokenCount", 0),
                tokens_out=usage.get("candidatesTokenCount", 0),
            )

        raise LLMError(f"All {len(pool)} Gemini key(s) failed. Last error: {last_error}")
