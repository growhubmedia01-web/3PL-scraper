"""ORM models. Mirrors backend/migrations/001_init.sql.

Design rule (§70): nothing in this module knows what "3PL" is. Service
specificity lives in the `services`, `service_signals`, `service_keywords`,
`discovery_queries` and `service_roles` rows - i.e. in data, not in code.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, CHAR, TypeDecorator


class GUID(TypeDecorator):
    """UUID on Postgres, CHAR(36) elsewhere."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return str(value) if value is not None else None


JSONType = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow,
        onupdate=utcnow)


# =====================================================================
# SERVICE CONFIGURATION
# =====================================================================
class Service(Base, TimestampMixin):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    signals_cfg: Mapped[list["ServiceSignal"]] = relationship(
        back_populates="service", cascade="all, delete-orphan")
    keywords: Mapped[list["ServiceKeyword"]] = relationship(
        back_populates="service", cascade="all, delete-orphan")
    queries: Mapped[list["DiscoveryQuery"]] = relationship(
        back_populates="service", cascade="all, delete-orphan")
    roles: Mapped[list["ServiceRole"]] = relationship(
        back_populates="service", cascade="all, delete-orphan")


class ServiceSignal(Base, TimestampMixin):
    """Signal definition + weight for one service. The scoring engine loads
    these at runtime - weights are never hardcoded."""
    __tablename__ = "service_signals"
    __table_args__ = (UniqueConstraint("service_id", "signal_type"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    signal_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    decay_days: Mapped[int | None] = mapped_column(Integer)
    max_occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service: Mapped[Service] = relationship(back_populates="signals_cfg")


class ServiceKeyword(Base):
    __tablename__ = "service_keywords"
    __table_args__ = (UniqueConstraint("service_id", "keyword", "category"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    signal_type: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)

    service: Mapped[Service] = relationship(back_populates="keywords")


class DiscoveryQuery(Base):
    __tablename__ = "discovery_queries"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)

    service: Mapped[Service] = relationship(back_populates="queries")


class ServiceRole(Base):
    """Which job titles matter for this service, and in what order (§21)."""
    __tablename__ = "service_roles"
    __table_args__ = (UniqueConstraint("service_id", "title_pattern"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    title_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    role_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service: Mapped[Service] = relationship(back_populates="roles")


# =====================================================================
# GENERIC COMPANY INTELLIGENCE (shared across every service)
# =====================================================================
class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (Index("idx_companies_status", "status"),
                      Index("idx_companies_country", "country"))

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    linkedin_source: Mapped[str | None] = mapped_column(Text)  # json_ld | site_link | search
    linkedin_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    country: Mapped[str | None] = mapped_column(String(2))
    country_confidence: Mapped[float | None] = mapped_column(Float)
    industry: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_ecommerce: Mapped[bool | None] = mapped_column(Boolean)
    is_physical_product: Mapped[bool | None] = mapped_column(Boolean)
    platform: Mapped[str | None] = mapped_column(Text)
    employee_count: Mapped[int | None] = mapped_column(Integer)
    founded_year: Mapped[int | None] = mapped_column(Integer)
    currencies: Mapped[list] = mapped_column(JSONType, default=list)
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    # What kind of business is this? dtc | wholesale | manufacturer |
    # retail | marketplace | subscription | importer | multi_channel
    business_model: Mapped[str | None] = mapped_column(Text)
    sales_channels: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="discovered")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    discovered_via: Mapped[str | None] = mapped_column(Text)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list["Source"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    opportunities: Mapped[list["ServiceOpportunity"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")
    decision_makers: Mapped[list["DecisionMaker"]] = relationship(
        back_populates="company", cascade="all, delete-orphan")


class Source(Base):
    """Every meaningful signal must point at one of these (§29)."""
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("company_id", "url"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
    content_hash: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)

    company: Mapped[Company] = relationship(back_populates="sources")


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    page_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    http_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)


class Signal(Base):
    """A detected, evidenced, time-bounded fact about a company for a service."""
    __tablename__ = "signals"
    __table_args__ = (Index("idx_signals_company_service", "company_id", "service_id"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    description: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("sources.id", ondelete="SET NULL"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)

    company: Mapped[Company] = relationship(back_populates="signals")
    source: Mapped[Source | None] = relationship()


class ServiceOpportunity(Base, TimestampMixin):
    __tablename__ = "service_opportunities"
    __table_args__ = (
        UniqueConstraint("company_id", "service_id"),
        Index("idx_opps_score", "score"),
        CheckConstraint(
            "intent_level in ('LOW','POSSIBLE','GOOD','STRONG','HOT')",
            name="ck_intent_level"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    raw_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    deterministic_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0)
    ai_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    evidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    score_breakdown: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    intent_level: Mapped[str] = mapped_column(Text, nullable=False, default="LOW")
    urgency: Mapped[str | None] = mapped_column(Text)
    likely_need: Mapped[list] = mapped_column(JSONType, default=list)
    target_country: Mapped[list] = mapped_column(JSONType, default=list)
    reasoning: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    ai_analysis: Mapped[dict | None] = mapped_column(JSONType)
    last_analyzed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(back_populates="opportunities")


class DecisionMaker(Base, TimestampMixin):
    """NO EMAIL FIELDS. This is a deliberate product constraint (§5, §20, §35)."""
    __tablename__ = "decision_makers"
    __table_args__ = (UniqueConstraint("company_id", "name", "job_title"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("sources.id", ondelete="SET NULL"))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence_label: Mapped[str | None] = mapped_column(Text)
    role_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    company: Mapped[Company] = relationship(back_populates="decision_makers")


class Suppression(Base):
    """GDPR right-to-object list. Checked before every decision_maker write."""
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("kind", "value"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)


# =====================================================================
# OPS
# =====================================================================
class SearchCache(Base):
    __tablename__ = "search_cache"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    service_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("services.id", ondelete="SET NULL"))
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    stats: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiUsage(Base):
    """Feeds §56 monitoring and the cost-per-qualified-lead metric in §66."""
    __tablename__ = "api_usage"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    company_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("companies.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)


class LeadReview(Base):
    __tablename__ = "lead_reviews"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("service_opportunities.id", ondelete="CASCADE"),
        nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow)
