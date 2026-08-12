"""Central configuration. Everything is env-driven; nothing is hardcoded."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, unquote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def _fix_unencoded_password(url: str) -> str:
    """Percent-encode a database password containing reserved characters.

    Supabase passwords frequently contain '@', ':', '/' or '#'. Pasted raw
    into a connection URI they mis-parse silently -
    'postgres:Shaik@HB1234@host/db' yields password='Shaik' and
    host='HB1234@host', producing a baffling DNS error instead of an auth
    error.

    The split is unambiguous as long as we anchor on the LAST '@': everything
    before it is userinfo, everything after is host[:port][/database]. That
    holds even when the password itself contains '@' or '/'.
    """
    if "://" not in url or url.startswith("sqlite"):
        return url

    scheme, _, rest = url.partition("://")
    last_at = rest.rfind("@")
    if last_at == -1:
        return url                      # no credentials in the URL

    userinfo, remainder = rest[:last_at], rest[last_at + 1:]
    user, colon, password = userinfo.partition(":")
    if not colon or not password:
        return url                      # no password to encode

    encoded = quote(password, safe="")
    if encoded == password:
        return url                      # nothing reserved to encode
    if unquote(password) != password:
        return url                      # already percent-encoded; don't double it

    log.warning(
        "Database password contains reserved characters and was not "
        "percent-encoded; encoding it automatically. To silence this warning, "
        "store the encoded form in .env: %s:%s@...", user, encoded)
    return f"{scheme}://{user}:{encoded}@{remainder}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- core ----
    environment: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me"
    admin_emails: str = ""
    cors_origins: str = "http://localhost:5173"

    # ---- supabase / db ----
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = "sqlite+pysqlite:///./local.db"
    database_migration_url: str = ""

    # ---- search ----
    search_provider: str = "serper"
    serper_api_key: str = ""
    serpapi_key: str = ""
    brave_search_api_key: str = ""
    exa_api_key: str = ""
    search_cache_ttl_hours: int = 168
    search_max_results: int = 20

    # ---- llm ----
    ai_provider: str = "groq"
    ai_fallback_providers: str = "gemini,openai"
    ai_model: str = "llama-3.3-70b-versatile"
    ai_temperature: float = 0.1
    ai_max_tokens: int = 2048
    ai_timeout: int = 60
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # ---- crawler ----
    crawler_user_agent: str = "IntentBot/1.0 (+https://example.com/bot)"
    crawl_concurrency: int = 5
    crawl_delay_seconds: float = 2.0
    crawl_timeout_seconds: int = 20
    crawl_max_retries: int = 3
    crawl_max_pages_per_company: int = 12
    respect_robots_txt: bool = True
    playwright_enabled: bool = False

    # ---- external signal sources ----
    companies_house_api_key: str = ""
    sec_edgar_user_agent: str = ""

    # ---- infra ----
    redis_url: str = "redis://localhost:6379/0"
    sentry_dsn: str = ""

    # ---- scoring defaults (DB service.config overrides these) ----
    score_weight_deterministic: float = 0.5
    score_weight_ai: float = 0.3
    score_weight_evidence: float = 0.2
    decision_maker_threshold: int = 80
    ai_analysis_min_raw_score: int = 25

    # ---- cost guards ----
    max_companies_per_discovery_run: int = 200
    max_queries_per_discovery_run: int = 50
    max_ai_calls_per_run: int = 100

    default_service_slug: str = "3pl"

    @field_validator("database_url", "database_migration_url")
    @classmethod
    def _normalize_driver(cls, v: str) -> str:
        # accept plain postgres:// URLs copied from the Supabase dashboard
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)
        return _fix_unencoded_password(v)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def fallback_provider_list(self) -> list[str]:
        return [p.strip() for p in self.ai_fallback_providers.split(",") if p.strip()]

    @property
    def db_configured(self) -> bool:
        return "YOUR_DB_PASSWORD" not in self.database_url

    @property
    def any_llm_configured(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key or self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
