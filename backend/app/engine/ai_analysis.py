"""AI analysis (§27, §28, Phase 5).

The model interprets evidence; it does not replace deterministic scoring.
Output is validated against a Pydantic schema and clamped - a hallucinated
0.99 probability with no supporting signals cannot drag a lead into HOT,
because the deterministic component still carries the configured weight.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.engine.service_config import ServiceConfig
from app.models import Company, Signal, Source
from app.providers.llm.base import LLMError
from app.providers.llm.factory import LLMService
from app.utils.text import truncate

log = logging.getLogger(__name__)

MAX_EVIDENCE_CHARS = 12_000


class AIAnalysis(BaseModel):
    """Schema the model must satisfy (§27)."""
    is_ecommerce: bool = False
    is_physical_product: bool = False
    service_probability: float = Field(0.0, ge=0.0, le=1.0)
    urgency: str = "low"
    likely_services: list[str] = Field(default_factory=list)
    target_markets: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    evidence_gaps: list[str] = Field(default_factory=list)

    @field_validator("urgency")
    @classmethod
    def _valid_urgency(cls, v: str) -> str:
        v = (v or "low").lower().strip()
        return v if v in {"low", "medium", "high"} else "low"

    @field_validator("likely_services", "target_markets", "evidence_gaps",
                     mode="before")
    @classmethod
    def _listify(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return [str(item) for item in v][:10]


def _build_prompt(company: Company, signals: list[Signal],
                  sources: list[Source], config: ServiceConfig) -> str:
    signal_lines = []
    for signal in signals:
        signal_lines.append(
            f"- {signal.signal_type} (confidence {signal.confidence:.2f}, "
            f"detected {signal.detected_at:%Y-%m-%d}): "
            f"{truncate(signal.evidence or signal.description, 300)}")

    evidence_lines, budget = [], MAX_EVIDENCE_CHARS
    for source in sorted(sources, key=lambda s: s.source_type):
        chunk = (f"[{source.source_type}] {source.url}\n"
                 f"{truncate(source.excerpt or source.content, 700)}")
        if budget - len(chunk) < 0:
            break
        budget -= len(chunk)
        evidence_lines.append(chunk)

    return f"""SERVICE BEING ASSESSED: {config.name}
{config.description or ""}

COMPANY
  Name: {company.name or "unknown"}
  Domain: {company.domain}
  Country (detected): {company.country or "unknown"}
  Industry (detected): {company.industry or "unknown"}
  Platform (detected): {company.platform or "unknown"}
  Ecommerce (detected): {company.is_ecommerce}
  Physical products (detected): {company.is_physical_product}
  Description: {truncate(company.description, 600)}

DETECTED SIGNALS
{chr(10).join(signal_lines) or "  (none)"}

SOURCE EVIDENCE
{chr(10).join(evidence_lines) or "  (none)"}

TASK
Assess how likely this company is to need "{config.name}" services.

Rules:
1. Use ONLY the evidence above. Do not use outside knowledge about this company.
2. If evidence is thin, return a LOW probability and a LOW confidence, and list
   what is missing in evidence_gaps. Do not speculate to fill gaps.
3. reasoning must cite the specific evidence that drove your conclusion.
4. target_markets must be countries or regions the evidence actually mentions.

Return ONLY valid JSON matching this schema:
{{
  "is_ecommerce": boolean,
  "is_physical_product": boolean,
  "service_probability": number between 0 and 1,
  "urgency": "low" | "medium" | "high",
  "likely_services": [string],
  "target_markets": [string],
  "reasoning": string,
  "confidence": number between 0 and 1,
  "evidence_gaps": [string]
}}"""


def analyze(db: Session, company: Company, signals: list[Signal],
            sources: list[Source], config: ServiceConfig) -> AIAnalysis | None:
    """Returns None when no LLM is configured or the call fails after all
    fallbacks - the pipeline continues on deterministic scoring alone (§55)."""
    llm = LLMService(db)
    if not llm.available:
        log.info("No LLM configured; skipping AI analysis for %s", company.domain)
        return None

    try:
        response = llm.complete(
            system=config.ai_system_prompt,
            user=_build_prompt(company, signals, sources, config),
            json_mode=True, operation="analyze_company", company_id=company.id)
    except LLMError as exc:
        log.warning("AI analysis unavailable for %s: %s", company.domain, exc)
        return None

    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("AI returned unparseable JSON for %s: %s", company.domain, exc)
        return None

    # Accept a few aliases so a model drifting on field names doesn't cost a run.
    aliases = (f"{config.slug}_probability", "probability",
               "service_need_probability", "need_probability")
    for alias in aliases:
        if alias in payload and "service_probability" not in payload:
            payload["service_probability"] = payload[alias]

    try:
        analysis = AIAnalysis(**payload)
    except ValidationError as exc:
        log.warning("AI output failed schema validation for %s: %s",
                    company.domain, exc)
        return None

    # Guardrail: the model cannot claim high probability with no signals.
    if not signals and analysis.service_probability > 0.4:
        log.info("Clamping AI probability for %s: no supporting signals",
                 company.domain)
        analysis.service_probability = 0.2
        analysis.confidence = min(analysis.confidence, 0.3)
        analysis.evidence_gaps.append(
            "No detected signals; probability clamped by guardrail")

    return analysis


def to_dict(analysis: AIAnalysis) -> dict:
    data = analysis.model_dump()
    data["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    return data
