"""API response/request schemas. No email fields anywhere (§5, §35, §40)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- services ----------------
class ServiceOut(ORMBase):
    id: str
    name: str
    slug: str
    description: str | None = None
    status: str
    config: dict = {}


class ServiceSignalOut(ORMBase):
    id: str
    signal_type: str
    signal_name: str
    description: str | None = None
    weight: float
    decay_days: int | None = None
    max_occurrences: int
    enabled: bool


class DiscoveryQueryOut(ORMBase):
    id: str
    query: str
    country: str | None = None
    priority: int
    enabled: bool
    last_run_at: datetime | None = None
    results_count: int


class ServiceKeywordOut(ORMBase):
    id: str
    keyword: str
    category: str | None = None
    signal_type: str | None = None
    weight: float
    enabled: bool


class ServiceRoleOut(ORMBase):
    id: str
    title_pattern: str
    role_priority: int
    enabled: bool


# ---------------- company / evidence ----------------
class SourceOut(ORMBase):
    id: str
    source_type: str
    url: str
    title: str | None = None
    excerpt: str | None = None
    published_at: datetime | None = None
    discovered_at: datetime
    http_status: int | None = None


class SignalOut(ORMBase):
    id: str
    signal_type: str
    strength: float
    description: str | None = None
    evidence: str | None = None
    confidence: float
    detected_at: datetime
    expires_at: datetime | None = None
    source_id: str | None = None
    source_url: str | None = None


class DecisionMakerOut(ORMBase):
    """No email field. Deliberate (§20)."""
    id: str
    name: str
    job_title: str | None = None
    profile_url: str | None = None
    source: str | None = None
    confidence: float
    confidence_label: str | None = None
    role_priority: int


class CompanyOut(ORMBase):
    id: str
    name: str | None = None
    domain: str
    website: str | None = None
    country: str | None = None
    country_confidence: float | None = None
    industry: str | None = None
    description: str | None = None
    is_ecommerce: bool | None = None
    is_physical_product: bool | None = None
    platform: str | None = None
    business_model: str | None = None
    sales_channels: list[str] = []
    employee_count: int | None = None
    founded_year: int | None = None
    status: str
    rejection_reason: str | None = None
    discovered_via: str | None = None
    last_crawled_at: datetime | None = None
    created_at: datetime


class ScoreLineOut(BaseModel):
    label: str
    signal_type: str | None = None
    weight: float
    multiplier: float
    points: float
    detail: str = ""


# ---------------- opportunities ----------------
class OpportunityOut(ORMBase):
    id: str
    company_id: str
    service_id: str
    score: float
    raw_score: float
    deterministic_score: float
    ai_score: float | None = None
    evidence_score: float
    intent_level: str
    urgency: str | None = None
    likely_need: list[str] = []
    target_country: list[str] = []
    reasoning: str | None = None
    confidence: float | None = None
    last_analyzed: datetime | None = None
    created_at: datetime


class OpportunityListItem(BaseModel):
    """Row shape for the lead list (§37)."""
    id: str
    company_id: str
    company_name: str | None = None
    domain: str
    website: str | None = None
    country: str | None = None
    industry: str | None = None
    platform: str | None = None
    business_model: str | None = None
    score: float
    intent_level: str
    urgency: str | None = None
    likely_need: list[str] = []
    signal_types: list[str] = []
    signal_count: int = 0
    evidence_count: int = 0
    decision_maker_name: str | None = None
    decision_maker_title: str | None = None
    decision_maker_confidence: float | None = None
    has_decision_maker: bool = False
    last_analyzed: datetime | None = None
    created_at: datetime


class OpportunityDetail(BaseModel):
    """Lead detail page payload (§38, §39)."""
    opportunity: OpportunityOut
    company: CompanyOut
    signals: list[SignalOut] = []
    sources: list[SourceOut] = []
    decision_makers: list[DecisionMakerOut] = []
    score_breakdown: list[ScoreLineOut] = []
    ai_analysis: dict | None = None


class PaginatedOpportunities(BaseModel):
    items: list[OpportunityListItem]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedCompanies(BaseModel):
    items: list[CompanyOut]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------- dashboard ----------------
class DashboardStats(BaseModel):
    """§36."""
    total_companies: int = 0
    total_opportunities: int = 0
    hot_leads: int = 0
    strong_leads: int = 0
    good_leads: int = 0
    new_leads_7d: int = 0
    countries: int = 0
    average_score: float = 0.0
    decision_makers_identified: int = 0
    companies_crawled: int = 0
    companies_rejected: int = 0
    crawl_success_rate: float = 0.0
    signals_detected: int = 0
    ai_calls: int = 0
    ai_failures: int = 0
    estimated_cost_usd: float = 0.0
    by_country: list[dict] = []
    by_intent: list[dict] = []
    by_signal: list[dict] = []
    by_business_model: list[dict] = []


# ---------------- admin ----------------
class ServiceCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    status: str = "draft"
    config: dict = {}


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    config: dict | None = None


class SignalCreate(BaseModel):
    signal_type: str
    signal_name: str
    description: str | None = None
    weight: float = 0
    decay_days: int | None = None
    max_occurrences: int = 1
    enabled: bool = True


class SignalUpdate(BaseModel):
    signal_name: str | None = None
    description: str | None = None
    weight: float | None = None
    decay_days: int | None = None
    max_occurrences: int | None = None
    enabled: bool | None = None


class QueryCreate(BaseModel):
    query: str
    country: str | None = None
    priority: int = 5
    enabled: bool = True


class QueryUpdate(BaseModel):
    query: str | None = None
    country: str | None = None
    priority: int | None = None
    enabled: bool | None = None


class KeywordCreate(BaseModel):
    keyword: str
    category: str | None = None
    signal_type: str | None = None
    weight: float = 1.0
    enabled: bool = True


class DiscoveryRunRequest(BaseModel):
    service_slug: str | None = None
    limit: int | None = Field(None, ge=1, le=1000,
                              description="Max companies created this run")
    max_queries: int | None = Field(None, ge=1, le=2000,
                                    description="Max Serper queries this run")
    tier: int | None = Field(None, ge=1, le=4,
                             description="1=platform+category (best yield), "
                                         "4=broad/geographic")
    country: str | None = None
    run_async: bool = True


class QueryLibraryStats(BaseModel):
    total: int
    enabled: int
    never_run: int
    by_tier: list[dict]
    estimated_serper_credits_full_pass: int


class AnalyzeRequest(BaseModel):
    service_slug: str | None = None
    force_crawl: bool = False
    skip_external: bool = False
    allow_ai: bool = True
    run_async: bool = True


class ManualCompanyRequest(BaseModel):
    url: str
    name: str | None = None
    analyze_now: bool = True


class SuppressionCreate(BaseModel):
    kind: str = Field(pattern="^(domain|person)$")
    value: str
    reason: str | None = None


class LeadReviewCreate(BaseModel):
    label: str = Field(pattern="^(excellent|good|maybe|bad)$")
    notes: str | None = None
    reviewer: str | None = None


class TaskAccepted(BaseModel):
    accepted: bool = True
    task_id: str | None = None
    message: str
    result: dict | None = None
