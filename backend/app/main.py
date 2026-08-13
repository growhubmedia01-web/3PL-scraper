"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, companies, export, opportunities, pipeline, services, stats
from app.api.admin import _open_router as admin_open_router
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s")
log = logging.getLogger("app")

if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment,
                    traces_sample_rate=0.1)

app = FastAPI(
    title="B2B Intent Intelligence & Lead Discovery Platform",
    description=(
        "Configurable B2B intent engine. V1 service: Third-Party Logistics.\n\n"
        "**This platform does not discover, verify or store email addresses.** "
        "A complete lead is Company + Intent + Evidence + Decision Maker."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (services.router, companies.router, opportunities.router,
               stats.router, pipeline.router, export.router, admin.router,
               admin_open_router):
    app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error",
                 "error": str(exc)[:300] if settings.environment == "development"
                 else None})


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "B2B Intent Intelligence Platform",
        "version": "1.0.0",
        "default_service": settings.default_service_slug,
        "docs": "/docs",
        "email_features": "none - out of scope by design (PRD section 5)",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": settings.environment}


@app.on_event("startup")
def on_startup() -> None:
    log.info("Environment: %s", settings.environment)

    # Fail loudly and specifically if the database is behind the code.
    # Without this the first symptom is an UndefinedColumn error thrown from
    # inside a background task, which is far harder to trace back.
    if settings.db_configured:
        from app.db import engine
        from app.schema_check import check_schema
        report = check_schema(engine)
        if not report.ok:
            for line in report.summary().splitlines():
                log.error(line)
        else:
            log.info("Database schema matches the application.")
    if not settings.db_configured:
        log.warning("DATABASE_URL still contains YOUR_DB_PASSWORD - set your "
                    "Supabase database password in backend/.env")
    if not settings.any_llm_configured:
        log.warning("No LLM key configured. The pipeline will run on "
                    "deterministic scoring only. Add GROQ_API_KEY or "
                    "GEMINI_API_KEY to enable AI analysis.")
    if not (settings.serper_api_key or settings.serpapi_key
            or settings.brave_search_api_key):
        log.warning("No search provider key configured - discovery will "
                    "return no results.")
