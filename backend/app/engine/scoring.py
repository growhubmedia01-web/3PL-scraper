"""Scoring engine (§26, §28, §39).

Three inputs, combined with configurable weights:
    deterministic  - signal weights x freshness x confidence
    ai             - the model's probability, used as an adjustment not a verdict
    evidence       - how well-sourced the conclusion is

Every contribution is recorded in `score_breakdown` so the UI can show the
exact arithmetic (§39) and a human can audit it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.service_config import ServiceConfig
from app.engine.signals import effective_strength
from app.models import Company, ServiceOpportunity, Signal, Source

log = logging.getLogger(__name__)

# Evidence quality: how much a source type is worth as corroboration.
SOURCE_TYPE_QUALITY: dict[str, float] = {
    "registry": 1.0, "funding": 1.0, "press_release": 0.9, "job": 0.9,
    "news": 0.8, "careers": 0.8, "shipping": 0.8, "returns": 0.7,
    "about": 0.7, "crowdfunding": 0.8, "website": 0.6, "directory": 0.5,
    "social": 0.4, "other": 0.3,
}


@dataclass
class ScoreLine:
    label: str
    signal_type: str | None
    weight: float
    multiplier: float
    points: float
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "label": self.label, "signal_type": self.signal_type,
            "weight": round(self.weight, 2), "multiplier": round(self.multiplier, 3),
            "points": round(self.points, 2), "detail": self.detail,
        }


@dataclass
class ScoreResult:
    score: float
    raw_score: float
    deterministic_score: float
    ai_score: float | None
    evidence_score: float
    intent_level: str
    breakdown: list[ScoreLine] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)

    def breakdown_dicts(self) -> list[dict]:
        return [line.to_dict() for line in self.breakdown]


# ---------------------------------------------------------------------
# Deterministic component
# ---------------------------------------------------------------------
def deterministic_score(signals: list[Signal], config: ServiceConfig,
                        now: datetime | None = None
                        ) -> tuple[float, float, list[ScoreLine]]:
    """Returns (raw_points, normalized_0_100, breakdown)."""
    now = now or datetime.now(timezone.utc)
    lines: list[ScoreLine] = []
    raw = 0.0

    for signal in signals:
        signal_def = config.signals.get(signal.signal_type)
        if signal_def is None:
            continue  # signal type was disabled or removed from the config
        multiplier = effective_strength(signal, signal_def, now)
        if multiplier <= 0 and signal_def.weight > 0:
            lines.append(ScoreLine(
                label=f"{signal_def.signal_name} (expired)",
                signal_type=signal.signal_type, weight=float(signal_def.weight),
                multiplier=0.0, points=0.0,
                detail="Signal has decayed past its freshness window"))
            continue

        # Negative signals (e.g. an incumbent provider) apply at full weight -
        # they are not discounted by freshness decay.
        if signal_def.weight < 0:
            points = float(signal_def.weight) * float(signal.confidence)
            multiplier = float(signal.confidence)
        else:
            points = float(signal_def.weight) * multiplier

        raw += points
        lines.append(ScoreLine(
            label=signal_def.signal_name, signal_type=signal.signal_type,
            weight=float(signal_def.weight), multiplier=multiplier,
            points=points,
            detail=(signal.evidence or signal.description or "")[:280]))

    ceiling = config.normalization_ceiling
    normalized = max(0.0, min(100.0, (raw / ceiling) * 100.0)) if ceiling else 0.0
    lines.sort(key=lambda l: l.points, reverse=True)
    return raw, normalized, lines


# ---------------------------------------------------------------------
# Evidence quality component
# ---------------------------------------------------------------------
def evidence_score(db: Session, company: Company, signals: list[Signal]
                   ) -> tuple[float, ScoreLine]:
    """0-100. Rewards: signals that cite a source, diversity of source types,
    and independent (off-site) corroboration."""
    if not signals:
        return 0.0, ScoreLine("Evidence quality", None, 0, 0, 0,
                              "No signals detected")

    cited = [s for s in signals if s.source_id]
    citation_rate = len(cited) / len(signals)

    source_rows = db.execute(
        select(Source).where(Source.company_id == company.id)
    ).scalars().all()
    types = {s.source_type for s in source_rows}
    diversity = min(len(types) / 5.0, 1.0)

    external_types = types & {"news", "funding", "press_release", "job",
                              "crowdfunding", "registry"}
    independence = min(len(external_types) / 3.0, 1.0)

    score = 100.0 * (0.45 * citation_rate + 0.30 * diversity + 0.25 * independence)
    detail = (f"{len(cited)}/{len(signals)} signals cite a source; "
              f"{len(types)} source types; "
              f"{len(external_types)} independent source types")
    return score, ScoreLine("Evidence quality", None, 100.0,
                            score / 100.0, score, detail)


# ---------------------------------------------------------------------
# Combination
# ---------------------------------------------------------------------
def intent_level_for(score: float, config: ServiceConfig) -> str:
    thresholds = config.intent_thresholds
    ordered = sorted(thresholds.items(), key=lambda kv: kv[1], reverse=True)
    for level, minimum in ordered:
        if score >= minimum:
            return level
    return "LOW"


def calculate(db: Session, company: Company, signals: list[Signal],
              config: ServiceConfig, ai_probability: float | None = None,
              now: datetime | None = None) -> ScoreResult:
    weights = config.score_weights
    raw, det_norm, lines = deterministic_score(signals, config, now)
    ev_score, ev_line = evidence_score(db, company, signals)

    ai_norm = None if ai_probability is None else max(
        0.0, min(100.0, float(ai_probability) * 100.0))

    # Renormalize weights when the AI component is unavailable, so a missing
    # LLM key can't silently cap every score at 70.
    w_det, w_ai, w_ev = weights["deterministic"], weights["ai"], weights["evidence"]
    if ai_norm is None:
        total = w_det + w_ev or 1.0
        w_det, w_ev, w_ai = w_det / total, w_ev / total, 0.0

    final = w_det * det_norm + w_ev * ev_score + (w_ai * (ai_norm or 0.0))

    # §23: a service can declare signals that must be present. Missing them
    # caps the score rather than zeroing it - the company may still be worth
    # a look, but must not be presented as HOT.
    missing = [s for s in config.required_signals
               if not any(sig.signal_type == s for sig in signals)]
    if missing:
        final = min(final, 45.0)

    final = round(max(0.0, min(100.0, final)), 2)

    lines.append(ev_line)
    lines.append(ScoreLine(
        label="Deterministic signal subtotal", signal_type=None,
        weight=100.0, multiplier=w_det, points=w_det * det_norm,
        detail=f"{raw:.1f} raw points / {config.normalization_ceiling:.0f} "
               f"ceiling = {det_norm:.1f}, weighted {w_det:.0%}"))
    if ai_norm is not None:
        lines.append(ScoreLine(
            label="AI contextual assessment", signal_type=None,
            weight=100.0, multiplier=w_ai, points=w_ai * ai_norm,
            detail=f"model probability {ai_probability:.2f}, weighted {w_ai:.0%}"))
    lines.append(ScoreLine(
        label="Evidence quality (weighted)", signal_type=None,
        weight=100.0, multiplier=w_ev, points=w_ev * ev_score,
        detail=f"{ev_score:.1f} x {w_ev:.0%}"))
    if missing:
        lines.append(ScoreLine(
            label="Capped: required signals missing", signal_type=None,
            weight=0, multiplier=0, points=0,
            detail=f"Missing {', '.join(missing)} - score capped at 45"))

    return ScoreResult(
        score=final, raw_score=round(raw, 2),
        deterministic_score=round(det_norm, 2),
        ai_score=None if ai_norm is None else round(ai_norm, 2),
        evidence_score=round(ev_score, 2),
        intent_level=intent_level_for(final, config),
        breakdown=lines, missing_required=missing,
    )


def upsert_opportunity(db: Session, company: Company, config: ServiceConfig,
                       result: ScoreResult, ai_analysis: dict | None = None
                       ) -> ServiceOpportunity:
    """Unique on (company_id, service_id) - §19, §51."""
    opportunity = db.execute(
        select(ServiceOpportunity).where(
            ServiceOpportunity.company_id == company.id,
            ServiceOpportunity.service_id == config.id)
    ).scalar_one_or_none()

    if opportunity is None:
        opportunity = ServiceOpportunity(company_id=company.id,
                                         service_id=config.id)
        db.add(opportunity)

    opportunity.score = result.score
    opportunity.raw_score = result.raw_score
    opportunity.deterministic_score = result.deterministic_score
    opportunity.ai_score = result.ai_score
    opportunity.evidence_score = result.evidence_score
    opportunity.score_breakdown = result.breakdown_dicts()
    opportunity.intent_level = result.intent_level
    opportunity.last_analyzed = datetime.now(timezone.utc)

    if ai_analysis:
        opportunity.ai_analysis = ai_analysis
        opportunity.urgency = ai_analysis.get("urgency")
        opportunity.likely_need = ai_analysis.get("likely_services") or []
        opportunity.target_country = ai_analysis.get("target_markets") or []
        opportunity.reasoning = ai_analysis.get("reasoning")
        opportunity.confidence = ai_analysis.get("confidence")
    elif not opportunity.reasoning:
        top = [l.label for l in result.breakdown if l.points > 0][:4]
        opportunity.reasoning = (
            "Deterministic assessment only (no AI analysis run). "
            f"Strongest signals: {', '.join(top) if top else 'none'}.")

    db.flush()
    return opportunity
