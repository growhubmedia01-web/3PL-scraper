"""Runtime view of a service's configuration (§10, §70).

The engine reads everything service-specific from here. Nothing below this
line knows the word "3PL" - that lives in the database rows created by
migrations/003_seed_3pl.sql.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DiscoveryQuery, Service, ServiceKeyword, ServiceRole, ServiceSignal,
)

DEFAULT_INTENT_THRESHOLDS = {"LOW": 0, "POSSIBLE": 31, "GOOD": 51,
                             "STRONG": 71, "HOT": 86}
DEFAULT_REFRESH_DAYS = {"HOT": 3, "STRONG": 7, "GOOD": 30,
                        "POSSIBLE": 60, "LOW": 180}


@dataclass
class SignalDef:
    signal_type: str
    signal_name: str
    weight: float
    decay_days: int | None
    max_occurrences: int
    description: str | None = None


@dataclass
class KeywordDef:
    keyword: str
    category: str | None
    signal_type: str | None
    weight: float


@dataclass
class RoleDef:
    title_pattern: str
    role_priority: int


@dataclass
class ServiceConfig:
    id: str
    slug: str
    name: str
    description: str | None
    raw_config: dict = field(default_factory=dict)
    signals: dict[str, SignalDef] = field(default_factory=dict)
    keywords: list[KeywordDef] = field(default_factory=list)
    queries: list[DiscoveryQuery] = field(default_factory=list)
    roles: list[RoleDef] = field(default_factory=list)

    # ---- derived config with safe fallbacks ----
    @property
    def score_weights(self) -> dict[str, float]:
        cfg = self.raw_config.get("score_weights") or {}
        return {
            "deterministic": float(cfg.get("deterministic",
                                           settings.score_weight_deterministic)),
            "ai": float(cfg.get("ai", settings.score_weight_ai)),
            "evidence": float(cfg.get("evidence", settings.score_weight_evidence)),
        }

    @property
    def intent_thresholds(self) -> dict[str, int]:
        cfg = self.raw_config.get("intent_thresholds") or {}
        return {**DEFAULT_INTENT_THRESHOLDS, **{k: int(v) for k, v in cfg.items()}}

    @property
    def refresh_days(self) -> dict[str, int]:
        cfg = self.raw_config.get("refresh_days") or {}
        return {**DEFAULT_REFRESH_DAYS, **{k: int(v) for k, v in cfg.items()}}

    @property
    def normalization_ceiling(self) -> float:
        """Raw score that maps to 100. Defaults to the sum of positive weights."""
        explicit = self.raw_config.get("normalization_ceiling")
        if explicit:
            return float(explicit)
        total = sum(s.weight * s.max_occurrences
                    for s in self.signals.values() if s.weight > 0)
        return max(total, 1.0)

    @property
    def required_signals(self) -> list[str]:
        return list(self.raw_config.get("required_signals") or [])

    @property
    def dm_threshold(self) -> float:
        return float(self.raw_config.get("decision_maker_threshold",
                                         settings.decision_maker_threshold))

    @property
    def dm_optional_threshold(self) -> float:
        return float(self.raw_config.get("decision_maker_optional_threshold", 60))

    @property
    def ai_min_raw_score(self) -> float:
        return float(self.raw_config.get("ai_analysis_min_raw_score",
                                         settings.ai_analysis_min_raw_score))

    @property
    def page_affinity(self) -> dict[str, set[str]]:
        """Which page types make a keyword hit meaningful for each signal.
        Falls back to generic defaults; services can override or extend."""
        from app.engine.signals import DEFAULT_PAGE_AFFINITY
        merged = {k: set(v) for k, v in DEFAULT_PAGE_AFFINITY.items()}
        for signal_type, page_types in (
                self.raw_config.get("signal_page_affinity") or {}).items():
            merged[signal_type] = set(page_types)
        return merged

    @property
    def ai_system_prompt(self) -> str:
        return self.raw_config.get("ai_system_prompt") or (
            f"You are a B2B analyst assessing whether a company needs "
            f"'{self.name}' services. Base every conclusion strictly on the "
            f"supplied evidence and never invent facts."
        )

    def weight_for(self, signal_type: str) -> float:
        sig = self.signals.get(signal_type)
        return float(sig.weight) if sig else 0.0

    def keywords_for(self, signal_type: str) -> list[KeywordDef]:
        return [k for k in self.keywords if k.signal_type == signal_type]

    def role_priority_for(self, job_title: str | None) -> int | None:
        """Lowest number wins. Longest pattern match wins to avoid 'ceo'
        matching inside a longer title before a more specific pattern."""
        if not job_title:
            return None
        title = job_title.lower()
        best: tuple[int, int] | None = None  # (pattern_length, priority)
        for role in self.roles:
            if role.title_pattern in title:
                candidate = (len(role.title_pattern), role.role_priority)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        return best[1] if best else None


def load_service_config(db: Session, slug: str | None = None) -> ServiceConfig:
    slug = slug or settings.default_service_slug
    service = db.execute(
        select(Service).where(Service.slug == slug)
    ).scalar_one_or_none()
    if service is None:
        raise LookupError(
            f"Service '{slug}' not found. Run migrations/003_seed_3pl.sql "
            f"or `python -m scripts.seed`.")
    return build_config(db, service)


def load_service_config_by_id(db: Session, service_id: str) -> ServiceConfig:
    service = db.get(Service, service_id)
    if service is None:
        raise LookupError(f"Service id '{service_id}' not found")
    return build_config(db, service)


def build_config(db: Session, service: Service) -> ServiceConfig:
    signal_rows = db.execute(
        select(ServiceSignal).where(
            ServiceSignal.service_id == service.id,
            ServiceSignal.enabled.is_(True))
    ).scalars().all()
    keyword_rows = db.execute(
        select(ServiceKeyword).where(
            ServiceKeyword.service_id == service.id,
            ServiceKeyword.enabled.is_(True))
    ).scalars().all()
    query_rows = db.execute(
        select(DiscoveryQuery).where(
            DiscoveryQuery.service_id == service.id,
            DiscoveryQuery.enabled.is_(True))
        .order_by(DiscoveryQuery.priority)
    ).scalars().all()
    role_rows = db.execute(
        select(ServiceRole).where(
            ServiceRole.service_id == service.id,
            ServiceRole.enabled.is_(True))
        .order_by(ServiceRole.role_priority)
    ).scalars().all()

    return ServiceConfig(
        id=service.id, slug=service.slug, name=service.name,
        description=service.description, raw_config=service.config or {},
        signals={
            r.signal_type: SignalDef(
                signal_type=r.signal_type, signal_name=r.signal_name,
                weight=float(r.weight), decay_days=r.decay_days,
                max_occurrences=r.max_occurrences, description=r.description)
            for r in signal_rows
        },
        keywords=[KeywordDef(r.keyword.lower(), r.category, r.signal_type,
                             float(r.weight)) for r in keyword_rows],
        queries=list(query_rows),
        roles=[RoleDef(r.title_pattern.lower(), r.role_priority) for r in role_rows],
    )
