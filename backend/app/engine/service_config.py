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
    def query_exclusion_terms(self) -> list[str]:
        """Negative operators appended to every discovery query.

        Every negative term costs recall, so this stays short and lives in
        config rather than code so it can be tuned against real results.
        """
        return list(self.raw_config.get("query_exclusion_terms") or [])

    @property
    def excluded_business_types(self) -> list[str]:
        """Business types rejected at classification even if they slip past
        the search filters - 3PLs, agencies, SaaS, professional services."""
        return list(self.raw_config.get("excluded_business_types") or [])

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

    # ---- generic extensions (007). All optional; absent keys keep the
    # ---- pre-007 behaviour, so legacy services are unaffected.
    @property
    def signal_dimensions(self) -> dict[str, str]:
        """signal_type -> 'intent' | 'fit' | 'negative'. Unlisted = intent."""
        return dict(self.raw_config.get("signal_dimensions") or {})

    def dimension_of(self, signal_type: str) -> str:
        return self.signal_dimensions.get(signal_type, "intent")

    @property
    def dimension_caps(self) -> dict[str, float]:
        """{'intent': 45} caps the score when no live signal of that
        dimension exists - fit alone can never make a lead HOT."""
        return {k: float(v) for k, v in
                (self.raw_config.get("dimension_caps") or {}).items()}

    @property
    def signal_rules(self) -> dict[str, dict]:
        """Per-signal polarity rules evaluated on the matched sentence:
        suppress_phrases, exclude_page_types, require_page_types,
        require_context_phrases."""
        return dict(self.raw_config.get("signal_rules") or {})

    @property
    def undated_confidence_factor(self) -> float:
        return float(self.raw_config.get("undated_confidence_factor", 1.0))

    @property
    def hiring_signal_types(self) -> list[str]:
        explicit = self.raw_config.get("hiring_signal_types")
        if explicit is not None:
            return list(explicit)
        return sorted({k.signal_type for k in self.keywords
                       if k.category == "hiring" and k.signal_type})

    @property
    def qualification(self) -> dict:
        return dict(self.raw_config.get("qualification") or {})

    @property
    def company_type_markers(self) -> dict[str, list[str]]:
        return dict(self.raw_config.get("company_type_markers") or {})

    @property
    def industry_keywords(self) -> dict[str, list[str]]:
        return dict(self.raw_config.get("industry_keywords") or {})

    @property
    def size_bands(self) -> list[dict]:
        return list(self.raw_config.get("size_bands") or [
            {"band": "micro", "min": 1, "max": 10},
            {"band": "small", "min": 11, "max": 49},
            {"band": "mid_market", "min": 50, "max": 500},
            {"band": "large", "min": 501, "max": None},
        ])

    @property
    def fit_multipliers(self) -> dict[str, dict[str, float]]:
        """{'employee_band': {...}, 'company_type': {...}} -> score factors."""
        return dict(self.raw_config.get("fit_multipliers") or {})

    @property
    def product_taxonomy(self) -> dict[str, dict[str, list[str]]]:
        """{category: {subcategory: [terms]}}."""
        return dict(self.raw_config.get("product_taxonomy") or {})

    @property
    def vehicle_segments(self) -> dict[str, list[str]]:
        return dict(self.raw_config.get("vehicle_segments") or {})

    @property
    def vehicle_platforms(self) -> list[str]:
        return list(self.raw_config.get("vehicle_platforms") or [])

    @property
    def interest_type_by_signal(self) -> dict[str, str]:
        return dict(self.raw_config.get("interest_type_by_signal") or {})

    @property
    def adjacent_categories(self) -> dict[str, list[str]]:
        return dict(self.raw_config.get("adjacent_categories") or {})

    @property
    def brand_patterns(self) -> list[str]:
        return list(self.raw_config.get("brand_patterns") or [])

    @property
    def no_product_demand_message(self) -> str:
        return self.raw_config.get("no_product_demand_message") or (
            "Specific product demand not publicly disclosed.")

    @property
    def crawl_priority_paths(self) -> list[tuple[str, str]] | None:
        paths = self.raw_config.get("crawl_priority_paths")
        return [tuple(p) for p in paths] if paths else None

    @property
    def crawl_max_pages(self) -> int | None:
        value = self.raw_config.get("crawl_max_pages")
        return int(value) if value else None

    @property
    def external_query_templates(self) -> list[tuple[str, str, str]] | None:
        rows = self.raw_config.get("external_query_templates")
        return [tuple(r) for r in rows] if rows else None

    @property
    def external_fetchers(self) -> list[str] | None:
        value = self.raw_config.get("external_fetchers")
        return list(value) if value is not None else None

    @property
    def fetch_external_articles(self) -> int:
        """How many external news results to fetch in full (0 = snippets)."""
        return int(self.raw_config.get("fetch_external_articles", 0))

    @property
    def discovery_blocked_domains(self) -> set[str]:
        return {d.lower() for d in
                self.raw_config.get("discovery_blocked_domains") or []}

    @property
    def ai_task(self) -> str | None:
        return self.raw_config.get("ai_task")

    @property
    def ai_extra_fields(self) -> dict[str, str]:
        return dict(self.raw_config.get("ai_extra_fields") or {})

    @property
    def ai_grounded_fields(self) -> list[str]:
        """List fields whose items must literally appear in the evidence."""
        return list(self.raw_config.get("ai_grounded_fields") or [])

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
        from app.utils.text import contains_phrase
        for role in self.roles:
            # Word-boundary match: 'coo' must not match 'coordinator'.
            if contains_phrase(title, role.title_pattern):
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
            f"Service '{slug}' not found. Run the seed migrations "
            f"(ALL_IN_ONE.sql) or `python -m scripts.seed`.")
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
