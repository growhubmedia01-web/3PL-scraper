"""Setup doctor. Tells you exactly what is and isn't configured, and why the
database might be empty.

    python -m scripts.check_setup
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

OK, WARN, FAIL = "  [ OK ]", "  [WARN]", "  [FAIL]"
problems: list[str] = []


def header(text: str) -> None:
    print(f"\n{text}\n" + "-" * len(text))


def check_project_refs() -> None:
    """The DB URL and the Supabase keys must belong to the same project."""
    import base64
    import json
    import re

    db_ref = None
    match = re.search(r"(?:db\.|postgres\.)([a-z]{20})", settings.database_url)
    if match:
        db_ref = match.group(1)
    pooler = re.search(r"postgres\.([a-z]{20})", settings.database_url)
    if pooler:
        db_ref = pooler.group(1)

    key_ref = None
    key = settings.supabase_service_role_key
    if key and key.count(".") == 2:
        try:
            payload = key.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            key_ref = json.loads(base64.urlsafe_b64decode(payload)).get("ref")
        except Exception:
            key_ref = None

    url_ref = None
    match = re.search(r"https://([a-z]{20})\.supabase\.co", settings.supabase_url)
    if match:
        url_ref = match.group(1)

    if not db_ref:
        return
    mismatched = {r for r in (key_ref, url_ref) if r and r != db_ref}
    if not mismatched:
        if key_ref or url_ref:
            print(f"{OK} Supabase project refs agree ({db_ref}).")
        return

    print(f"{WARN} Supabase project mismatch:")
    print(f"         DATABASE_URL       -> {db_ref}")
    if url_ref:
        print(f"         SUPABASE_URL       -> {url_ref}")
    if key_ref:
        print(f"         service-role key   -> {key_ref}")
    print("         The backend uses SQLAlchemy against DATABASE_URL, so it")
    print("         will still work. But update SUPABASE_URL and the keys to")
    print("         the same project before using supabase-js or the REST API.")


def check_database() -> bool:
    header("1. Database")
    url = settings.database_url

    if "YOUR_DB_PASSWORD" in url:
        print(f"{FAIL} DATABASE_URL still contains the YOUR_DB_PASSWORD placeholder.")
        print("         Nothing can be stored until this is a real connection string.")
        print("         Supabase -> Project Settings -> Database -> Connection string")
        print("         Or run everything locally first:")
        print('           DATABASE_URL="sqlite+pysqlite:///./local.db"')
        problems.append("DATABASE_URL is not configured")
        return False

    kind = "SQLite (local file)" if url.startswith("sqlite") else "PostgreSQL"
    print(f"{OK} Driver: {kind}")
    print(f"       Target: {url.split('@')[-1]}")

    if not url.startswith("sqlite"):
        from sqlalchemy.engine import make_url
        parsed = make_url(url)
        if parsed.host and "@" in parsed.host:
            print(f"{FAIL} The password contains an unencoded reserved character.")
            print(f"         Parsed host is {parsed.host!r} — that is wrong.")
            print("         Percent-encode it: @ becomes %40, : becomes %3A")
            problems.append("database password is not percent-encoded")
            return False
        check_project_refs()

    # DNS pre-check: a failed lookup here is by far the most common problem,
    # and the psycopg traceback for it is 60 lines of noise.
    if not url.startswith("sqlite"):
        import socket
        from sqlalchemy.engine import make_url
        host = make_url(url).host
        try:
            socket.getaddrinfo(host, None)
            print(f"{OK} DNS: {host} resolves.")
        except socket.gaierror:
            print(f"{FAIL} DNS: {host} does not resolve.")
            print("         Nothing can connect until this is fixed.\n")
            print("         Supabase direct-connection hostnames "
                  "(db.<ref>.supabase.co)")
            print("         are IPv6-only on projects created after early 2024,")
            print("         and often will not resolve at all on IPv4 networks.\n")
            print("         Two fixes:\n")
            print("         A) Skip the network entirely (recommended).")
            print("            Paste backend/migrations/ALL_IN_ONE.sql into the")
            print("            Supabase SQL Editor and press Run. That creates")
            print("            the schema and seeds the 3PL config with no local")
            print("            database connection at all.\n")
            print("         B) Use the transaction pooler, which is IPv4:")
            print("            Supabase -> Project Settings -> Database ->")
            print("            Connection string -> Transaction pooler")
            print("            Host looks like: aws-0-<region>.pooler.supabase.com")
            print("            Port 6543. Put that in DATABASE_URL.\n")
            print("         Also confirm the project ref is right and the")
            print("         project is not paused (free projects pause when idle).")
            problems.append(f"DNS lookup failed for {host}")
            return False

    try:
        from sqlalchemy import text

        from app.db import engine
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        print(f"{OK} Connection succeeded.")
    except Exception as exc:
        message = str(exc)
        print(f"{FAIL} Could not connect: {type(exc).__name__}: {message[:200]}")
        if "Network is unreachable" in message or "could not translate" in message:
            print("\n         Direct connections (db.<ref>.supabase.co:5432) are")
            print("         IPv6-only on newer Supabase projects. If your network")
            print("         is IPv4-only, use the transaction pooler instead:")
            print("           Supabase -> Project Settings -> Database ->")
            print("           Connection string -> Transaction pooler (port 6543)")
        elif "password authentication failed" in message:
            print("\n         The host resolved, so the URL is well-formed — the")
            print("         password is simply wrong. Reset it in Supabase ->")
            print("         Project Settings -> Database.")
        problems.append("database connection failed")
        return False
    return True


def check_schema() -> bool:
    header("2. Schema and seed data")
    try:
        from sqlalchemy import func, inspect, select

        from app.db import SessionLocal, engine
        from app.models import (
            Company, DiscoveryQuery, Service, ServiceOpportunity,
            ServiceSignal, Signal,
        )

        tables = set(inspect(engine).get_table_names())
        expected = {"services", "service_signals", "service_keywords",
                    "discovery_queries", "service_roles", "companies",
                    "sources", "crawl_jobs", "signals",
                    "service_opportunities", "decision_makers"}
        missing = expected - tables

        if missing:
            print(f"{FAIL} {len(missing)} tables missing: {', '.join(sorted(missing))}")
            print("         Run:  python -m scripts.seed")
            print("         (or paste backend/migrations/*.sql into the "
                  "Supabase SQL editor)")
            problems.append("schema not created")
            return False
        print(f"{OK} All {len(expected)} core tables exist.")

        db = SessionLocal()
        try:
            service = db.execute(
                select(Service).where(Service.slug == settings.default_service_slug)
            ).scalar_one_or_none()
            if service is None:
                print(f"{FAIL} Service '{settings.default_service_slug}' not seeded.")
                print("         Run:  python -m scripts.seed")
                problems.append("service config not seeded")
                return False

            counts = {
                "signal definitions": db.execute(
                    select(func.count(ServiceSignal.id))
                    .where(ServiceSignal.service_id == service.id)).scalar_one(),
                "discovery queries": db.execute(
                    select(func.count(DiscoveryQuery.id))
                    .where(DiscoveryQuery.service_id == service.id)).scalar_one(),
            }
            print(f"{OK} Service '{service.slug}' seeded "
                  f"({counts['signal definitions']} signals, "
                  f"{counts['discovery queries']} discovery queries).")

            data = {
                "companies": db.execute(select(func.count(Company.id))).scalar_one(),
                "signals detected": db.execute(
                    select(func.count(Signal.id))).scalar_one(),
                "opportunities": db.execute(
                    select(func.count(ServiceOpportunity.id))).scalar_one(),
            }
            print()
            for label, count in data.items():
                print(f"       {label:20} {count}")

            if data["companies"] == 0:
                print(f"\n{WARN} No companies yet. This is expected on a fresh "
                      f"install -\n         the pipeline has not been run.")
                print("         Fastest test (one company, no search key needed):")
                print("           curl -X POST http://localhost:8000/api/companies/add \\")
                print('             -H "Content-Type: application/json" \\')
                print('             -d \'{"url":"https://allbirds.com"}\'')
                print("         Or run discovery:")
                print("           curl -X POST http://localhost:8000/api/discovery/run \\")
                print('             -H "Content-Type: application/json" -d \'{"limit":20}\'')
        finally:
            db.close()
    except Exception as exc:
        print(f"{FAIL} Schema check failed: {type(exc).__name__}: {str(exc)[:200]}")
        problems.append("schema check failed")
        return False
    return True


def check_search() -> None:
    header("3. Search provider (needed for discovery)")
    import httpx

    if settings.serper_api_key:
        key = settings.serper_api_key
        masked = f"{key[:8]}...{key[-4:]}"
        if key.startswith("live_"):
            print(f"{WARN} SERPER_API_KEY = {masked}")
            print("         serper.dev keys are 40-char hex with no prefix.")
            print("         A 'live_' prefix suggests a different vendor.")
        else:
            print(f"{OK} SERPER_API_KEY set ({masked})")
        try:
            resp = httpx.post("https://google.serper.dev/search",
                              json={"q": "test", "num": 1},
                              headers={"X-API-KEY": key,
                                       "Content-Type": "application/json"},
                              timeout=20)
            if resp.status_code == 200:
                print(f"{OK} Live check passed - serper.dev accepted the key.")
            else:
                print(f"{FAIL} serper.dev returned HTTP {resp.status_code}: "
                      f"{resp.text[:150]}")
                print("         Either get a serper.dev key, or switch provider:")
                print("           SEARCH_PROVIDER=brave  + BRAVE_SEARCH_API_KEY=...")
                problems.append("search key rejected")
        except Exception as exc:
            print(f"{WARN} Could not reach serper.dev to verify: "
                  f"{type(exc).__name__}")
    elif settings.serpapi_key or settings.brave_search_api_key:
        print(f"{OK} Alternative search provider configured.")
    else:
        print(f"{WARN} No search provider key. Discovery will return nothing.")
        print("         You can still test the pipeline with /api/companies/add.")


def check_llm() -> None:
    header("4. LLM provider (optional)")
    configured = [name for name, key in (
        ("groq", settings.groq_api_key),
        ("gemini", settings.gemini_api_key),
        ("openai", settings.openai_api_key)) if key]

    if not configured:
        print(f"{WARN} No LLM key set.")
        print("         The pipeline still works: scoring runs on deterministic")
        print("         signals only and the weights renormalize automatically.")
        print("         Add GROQ_API_KEY or GEMINI_API_KEY (both have free tiers)")
        print("         to enable AI analysis, urgency and likely-need output.")
        return
    print(f"{OK} Configured: {', '.join(configured)}")

    import httpx
    if settings.groq_api_key:
        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={"model": settings.ai_model,
                      "messages": [{"role": "user", "content": "say ok"}],
                      "max_tokens": 5},
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                timeout=20)
            print(f"{OK} Groq live check: HTTP {resp.status_code}"
                  if resp.status_code == 200
                  else f"{FAIL} Groq returned {resp.status_code}: {resp.text[:150]}")
        except Exception as exc:
            print(f"{WARN} Could not reach Groq: {type(exc).__name__}")


def check_redis() -> None:
    header("5. Redis / Celery (optional)")
    try:
        import redis
        client = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        print(f"{OK} Redis reachable at {settings.redis_url}")
    except Exception:
        print(f"{WARN} Redis not reachable at {settings.redis_url}")
        print("         Not a problem: the API falls back to in-process")
        print("         background tasks. Start it with: docker compose up -d redis")


def main() -> int:
    print("=" * 62)
    print("  SETUP DOCTOR")
    print("=" * 62)

    db_ok = check_database()
    if db_ok:
        check_schema()
    else:
        header("2. Schema and seed data")
        print(f"{FAIL} Skipped - fix the database connection first.")
    check_search()
    check_llm()
    check_redis()

    print("\n" + "=" * 62)
    if problems:
        print(f"  {len(problems)} blocking issue(s):")
        for item in problems:
            print(f"    - {item}")
        print("=" * 62)
        return 1
    print("  Ready. Start the API:  uvicorn app.main:app --reload")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
