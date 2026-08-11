from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.llm.base import LLMError, LLMProvider, LLMResponse

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.gemini_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=20),
           retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    def complete(self, *, system: str, user: str, model: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None,
                 json_mode: bool = False) -> LLMResponse:
        if not self.configured:
            raise LLMError("GEMINI_API_KEY is not set")
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
        with httpx.Client(timeout=settings.ai_timeout) as client:
            resp = client.post(url, json=payload,
                               headers={"x-goog-api-key": self.api_key})
            if resp.status_code == 429:
                raise httpx.HTTPError("Gemini rate limit (429)")
            if resp.status_code >= 400:
                raise LLMError(f"Gemini {resp.status_code}: {resp.text[:400]}")
            data = resp.json()

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text, model=model, provider=self.name,
            tokens_in=usage.get("promptTokenCount", 0),
            tokens_out=usage.get("candidatesTokenCount", 0),
        )
