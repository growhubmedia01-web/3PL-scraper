# Runbook

## First run

```bash
cd backend
pip install -r requirements.txt
# edit .env: DATABASE_URL password + one LLM key
python -m scripts.seed
uvicorn app.main:app --reload
```

Check `GET /api/stats/health` — it returns a setup checklist:

```json
{"database": {"ok": true, "url_configured": true},
 "search": {"ok": true, "providers": ["serper"]},
 "llm": {"ok": false, "providers": []}}
```

## Local development without Supabase

```bash
cd backend
DATABASE_URL="sqlite+pysqlite:///./local.db" python -m scripts.seed --local
DATABASE_URL="sqlite+pysqlite:///./local.db" uvicorn app.main:app --reload
```

Everything works except Postgres-specific RLS.

## Common problems

**"Service '3pl' not found"** — the seed didn't run. `python -m scripts.seed`.

**Discovery returns 0 companies** — check `/api/stats/health` for
`search.ok: false`, then verify your search key. Also normal if every result
was a marketplace/social domain; those are blocked by design in
`utils/urls.py::BLOCKED_DOMAINS`.

**Every company gets rejected** — check `companies.rejection_reason`. Usually
"no ecommerce or physical-product evidence found", which is correct for SaaS
and agencies. If legitimate stores are being rejected, they're probably
JS-rendered: set `PLAYWRIGHT_ENABLED=true` and
`pip install -r requirements-optional.txt && playwright install chromium`.

**Scores all clustered near 45** — that's the required-signals cap. Those
companies are missing `ecommerce` or `physical_products`.

**Scores feel too low across the board** — check whether AI is running.
Without an LLM key the AI component is skipped (weights renormalize, but the
lift from contextual assessment is gone). Also check
`ai_analysis_min_raw_score` — companies below it never reach the model.

**Crawl success rate is low** — inspect `crawl_jobs.error`. Timeouts mean you
should raise `CRAWL_TIMEOUT_SECONDS`; a wall of `skipped` means robots.txt is
blocking you, which you must respect.

## Tuning weights without deploying

```bash
curl -X PATCH http://localhost:8000/api/admin/signals/{signal_id} \
  -H "X-Admin-Token: $SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"weight": 25}'

# then re-score everything from stored signals (no re-crawl, no API cost)
celery -A app.workers.celery_app call app.workers.tasks.recalculate_scores_task
```

## Validation loop (Phase 9)

1. Label ~100 leads via the lead detail page (excellent / good / maybe / bad).
2. Query precision:

```sql
select o.intent_level,
       count(*) filter (where r.label in ('excellent','good')) as good,
       count(*) as total,
       round(100.0 * count(*) filter (where r.label in ('excellent','good'))
             / count(*), 1) as precision_pct
from lead_reviews r
join service_opportunities o on o.id = r.opportunity_id
group by o.intent_level order by 4 desc;
```

3. Cost per qualified lead:

```sql
select (select sum(cost_usd) from api_usage)
     / nullif((select count(*) from service_opportunities
               where intent_level in ('HOT','STRONG')), 0) as cost_per_lead;
```

Only add a second service once HOT precision is acceptable.
