"""Shared FastAPI dependencies: service resolution and admin auth (§53)."""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.engine.service_config import ServiceConfig, load_service_config


def get_service_config(
    service: str | None = Query(None, description="Service slug, e.g. '3pl'"),
    db: Session = Depends(get_db),
) -> ServiceConfig:
    try:
        return load_service_config(db, service)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def require_admin(x_admin_token: str | None = Header(None)) -> None:
    """Admin endpoints (§46) are gated by a shared secret.

    In production, replace this with Supabase Auth JWT verification and check
    the caller's email against ADMIN_EMAILS.
    """
    if settings.environment == "development" and not settings.secret_key:
        return
    if not x_admin_token or not hmac.compare_digest(
            x_admin_token, settings.secret_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required. Send header X-Admin-Token.")
