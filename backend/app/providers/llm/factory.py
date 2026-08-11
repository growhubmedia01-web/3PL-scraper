"""LLM factory + fallback chain + usage accounting (§47, §55, §56)."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiUsage
from app.providers.llm.base import LLMError, LLMProvider, LLMResponse
from app.providers.llm.gemini_provider import GeminiProvider
from app.providers.llm.groq_provider import GroqProvider
from app.providers.llm.openai_provider import OpenAIProvider

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}

# USD per 1M tokens. Indicative only - update from vendor pricing pages.
# Used for the cost-per-qualified-lead metric (§66), not for billing.
_COST_PER_MTOK: dict[str, tuple[float, float]] = {
    "groq": (0.59, 0.79),
    "gemini": (0.10, 0.40),
    "openai": (0.15, 0.60),
}


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _REGISTRY[name.lower()] = cls


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_llm_provider(name: str | None = None) -> LLMProvider:
    key = (name or settings.ai_provider or "groq").lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise LLMError(f"Unknown LLM provider '{key}'. Available: {available_providers()}")
    return cls()


def estimate_cost(provider: str, tokens_in: int, tokens_out: int) -> float:
    rate_in, rate_out = _COST_PER_MTOK.get(provider, (0.0, 0.0))
    return (tokens_in / 1_000_000 * rate_in) + (tokens_out / 1_000_000 * rate_out)


class LLMService:
    """Primary provider with automatic fallback, plus per-call usage logging."""

    def __init__(self, db: Session | None = None, provider: str | None = None):
        self.db = db
        self.chain: list[LLMProvider] = []
        for name in [provider or settings.ai_provider, *settings.fallback_provider_list]:
            if name in {p.name for p in self.chain}:
                continue
            try:
                candidate = get_llm_provider(name)
            except LLMError:
                continue
            if candidate.configured:
                self.chain.append(candidate)

    @property
    def available(self) -> bool:
        return bool(self.chain)

    def _log(self, resp: LLMResponse | None, provider: str, operation: str,
             success: bool, company_id: str | None) -> None:
        if self.db is None:
            return
        self.db.add(ApiUsage(
            provider=provider, operation=operation,
            model=resp.model if resp else settings.ai_model,
            tokens_in=resp.tokens_in if resp else 0,
            tokens_out=resp.tokens_out if resp else 0,
            cost_usd=estimate_cost(provider, resp.tokens_in, resp.tokens_out)
            if resp else 0,
            success=success, company_id=company_id,
        ))
        self.db.flush()

    def complete(self, *, system: str, user: str, json_mode: bool = True,
                 operation: str = "analysis", company_id: str | None = None,
                 max_tokens: int | None = None) -> LLMResponse:
        if not self.chain:
            raise LLMError(
                "No LLM provider configured. Set GROQ_API_KEY, GEMINI_API_KEY "
                "or OPENAI_API_KEY in backend/.env")
        last: Exception | None = None
        for provider in self.chain:
            try:
                resp = provider.complete(system=system, user=user,
                                         json_mode=json_mode, max_tokens=max_tokens)
                self._log(resp, provider.name, operation, True, company_id)
                return resp
            except Exception as exc:
                last = exc
                self._log(None, provider.name, operation, False, company_id)
                log.warning("LLM provider %s failed (%s); trying fallback",
                            provider.name, exc)
                continue
        raise LLMError(f"All LLM providers failed. Last error: {last}")
