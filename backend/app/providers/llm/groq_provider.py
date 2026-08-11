from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.llm.base import LLMError, LLMProvider, LLMResponse

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(LLMProvider):
    name = "groq"
    default_model = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.groq_api_key

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
            raise LLMError("GROQ_API_KEY is not set")
        model = model or settings.ai_model or self.default_model
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": settings.ai_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or settings.ai_max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=settings.ai_timeout) as client:
            resp = client.post(_ENDPOINT, json=payload, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"})
            if resp.status_code == 429:
                raise httpx.HTTPError("Groq rate limit (429)")
            if resp.status_code >= 400:
                raise LLMError(f"Groq {resp.status_code}: {resp.text[:400]}")
            data = resp.json()

        usage = data.get("usage") or {}
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            model=model, provider=self.name,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )
