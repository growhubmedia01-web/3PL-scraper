# Technical Documentation

**Configurable B2B Intent Intelligence & Lead Discovery Platform**
V1 service: Third-Party Logistics (3PL) — architecture supports additional services via configuration only.

Audience: engineers picking up, extending, or operating this system.

---

## 1. What the system does, mechanically

Given nothing but a set of search queries, the system:

1. **Discovers** candidate company domains via search-engine queries.
2. **Crawls** each domain's public pages (politely, respecting `robots.txt`).
3. **Classifies** each company — ecommerce? physical goods? platform? country? business model?
4. **Detects signals** — configurable, evidenced facts ("hiring a warehouse manager", "recently funded", "outgrowing our warehouse").
5. **Gathers external evidence** — public job boards (ATS APIs), SEC EDGAR filings, news/SERP search — beyond the company's own site.
6. **Scores intent** — a weighted blend of deterministic signal strength, an optional LLM's contextual read, and evidence quality — fully traceable line-by-line.
7. **Identifies likely decision makers** — names + titles extracted from the company's own team/leadership pages, press releases, and job posts. **No email addresses, ever.**
8. **Surfaces qualified leads** through a REST API and a React dashboard, with CSV export.

Everything runs as a cost-gated funnel (§ Cost control below) so a nightly discovery run doesn't produce a runaway API bill.

---

## 2. Repository layout

```
backend/
  app/
    config.py              env-driven Settings (pydantic-settings), single source of truth
    models.py               SQLAlchemy ORM — mirrors migrations/001_init.sql
    schemas.py               Pydantic API request/response contracts (no email fields anywhere)
    db.py, deps.py            session/engine setup, FastAPI dependencies
    providers/
      search/                SearchProvider abstraction: serper, serpapi, brave, exa + factory
      llm/                    LLMProvider abstraction: groq, gemini, openai + fallback chain
    engine/
      service_config.py       loads a service's DB-stored config into a typed object at runtime
      discovery.py             search -> domains -> dedupe -> Company rows
      crawler.py                polite crawler: robots.txt, retries, optional Playwright
      extractor.py               HTML -> ExtractedPage (text, JSON-LD, scripts, page_type)
      classifier.py               "what IS this company?" — service-agnostic
      signals.py                   config-driven signal detection + freshness decay
      evidence.py                   ATS job boards, SEC EDGAR, news/SERP search
      ai_analysis.py                 schema-validated LLM interpretation, with guardrails
      scoring.py                      deterministic + AI + evidence -> final score, fully traceable
      decision_makers.py               public-source people identification (no email)
      pipeline.py                       orchestrates the funnel above; per-company fault isolation
    api/                       FastAPI routers (see §6)
    workers/                    Celery tasks + beat schedule
  migrations/                  raw SQL for Supabase (run in order: 001, 002, 003, …)
  scripts/
    seed.py                     creates schema + seeds the 3PL service config
    drain_queue.py               operational helper for free-tier hosts (see docs/DRAINING_THE_QUEUE.md)
    check_setup.py                diagnoses a broken local setup
  tests/                        45 tests
frontend/
  src/pages/                    Dashboard, Leads, LeadDetail
  src/components/ui.tsx          score ring, intent badges, chips
  src/lib/api.ts                  typed API client
  src/lib/types.ts                 shared TS types mirroring backend schemas
docs/
  ARCHITECTURE.md               the service-agnostic design principle, layer boundaries
  SEGMENTS.md                    which company segments are targeted and why (3PL-specific)
  RUNBOOK.md                      first-run steps, common problems, tuning without deploying
  DRAINING_THE_QUEUE.md            operating the synchronous queue processor on free-tier hosts
  QUERY_LIBRARY.md                 the discovery query set
```

---

## 3. The core design principle: service-agnostic engine

**The crawler, the company database, and the generic intelligence engine do not know what "3PL" is.** All service-specific knowledge — signal weights, which job titles matter, score thresholds, the AI prompt, discovery queries — lives in five database tables, not in code:

| Table | Holds |
|---|---|
| `services` | weights, thresholds, AI system prompt, refresh cadence (as JSONB `config`) |
| `service_signals` | which signals exist for this service, their weight and decay window |
| `service_keywords` | phrases that map to a signal |
| `discovery_queries` | search queries used to find candidates for this service |
| `service_roles` | which job titles matter, and their priority order |

Adding a second service (e.g. "Packaging", "Freight") means **inserting rows**, not writing code — proven by `backend/tests/test_service_config.py::test_a_second_service_needs_only_new_rows`. `default_service_slug` in `config.py` is the only place "3pl" appears in application code (plus one docstring); grep for the exact test in `docs/ARCHITECTURE.md`.

Layer boundaries enforced by convention and tests:

| Layer | Knows about | Never knows about |
|---|---|---|
| `utils/` | URLs, text, robots.txt | services, signals, scoring |
| `providers/` | vendor APIs | what a company is |
| `engine/crawler,extractor` | HTML, HTTP | services |
| `engine/classifier` | what a company IS | whether it's a good lead |
| `engine/signals,scoring` | `ServiceConfig` | which service it is |
| `engine/pipeline` | orchestration | vendor details |
| `api/` | HTTP contracts | crawling internals |

`classifier.py` answers "what is this company?"; `scoring.py` answers "is it a good lead for service X?" — kept separate so company intelligence (crawl once, understand once) is reusable across future services.

---

## 4. Data model

Two logical groups of tables (see `backend/app/models.py`, mirrored by `backend/migrations/001_init.sql`):

### Service configuration (drives behavior, no code changes needed)
`services`, `service_signals`, `service_keywords`, `discovery_queries`, `service_roles`.

### Generic company intelligence (shared across every service)
- **`companies`** — domain (unique), name, country (+confidence), industry, `is_ecommerce`, `is_physical_product`, `platform` (Shopify/Woo/etc.), `business_model` (dtc/wholesale/manufacturer/retail/marketplace/subscription/importer/multi_channel), `sales_channels` (JSON list), `status` (discovered → queued → classified/rejected), `rejection_reason`, `linkedin_url`/`linkedin_source`/`linkedin_checked_at` (see §7 addendum).
- **`sources`** — every page or external document that contributed evidence; unique per `(company_id, url)`; carries `content_hash` for change detection.
- **`crawl_jobs`** — one row per fetch attempt: status (`pending`/`ok`/`skipped`/`failed`), HTTP status, error, attempt count. Robots-blocked fetches are `skipped`, not `failed`.
- **`signals`** — a detected, evidenced, time-bounded fact about a company *for a specific service* (`service_id` FK). Carries `strength`, `confidence`, `detected_at`/`expires_at`, and a `source_id` for citation.
- **`service_opportunities`** — one row per `(company, service)`: `score`, `raw_score`, `deterministic_score`, `ai_score`, `evidence_score`, `score_breakdown` (JSON, full arithmetic), `intent_level` (LOW/POSSIBLE/GOOD/STRONG/HOT), `urgency`, `likely_need`, `target_country`, `reasoning`.
- **`decision_makers`** — `name`, `job_title`, `profile_url` (the *source page* it was found on, not a third-party profile), `source`/`source_id`, `confidence`/`confidence_label`, `role_priority`. **No email column exists on this table — a deliberate constraint, enforced by `backend/tests/test_no_email.py`, not just convention.**
- **`suppressions`** — GDPR right-to-object list, checked before every `decision_makers` write.
- **`search_cache`** — Postgres-backed cache of search results, TTL default 7 days.
- **`pipeline_runs`** — one row per discovery/queue-processing invocation; backs the `/api/pipeline/status` observability endpoint.
- **`api_usage`** — per-call token counts and estimated cost, tagged by provider/operation/company — feeds cost-per-qualified-lead reporting.
- **`lead_reviews`** — human labels (excellent/good/maybe/bad) on opportunities, used to measure precision per intent level.

`GUID` is a custom SQLAlchemy type: native `UUID` on Postgres, `CHAR(36)` elsewhere (so the same models work against local SQLite in dev).

---

## 5. Pipeline stages in detail

`backend/app/engine/pipeline.py::process_company` runs these stages for one company, in order, stopping early wherever there's nothing left to gain:

1. **Crawl** (`crawler.py`) — reuses stored pages unless `force_crawl` or the company was never crawled; otherwise fetches up to `crawl_max_pages_per_company` (default 12), respecting `robots.txt`, with a configurable delay, timeout, and retry count. Wall-clock budget per company: `crawl_max_seconds_per_company` (default 45s).
2. **Classify** (`classifier.py`) — service-agnostic. Rejects competitors/service businesses first (a 3PL's own site is full of fulfillment vocabulary and would otherwise score well). Then detects:
   - platform fingerprint (Shopify/WooCommerce/BigCommerce/Magento/Squarespace/Wix/PrestaShop/Salesforce Commerce/Shopware/Webflow) via markers in HTML/scripts.
   - ecommerce (≥2 pieces of corroborating evidence: platform fingerprint, cart/checkout markers, `schema.org:Product` JSON-LD, cart/checkout/product URLs).
   - **physical-product qualification gate** — tiered evidence, not flat counting. One *decisive* marker ("minimum order quantity", "our factory", "container shipments", a shipping/returns policy page, `schema.org:Product`) qualifies alone; weaker markers need ≥2 and must outweigh SaaS/service markers. This deliberately qualifies wholesalers, manufacturers, and retail-distributed brands with no online cart at all, not just DTC ecommerce.
   - business model (`wholesale`, `manufacturer`, `subscription`, `marketplace`, `retail`, `importer`, `dtc`) — ranked by number of distinct markers; ≥3 matched channels → tagged `multi_channel`.
   - country — weighted vote across TLD, address text/phrases, postcode format, and detected currency.
   - industry — keyword scoring across apparel/beauty/food & beverage/home/electronics/health/pet/toys/sports/jewellery.
   - Non-physical (SaaS/agency/consulting) companies and 3PL/freight/agency competitors are rejected here, with a stored `rejection_reason`, so they are never blindly reprocessed.
3. **External evidence** (`evidence.py`) — three independent, free, unauthenticated sources:
   - **ATS job boards** — Greenhouse, Lever, Ashby, Workable, Recruitee public JSON endpoints, probed by slug candidates derived from the company name/domain. Capped at 2 slug candidates × a 4s timeout × a 24s hard ceiling per company (previously up to 225s — see `docs/DRAINING_THE_QUEUE.md`).
   - **SEC EDGAR full-text search** — free, no API key; a Form D filing indicates a US private funding round.
   - **News/SERP search** — via the `SearchProvider` abstraction, templated queries for funding, news, press releases (launches/expansion), and crowdfunding. Results are filtered to require the company name actually appearing in the snippet, and to exclude the company's own domain.
   All discovered items are persisted as `sources` rows (deduplicated by URL) so later stages can cite them.
4. **Signal detection** (`signals.py`) — config-driven: `service_signals` and `service_keywords` rows, loaded per service via `ServiceConfig`, determine what to look for and how much it's worth. Every detected signal must carry a `source_id` (§29 in the code's internal spec numbering) — nothing is scored without a citation.
5. **Provisional score** — computed once, cheaply, to decide whether the AI call (which costs money) is worth making at all.
6. **AI analysis** (`ai_analysis.py`) — only runs if `provisional.raw_score >= ai_analysis_min_raw_score` (default 25). Sends signals + evidence excerpts (capped at 12,000 chars) to the configured LLM, in JSON mode, with a strict Pydantic schema (`AIAnalysis`) the response must satisfy. Guardrails:
   - malformed/unparseable output → treated as "no AI analysis" (pipeline continues on deterministic scoring, doesn't fail);
   - the model is told to use *only* the evidence given, not outside knowledge;
   - if the model claims `service_probability > 0.4` with **zero** detected signals, it's clamped to 0.2 and flagged in `evidence_gaps` — a hallucinated high-confidence read can't manufacture a HOT lead.
7. **Final score** (`scoring.py`) — see §7 below.
8. **Decision makers** (`decision_makers.py`) — only runs if `final.score >= decision_maker_threshold` (default 80), to control cost. See §8 below.

Every company is processed independently and committed independently (`process_batch` commits per company) — one bad site never aborts a batch, and a batch cut short by a time budget keeps everything it already did.

---

## 6. Scoring model

Three components, weighted (default 50% deterministic / 30% AI / 20% evidence, configurable per service):

**Deterministic** — for each detected signal: `weight × freshness_multiplier × confidence`, summed, then normalized against a configurable `normalization_ceiling` (default 110, so ~110 raw points = 100/100). Freshness decays linearly from `detected_at` to `expires_at`; negative signals (e.g. `existing_3pl`, weight −20) are exempt from decay and apply at full weight scaled only by confidence — an incumbent provider doesn't become "less true" over time, it just doesn't disqualify (they may need overflow capacity, a second location, or international fulfillment).

**AI** — the model's `service_probability` (0–1), scaled to 0–100, used as one weighted input, never the verdict.

**Evidence quality** — `100 × (0.45 × citation_rate + 0.30 × source_type_diversity + 0.25 × independent_source_types)`. Rewards signals that cite a source, a diversity of source types, and off-site (independent) corroboration.

**Combination**:
```
final = w_det × deterministic_normalized + w_ai × ai_normalized + w_ev × evidence_score
```
If no LLM is configured (or the call failed), weights renormalize across deterministic+evidence only — `w_ai` becomes 0 rather than silently capping every score ~30 points low.

**Required-signal cap** — a service can declare `required_signals` (e.g., for 3PL: `physical_products`). Missing any of them caps the final score at 45, regardless of how high the other components run — visible in the lead list, but never presented as HOT.

**Intent levels** — `LOW` / `POSSIBLE` / `GOOD` / `STRONG` / `HOT`, driven by configurable thresholds (`intent_thresholds` in `services.config`).

Every contributing line (per-signal points, the AI contribution, the evidence contribution, any cap applied) is stored in `score_breakdown` (JSON) on `service_opportunities` and rendered on the lead detail page — the score is always auditable back to its exact arithmetic, not a black box.

---

## 7. Decision-maker identification — no email, by design

`decision_makers.py` extracts **name + job title** pairs using three regex patterns run only against the company's own "about"/"team"/"leadership"/"careers"/press-release/job pages:

- `NAME_THEN_TITLE` — "Jane Smith, COO"
- `TITLE_THEN_NAME` — "COO: Jane Smith"
- `QUOTE_ATTRIBUTION` — "said Jane Smith, COO of Example Brand"

Candidates are filtered against a plausible-name heuristic (2–3 capitalized words, no digits, not a known stopword phrase like "our team" or "customer service"), then checked against the service's `service_roles` (only roles the service cares about are kept, in priority order).

**Confidence labeling**: `confirmed` (0.92) if found on a URL matching `/about|team|leadership|our-story|people|founders|management|who-we-are/`; `likely` (0.78) on another about/website page or a press-release quote (0.72); `possible` (0.55 or 0.5) if only found on a job posting or looser context.

Every candidate is checked against `suppressions` (GDPR right-to-object, by name or by company domain) before being written. Records are unique per `(company_id, name, job_title)`; re-detection with higher confidence updates the existing row rather than duplicating it.

**`profile_url` stores the page the person was found on — the company's own website — not a LinkedIn or other third-party profile URL.** There is no LinkedIn scraper, LinkedIn API integration, or third-party people-enrichment call (Clearbit/Apollo/Hunter/Proxycurl/etc.) for *people* anywhere in this codebase; `linkedin.com` appears in `utils/urls.py::BLOCKED_DOMAINS`, where it (and other social/aggregator domains) is rejected as a *candidate company domain* during discovery, unrelated to profile lookup.

This constraint is enforced structurally, not just by convention: `DecisionMaker` has no email column, and `backend/tests/test_no_email.py` asserts the absence at both the schema and CSV-export layers.

### Company LinkedIn URL resolution (distinct from the above)

`engine/linkedin.py` resolves a company's *own official LinkedIn page* (`companies.linkedin_url`) — separate from decision-maker/people enrichment above, which still never touches LinkedIn. Two tiers, cheapest first:

- **Tier 1 (free)** — `extract_company_linkedin_url()` scans data already captured during the normal crawl: `schema.org` `Organization`/`Corporation` json_ld `sameAs` arrays (checked first — structured, company-published), then any `linkedin.com/company/...` link already present in the page's own anchor tags (`ExtractedPage.links`, previously captured but unused for this). Zero extra HTTP requests.
- **Tier 2 (fallback)** — `search_company_linkedin_url()`, only if tier 1 finds nothing and external calls aren't disabled for the run: one `site:linkedin.com/company "{name}"` query through the existing `SearchService` (same caching/provider-pool infrastructure as everything else in `evidence.py`).

Both tiers restrict matches to `/company/` paths only (`_is_linkedin_company_url()`), explicitly excluding `/in/` (personal profiles — must never surface here, same constraint as `DecisionMaker.profile_url`), `/school/`, `/jobs/`, `/posts/`. `companies.linkedin_source` records which tier resolved it (`json_ld` / `site_link` / `search`). `companies.linkedin_checked_at` is a repeat-spend guard: tier 2 fires at most once ever per company, regardless of whether it found anything, so re-processing never repeats the search-provider call. `resolve_company_linkedin()` runs in `pipeline.py` right after classification (rejected companies are never resolved), unconditionally for every classified company — not score-gated like AI analysis or decision-maker research, since it's cheap identity resolution rather than intent scoring. LinkedIn itself is never fetched directly by any of this.

---

## 8. Provider abstractions

Both external-vendor integrations follow the same pattern — a small interface, several implementations, a factory, and a config-driven default with automatic fallback:

**`providers/search/`** — `SearchProvider` interface; implementations for `serper`, `serpapi`, `brave`, `exa`. Selected by `SEARCH_PROVIDER` env var. Supports multi-key rotation (`SERPER_API_KEYS`, `EXA_API_KEYS` comma-separated). Results are cached in `search_cache` (Postgres) for `SEARCH_CACHE_TTL_HOURS` (default 168h/7d). Registering a new vendor requires no code changes to callers — `register_provider("myvendor", MyProvider)`.

**`providers/llm/`** — `LLMProvider` interface; implementations for `groq`, `gemini`, `openai`. `AI_PROVIDER` sets the primary; `AI_FALLBACK_PROVIDERS` (default `gemini,openai`) is tried in order if the primary fails. Every call is logged to `api_usage` with token counts and estimated cost.

---

## 9. API surface

FastAPI app in `backend/app/main.py`; interactive docs at `/docs`. Routers under `backend/app/api/`:

| Router | Purpose |
|---|---|
| `services.py` | `GET /api/services`, `/{ref}`, `/{ref}/signals`, `/{ref}/keywords`, `/{ref}/queries`, `/{ref}/roles`, `/{ref}/config` (the fully resolved runtime config) |
| `companies.py` | `GET /api/companies`, `/{id}`, `/{id}/signals`, `/{id}/sources`, `/{id}/decision-makers` |
| `opportunities.py` | `GET /api/services/{ref}/opportunities` (paginated, filterable lead list), `/{id}` (full detail incl. score breakdown), `POST /{id}/review` (label a lead) |
| `pipeline.py` | `POST /api/discovery/run`, `/api/crawl/{company_id}`, `/api/analyze/{company_id}`, `/api/pipeline/process-queue` (time-bounded batch, see §10), `/api/companies/add` (seed one company by URL), `GET /api/pipeline/status`, `/api/pipeline/runs`, `/api/discovery/queries` |
| `stats.py` | `GET /api/stats` (dashboard metrics), `/api/stats/health` (setup checklist: DB/search/LLM configured?) |
| `export.py` | `GET /api/export` — CSV, no email fields |
| `admin.py` | `X-Admin-Token`-gated CRUD over `services`/`signals`/`queries`/`keywords`/`roles`/`suppressions`, plus `POST /run-migration` |

Admin routes currently authenticate via a shared `X-Admin-Token` header matched against `SECRET_KEY`; the README flags this as something to replace with real auth (Supabase Auth JWT verification) before production use with untrusted admins.

---

## 10. Background processing & operational model

**Celery** (`workers/celery_app.py`) with a beat schedule:

| Task | Cadence | Purpose |
|---|---|---|
| `discover_companies` | daily 02:00 | tier-1 discovery queries, least-recently-run first |
| `process_queue_task` | hourly (`:15`) | crawl/classify/score queued companies |
| `recalculate_scores_task` | daily 03:00 | re-score from stored signals — applies freshness decay without re-crawling |
| `refresh_stale_task` | daily 04:30 | re-crawl companies whose refresh cadence (by intent level) has elapsed |
| `prune_cache_task` | daily 05:00 | drop expired `search_cache` rows |
| `enforce_retention_task` | weekly (Sun 06:00) | GDPR: drop decision-maker records for companies gone cold (>365 days) |

**Redis is optional.** If Celery isn't reachable, the API falls back to FastAPI `BackgroundTasks`; on hosts that kill background tasks the moment the HTTP response flushes (e.g. Render/Railway free tiers), `process-queue` instead runs **synchronously**, bounded by wall-clock time rather than a company count — `POST /api/pipeline/process-queue?limit=8&max_seconds=240` stops cleanly at the deadline, commits per company, and reports `stopped_reason: "time_budget_reached"` (not an error — call it again). See `docs/DRAINING_THE_QUEUE.md` for the full operational playbook, including `scripts/drain_queue.py`, a loop that drains the queue against a live (possibly cold-starting, possibly flaky) deployment, and `GET /api/pipeline/status` for confirming a cron scheduler is actually firing.

**Cost guards** (`config.py`): `max_companies_per_discovery_run` (200), `max_queries_per_discovery_run` (50), `max_ai_calls_per_run` (100) — hard ceilings independent of the per-company time budget.

---

## 11. Configuration reference (`backend/app/config.py`)

All settings are environment-driven via `pydantic-settings`, loaded from `backend/.env`. Key groups:

- **Core**: `environment`, `secret_key`, `admin_emails`, `cors_origins`.
- **Database**: `database_url` / `database_migration_url` — accepts bare `postgres://` or `postgresql://` and rewrites to `postgresql+psycopg://`; auto-detects and percent-encodes unescaped special characters in a pasted Supabase password (a common source of a misleading DNS-looking error — see the docstring in `_fix_unencoded_password`).
- **Search**: `search_provider`, per-vendor keys, `search_cache_ttl_hours`, `search_max_results`.
- **LLM**: `ai_provider`, `ai_fallback_providers`, `ai_model`, `ai_temperature`, `ai_max_tokens`, `ai_timeout`, per-vendor keys.
- **Crawler**: `crawler_user_agent` (should include a contact URL), `crawl_concurrency`, `crawl_delay_seconds`, `crawl_timeout_seconds`, `crawl_max_retries`, `crawl_max_pages_per_company`, `crawl_max_seconds_per_company`, `respect_robots_txt` (hard gate, always on by default), `playwright_enabled`.
- **External signal sources**: `companies_house_api_key`, `sec_edgar_user_agent`.
- **Infra**: `redis_url`, `sentry_dsn`.
- **Scoring defaults**: `score_weight_deterministic/ai/evidence`, `decision_maker_threshold`, `ai_analysis_min_raw_score` — all overridable per-service via the `services.config` JSONB.
- **Cost guards**: as above.
- **`default_service_slug`**: the only "3pl" reference in application code; the entire product retargets by pointing this elsewhere and seeding a new service's rows.

---

## 12. Compliance & data-protection mechanisms (technical view)

Storing named individuals makes the operator a data controller under GDPR/UK GDPR for any EU/UK subject. What's structurally enforced, not just documented:

- **No email** anywhere in the pipeline or schema — `test_no_email.py` checks the ORM schema and the CSV export layer.
- **`suppressions`** table, checked before every `decision_makers` write; `POST /api/admin/suppressions` implements right-to-object and deletes existing matching records; `DELETE /api/admin/decision-makers/{id}` implements erasure.
- **`enforce_retention_task`** — weekly sweep dropping decision-maker records for companies with no recent activity (default 365-day threshold).
- Every `decision_makers` row carries `source_id`/`source` and a `confidence_label` — provenance and confidence are never dropped.
- `robots.txt` is honored as a hard gate (`respect_robots_txt`, default true); a robots-blocked fetch is recorded as `skipped` in `crawl_jobs`, distinct from `failed`, so compliance and reliability failures aren't conflated in metrics.
- `crawler_user_agent` is expected to include a contact URL.

**Not automated, and explicitly called out in the README as the operator's responsibility**: a Legitimate Interests Assessment, a published privacy policy, a documented retention period. Not legal advice.

---

## 13. Testing

```bash
cd backend && pytest
```

45 tests covering: scoring arithmetic, freshness decay, the "AI cannot dominate the score" guarantee, required-signal capping, domain normalization and the blocklist, signal evidence being verbatim (not paraphrased/hallucinated), decision-maker ranking and suppression, the no-email constraint at both schema and export layers, and `test_a_second_service_needs_only_new_rows` (proves the service-agnostic claim in §3).

---

## 14. Deployment

| Component | Typical host |
|---|---|
| Frontend | Vercel (`VITE_API_BASE_URL` → API URL) |
| API + workers | Railway / Render — needs a long-running process; not a good fit for pure serverless given the synchronous-queue fallback in §10 |
| Database | Supabase (Postgres) |
| Redis | Railway add-on or Upstash (optional — see §10) |
| Errors | Sentry (`SENTRY_DSN`) |

`PLAYWRIGHT_ENABLED=true` (for JS-rendered sites the plain crawler can't parse) should run as its own service — budget 1–2GB RAM per worker; it will dominate the hosting bill more than any API call.

### RLS model (Supabase)
- Backend uses the **service-role key**, bypasses RLS entirely.
- Frontend gets the **publishable key**, read-only, non-personal tables only.
- `decision_makers` requires an authenticated session and filters suppressed people automatically.
- `crawl_jobs`, `api_usage`, `search_cache`, `suppressions` have **no policies at all** — service-role access only.
- The service-role key must never reach the browser.

---

## 15. Known operational sharp edges

- **Free-tier hosting kills background tasks on response flush.** `process-queue` must run synchronously and be time-bounded, not count-bounded — see §10 and `docs/DRAINING_THE_QUEUE.md`. `limit=50` alone was previously capable of a 32-minute-to-several-hour request.
- **PgBouncer + prepared statements.** Recent fixes (see git history) set `prepare_threshold=None` via a SQLAlchemy `connect` event listener to fully disable server-side prepared statements — required when connecting through PgBouncer in transaction-pooling mode, where prepared statements between requests cause `InvalidSqlStatementName` errors.
- **ATS probing cost.** Originally up to 225s per company (3 slugs × 5 vendors × 15s timeout) against endpoints that mostly 404; capped to ≤24s (2 slugs, 4s timeout) — see `evidence.py::ATS_TIMEOUT_SECONDS`/`ATS_MAX_SLUG_CANDIDATES`.
- **A missing LLM key doesn't uniformly suppress scores** — weights renormalize (§6) — but the contextual lift the AI component provides for borderline companies is genuinely gone without it.
