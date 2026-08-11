<<<<<<< HEAD
# Configurable B2B Intent Intelligence & Lead Discovery Platform

**V1 service: Third-Party Logistics (3PL)**

Discovers ecommerce and physical-product brands, collects public business
information, detects buying signals, scores intent, identifies the likely
decision maker, and shows the evidence behind every conclusion.

> **This platform does not discover, verify, or store email addresses.**
> A complete lead is Company + Intent + Evidence + Decision Maker.
> The constraint is enforced by tests, not by convention — see
> `backend/tests/test_no_email.py`.

---

> **Database empty / not sure how to run it?** See **[QUICKSTART.md](QUICKSTART.md)**,
> or run `cd backend && python -m scripts.check_setup` for a diagnosis.

## Quick start

```bash
# 1. Backend deps
cd backend && pip install -r requirements.txt

# 2. Add your Supabase DB password + one LLM key to backend/.env  (see below)

# 3. Create the schema and seed the 3PL configuration
python -m scripts.seed

# 4. Run the API
uvicorn app.main:app --reload      # http://localhost:8000/docs

# 5. Run the dashboard (new terminal)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

Or use the Makefile: `make install`, `make seed`, `make api`, `make frontend`.

### Try it without waiting for discovery

Open the dashboard, paste any brand's website into **Test the pipeline**, and
hit *Analyze company*. That runs crawl → classify → signals → score →
decision makers against one company so you can see the whole thing work.

---

## What you still need to fill in

Your Supabase and Serper keys are already in `backend/.env`. Three gaps remain:

| What | Where | Why |
|---|---|---|
| **Supabase DB password** | `backend/.env` → `DATABASE_URL` and `DATABASE_MIGRATION_URL` (replace `YOUR_DB_PASSWORD`) | The service-role key authenticates against the REST API; direct SQL needs the database password. Get it from Supabase → Project Settings → Database. |
| **One LLM key** | `backend/.env` → `GROQ_API_KEY` or `GEMINI_API_KEY` | Without it the pipeline still runs, but on deterministic scoring only — the AI component is skipped and weights renormalize automatically. Both vendors have free tiers. |
| **Verify the Serper key** | `backend/.env` → `SERPER_API_KEY` | See the note below. |

### ⚠️ About the Serper key

The key you supplied is `live_OgsqA9fABgwBIEwMZ1ZRXtDCUIB28Brh`.

**serper.dev keys are 40-character hex strings with no prefix.** A `live_`
prefix is the format used by several other vendors, so this key may belong to
a different service. Verify it with:

```bash
curl -X POST https://google.serper.dev/search \
  -H "X-API-KEY: live_OgsqA9fABgwBIEwMZ1ZRXtDCUIB28Brh" \
  -H "Content-Type: application/json" \
  -d '{"q":"new DTC brand","num":3}'
```

- **HTTP 200** → you're set, nothing to change.
- **HTTP 401/403** → the key is for a different vendor. Either grab a
  serper.dev key, or set `SEARCH_PROVIDER=serpapi` / `brave` and fill in the
  matching key. The `SearchProvider` abstraction means no code changes either
  way — and you can register a new vendor with
  `register_provider("myvendor", MyProvider)`.

Nothing else in the system depends on which search vendor you pick.

---

## Setting up Supabase

Two options for creating the schema:

**Option A — SQL editor (recommended).** Paste each file into the Supabase SQL
editor and run in order:

1. `backend/migrations/001_init.sql` — tables, indexes, triggers
2. `backend/migrations/002_rls.sql` — row-level security policies
3. `backend/migrations/003_seed_3pl.sql` — the 3PL service configuration

**Option B — from Python**, once `DATABASE_MIGRATION_URL` has a real password:

```bash
cd backend && python -m scripts.seed --sql
```

### RLS model

- The backend uses the **service-role key** and bypasses RLS.
- The frontend gets the **publishable key** and read-only access to
  non-personal tables.
- `decision_makers` requires an authenticated session and filters out
  suppressed people automatically.
- `crawl_jobs`, `api_usage`, `search_cache` and `suppressions` have no
  policies at all — service-role only.

**Never ship the service-role key to the browser.**

---

## Architecture

```
                    INTERNET
                        │
                   DISCOVERY          search provider abstraction
                        │
                    CRAWLER           robots.txt, rate limits, retries
                        │
                 COMPANY DATA         generic — knows nothing about 3PL
                        │
                 SIGNAL ENGINE        driven by service_signals rows
                        │
                SERVICE CONFIG  ──────┬──────────┬──────────┐
                        │            3PL     Packaging    Freight
                   AI ANALYSIS        │          │          │
                        │           config    config     config
                      SCORE
                        │
                 DECISION MAKER
                        │
                 QUALIFIED LEAD
                        │
              DASHBOARD / CSV / CRM
```

**The core principle (§70): the crawler, the company database, and the generic
intelligence engine do not know what 3PL is.** All service specificity lives in
five database tables:

| Table | Holds |
|---|---|
| `services` | weights, thresholds, AI prompt, refresh cadence |
| `service_signals` | which signals exist, their weight and decay window |
| `service_keywords` | phrases that map to signals |
| `discovery_queries` | search queries used to find candidates |
| `service_roles` | which job titles matter, and in what order |

Adding a second service means inserting rows, not writing code.
`backend/tests/test_service_config.py::test_a_second_service_needs_only_new_rows`
proves it.

---

## Project layout

```
backend/
  app/
    config.py              env-driven settings
    models.py              ORM — mirrors migrations/001_init.sql
    schemas.py             API contracts (no email fields anywhere)
    providers/
      search/              SearchProvider: serper, serpapi, brave + factory
      llm/                 LLMProvider: groq, gemini, openai + fallback chain
    engine/
      service_config.py    loads a service's config at runtime
      discovery.py         search → domains → dedupe → company rows
      crawler.py           polite crawler, robots.txt, retries, Playwright
      extractor.py         HTML → text + structured page facts
      classifier.py        ecommerce / physical / country / platform / industry
      signals.py           config-driven detection + time decay
      evidence.py          ATS job boards, SEC EDGAR, news search
      ai_analysis.py       schema-validated LLM interpretation
      scoring.py           deterministic + AI + evidence, fully traceable
      decision_makers.py   public-source people identification
      pipeline.py          orchestration + cost funnel
    api/                   FastAPI routers
    workers/               Celery tasks + beat schedule
  migrations/              SQL for Supabase
  scripts/seed.py          schema + 3PL seed
  tests/                   45 tests
frontend/
  src/pages/               Dashboard, Leads, LeadDetail
  src/components/ui.tsx    score ring, intent badges, chips
  src/lib/api.ts           typed API client
```

---

## How scoring works

Three components, combined with configurable weights (default 50/30/20):

1. **Deterministic** — signal weight × freshness decay × confidence,
   normalized to 0–100.
2. **AI** — the model's probability, used as an *adjustment*, never the verdict.
3. **Evidence quality** — citation rate, source-type diversity, and independent
   corroboration.

Design decisions worth knowing about:

- **Freshness is real.** Signals decay linearly from detection to expiry.
  Funding from 500 days ago scores near zero; `recalculate_scores_task` runs
  nightly so decay applies even when nothing was re-crawled.
- **The AI cannot manufacture a HOT lead.** At 30% weight, a maximally
  confident model moves the score by at most ~30 points. There's also a
  guardrail that clamps high probabilities when there are no supporting
  signals.
- **A missing LLM key doesn't silently cap every score.** Weights renormalize
  when the AI component is unavailable.
- **Required signals cap rather than reject.** A company without both
  `ecommerce` and `physical_products` is capped at 45 — visible, but never
  presented as HOT.
- **An incumbent 3PL subtracts, it doesn't disqualify.** They may need overflow,
  a second location, or international fulfillment.

Every point appears in `score_breakdown` and renders on the lead detail page.

### Cost control

The funnel in `pipeline.py` keeps spend down:

```
discovered domains
  → crawl + classify        cheap, no paid API
  → reject early            reason recorded, never reprocessed
  → detect signals          cheap, config-driven
  → external evidence       SERP calls, classified companies only
  → AI analysis             only above ai_analysis_min_raw_score (25)
  → score
  → decision makers         only above decision_maker_threshold (80)
```

Search results are cached in Postgres for a week. Unchanged pages are detected
by `content_hash` and skipped. Token counts and estimated cost are logged per
call in `api_usage`, so cost-per-qualified-lead is computable.

---

## Free data sources already wired up

No API key required for any of these:

- **Greenhouse, Lever, Ashby, Workable, Recruitee** — public JSON job-board
  endpoints. This is where the highest-weight signals (`fulfillment_hiring` at
  20, `operations_hiring` at 15) come from.
- **SEC EDGAR full-text search** — Form D filings indicate US private funding
  rounds.
- **Platform fingerprinting** — Shopify/Woo/BigCommerce/Magento detected from
  HTML markers, no BuiltWith subscription needed.

---

## Compliance

The system stores named individuals, which makes you a data controller under
GDPR/UK GDPR if any subject is in the EU/UK. What's built in:

- `suppressions` table checked before every decision-maker write
- `POST /api/admin/suppressions` — right to object; also deletes existing records
- `DELETE /api/admin/decision-makers/{id}` — erasure
- `enforce_retention_task` — weekly sweep dropping records for cold companies
- Source URL and confidence label stored on every person record
- robots.txt honoured as a hard gate; skipped fetches recorded, not hidden
- Custom User-Agent with a contact URL

**Still your job before you sell access:** a Legitimate Interests Assessment, a
published privacy policy, and a documented retention period. Worth a short
consult with a privacy lawyer. This is not legal advice.

---

## Background processing

```bash
docker compose up -d redis
make worker    # celery worker
make beat      # celery scheduler
```

Schedule (`app/workers/celery_app.py`):

| Task | Cadence |
|---|---|
| `discover_companies` | daily 02:00 |
| `process_queue_task` | hourly |
| `recalculate_scores_task` | daily 03:00 (applies freshness decay) |
| `refresh_stale_task` | daily 04:30 (cadence by intent level) |
| `prune_cache_task` | daily 05:00 |
| `enforce_retention_task` | weekly (GDPR) |

**Redis is optional.** If Celery isn't reachable, the API falls back to FastAPI
`BackgroundTasks` — the endpoints never block on crawling or LLM calls either
way.

---

## API

Full interactive docs at `/docs`. Core routes:

```
GET    /api/services
GET    /api/services/{ref}/config          resolved config the engine uses
GET    /api/companies
GET    /api/companies/{id}/signals
GET    /api/companies/{id}/sources
GET    /api/companies/{id}/decision-makers
GET    /api/services/{ref}/opportunities   lead list, all filters
GET    /api/services/{ref}/opportunities/{id}
POST   /api/discovery/run
POST   /api/crawl/{company_id}
POST   /api/analyze/{company_id}
POST   /api/companies/add                  seed one company by URL
GET    /api/export                         CSV
GET    /api/stats                          dashboard metrics
GET    /api/stats/health                   setup checklist
```

Admin routes under `/api/admin/*` require the `X-Admin-Token` header (matches
`SECRET_KEY`). Replace with Supabase Auth JWT verification before production.

---

## Testing

```bash
cd backend && pytest
```

45 tests, covering the parts most worth getting right: scoring maths, freshness
decay, the AI-cannot-dominate guarantee, required-signal capping, domain
normalization and blocklists, signal evidence being verbatim, decision-maker
ranking and suppression, and the no-email constraint at both the schema and
export layers.

---

## Deployment

| Component | Host |
|---|---|
| Frontend | Vercel — `VITE_API_BASE_URL` = your API URL |
| API + workers | Railway / Render — needs a long-running process, not serverless |
| Database | Supabase |
| Redis | Railway add-on or Upstash |
| Errors | Sentry — set `SENTRY_DSN` |

If you enable `PLAYWRIGHT_ENABLED`, budget 1–2 GB RAM per worker and run it as
a separate service — it will drive your hosting bill more than any API.

---

## Next steps

1. Fill in the DB password and an LLM key; run `python -m scripts.seed`.
2. Verify the Serper key with the curl above.
3. Add 5–10 companies you already know are good 3PL prospects via
   `POST /api/companies/add`. Check whether they score STRONG or HOT — if they
   don't, tune weights in `service_signals` rather than changing code.
4. Run discovery, label ~100 leads in the UI, then measure HOT/STRONG precision
   before adding a second service.
=======
# 3PL-scraper
>>>>>>> 29488e56206cd7a8994f9b5da41ee51af614a728
