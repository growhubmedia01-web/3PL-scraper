# Master Project Documentation
# Configurable B2B Intent Intelligence & Lead Discovery Platform

**Default service: Powersports Aftermarket Product Sourcing** (see `docs/POWERSPORTS_SOURCING.md`).
**Legacy service: Third-Party Logistics (3PL)** - retained inactive; sections describing it are kept for reference.

---

## Executive Summary & System Purpose

The **Configurable B2B Intent Intelligence & Lead Discovery Platform** is an enterprise-grade automated intelligence system that identifies companies in need of specific B2B services (initially 3PL / Third-Party Logistics) **before** they actively go shopping or issue RFPs.

Instead of relying on static databases or broad lead lists, the platform continuously monitors public signals across the web—such as job postings (e.g., hiring a warehouse manager), funding rounds, warehouse expansion announcements, or mentions of outgrowing current fulfillment capacity. It validates, scores, and contextualizes these buying signals to deliver ranked, evidence-backed sales opportunities.

### Core Philosophy & Anti-Spam Constraints

1. **Company + Intent + Evidence + Decision Maker = Lead**: A qualified lead must be substantiated by verifiable public evidence.
2. **Strict No-Email Policy**: The platform **does not discover, verify, or store individual email addresses**. This constraint is enforced at both the database schema level and in automated build tests (`backend/tests/test_no_email.py`).
3. **No Social Scraping**: Decision maker names and titles are extracted exclusively from companies' official public pages (About, Team, Leadership, Press Releases, Careers). The system does not scrape LinkedIn or third-party people brokers.
4. **Service-Agnostic Engine**: The backend execution pipeline (crawling, classification, evidence extraction, AI analysis, scoring) contains zero 3PL-specific logic. All domain-specific signals, query templates, scoring weights, and roles are driven dynamically via database configuration.

---

## 1. System Architecture & Design Principles

```
+-------------------------------------------------------------------------------+
|                               FRONTEND (React + TS + Tailwind)               |
|                           Dashboard | Leads | Lead Detail                     |
+-------------------------------------------------------------------------------+
                                       | HTTP REST API
+-------------------------------------------------------------------------------+
|                               BACKEND (FastAPI + Pydantic)                    |
|  +-------------------+  +---------------------+  +-------------------------+  |
|  | API Routers       |  | Service Engine      |  | Worker Scheduler        |  |
|  | /companies        |  | - Crawler           |  | - Celery / Beat         |  |
|  | /opportunities    |  | - Classifier        |  | - Time-bounded Queue    |  |
|  | /pipeline         |  | - Signal Engine     |  |   Processor             |  |
|  | /admin            |  | - Scoring Engine    |  +-------------------------+  |
|  +-------------------+  +---------------------+                               |
|          |                         |                                          |
|  +-------------------------------------------------------------------------+  |
|  | Providers (Search: Serper/Brave/Exa | LLM: Groq/Gemini/OpenAI)          |  |
|  +-------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------+
                                       |
+-------------------------------------------------------------------------------+
|                               DATABASE (Supabase / PostgreSQL)               |
|  Service Config Tables                | Generic Intelligence Tables           |
|  - services, service_signals          | - companies, sources, crawl_jobs      |
|  - service_keywords, discovery_queries| - signals, service_opportunities      |
|  - service_roles                      | - decision_makers, suppressions       |
+-------------------------------------------------------------------------------+
```

### Layer Isolation & Boundaries

- **`app/config.py`**: Pydantic-settings single source of truth for runtime config.
- **`app/db.py` & `app/models.py`**: ORM models mapping natively to PostgreSQL / SQLite.
- **`app/providers/`**: Pluggable provider abstractions for Search Engine APIs and LLMs.
- **`app/engine/`**: Core logic split into modular single-responsibility units:
  - `crawler.py`: Polite HTTP crawler respecting `robots.txt` and concurrency limits.
  - `extractor.py`: HTML parsing into structured `ExtractedPage` objects.
  - `classifier.py`: Service-agnostic company qualification and business model tagging.
  - `signals.py`: Pattern-based keyword and structural signal detection with decay.
  - `evidence.py`: Integrations with ATS job boards (Greenhouse/Lever/Workable/etc.), SEC EDGAR, news SERPs.
  - `ai_analysis.py`: LLM reasoning validation using strict Pydantic JSON schemas.
  - `scoring.py`: Multi-component scoring math (Deterministic + AI + Evidence Quality).
  - `decision_makers.py`: Public page regex extraction with suppression list validation.
  - `pipeline.py`: Orchestrates per-company isolated execution lifecycle.

---

## 2. Data Model & Database Schema

The database consists of two distinct conceptual groups across 14 primary tables:

### A. Dynamic Service Configuration Tables
These tables dictate what the engine looks for. Retargeting the application to a new domain (e.g., Packaging or Freight) requires adding database rows without changing code.

1. **`services`**: Master service definition (e.g. `slug = '3pl'`). Stores JSONB `config` containing score weights, thresholds, and LLM system prompts.
2. **`service_signals`**: Detectable intent signals per service (e.g., `hiring_warehouse_manager`, weight: +35, decay: 90 days).
3. **`service_keywords`**: Target phrases and regex patterns associated with signals.
4. **`discovery_queries`**: Templated search strings for candidate discovery.
5. **`service_roles`**: Job titles relevant for decision-maker identification (e.g., COO, VP Supply Chain, Logistics Director).

### B. Generic Company Intelligence Tables
Stores discovered data, shared seamlessly across potential future services.

1. **`companies`**: Unique domain records, classification details, country, platform (Shopify/Woo/etc.), business model, and resolved company LinkedIn URL.
2. **`sources`**: Tracked web pages and external documents providing evidence; tagged with content hash for change detection.
3. **`crawl_jobs`**: Audit log of crawl attempts, HTTP statuses, and `robots.txt` skips.
4. **`signals`**: Detected signal instances linked to specific companies, services, and evidence sources.
5. **`service_opportunities`**: Scored lead evaluation per `(company, service)`. Contains `score`, `raw_score`, `deterministic_score`, `ai_score`, `evidence_score`, `intent_level`, and a complete JSON `score_breakdown`.
6. **`decision_makers`**: Sourced names, titles, page URLs, and confidence labels (`confirmed`, `likely`, `possible`).
7. **`suppressions`**: Right-to-object table to block specific names or domains.
8. **`search_cache`**: Postgres-backed SERP cache with TTL.
9. **`pipeline_runs`**: Execution logging for observability.
10. **`api_usage`**: Granular LLM and Search token/cost tracking.

---

## 3. Pipeline Funnel & Stage Mechanics

Every candidate domain passes through an 8-stage cost-gated processing funnel:

```
[1. Discovery] ---> [2. Polite Crawl] ---> [3. Classification & Gate]
                                                    |
                                                    v
[6. AI Analysis] <-- [5. Provisional Score] <-- [4. External Evidence]
       |
       v
[7. Final Scoring] ---> [8. Decision Maker Sourcing]
```

1. **Discovery**: Executes templated web queries (`discovery_queries`) via the active `SearchProvider` to discover new candidate domains.
2. **Polite Crawling**: Crawls up to `crawl_max_pages_per_company` (default: 12) within a strict wall-clock budget (45s max per company). Respects `robots.txt` explicitly.
3. **Classification & Qualification Gate**:
   - Identifies tech stack / platform markers (Shopify, WooCommerce, Magento, etc.).
   - Evaluates physical-product qualification using tiered evidence (MOQ, shipping policy, product schema).
   - Classifies business model (DTC, Wholesale, Manufacturer, Retail, Marketplace).
   - **Rejection Filter**: Immediately rejects software/SaaS, service agencies, and competing 3PL/freight providers. Stored with a `rejection_reason` to prevent re-processing.
4. **External Evidence Gathering**:
   - ATS Job Boards: Probes public API endpoints (Greenhouse, Lever, Ashby, Workable, Recruitee).
   - SEC EDGAR: Searches Form D full-text filings for US private funding rounds.
   - News/SERP Search: Executes news and press release queries for funding/expansion announcements.
5. **Provisional Score**: Calculates a lightweight score to check if the company meets `ai_analysis_min_raw_score` (default: 25).
6. **AI Analysis (Guarded)**: Sends signals and page excerpts (capped at 12,000 characters) to an LLM for structured interpretation. Guardrails ensure that hallucinated high-confidence reads without factual signals are automatically clamped to low probability.
7. **Final Scoring**: Blends deterministic, AI, and evidence scores (§4).
8. **Decision Maker Extraction**: Sources decision makers only if `final_score >= decision_maker_threshold` (default: 80).

---

## 4. Scoring Model Math & Auditing

The opportunity score is a weighted blend normalized to a 0–100 scale:

$$\text{Final Score} = (w_{\text{det}} \times \text{Det}_{\text{norm}}) + (w_{\text{ai}} \times \text{AI}_{\text{norm}}) + (w_{\text{ev}} \times \text{Ev}_{\text{score}})$$

- **Default Weights**: Deterministic ($50\%$), AI ($30\%$), Evidence Quality ($20\%$).
- **LLM Fallback Auto-Renormalization**: If no LLM is configured or an LLM call fails, $w_{\text{ai}}$ becomes $0$, and remaining weights renormalize to $100\%$ ($71.4\%$ Deterministic, $28.6\%$ Evidence) without artificially lowering scores.

### Component Details

- **Deterministic Score**: Sum of detected signal weights multiplied by linear time decay ($1.0 \rightarrow 0.0$ over signal decay window) and detection confidence. Negative signals (e.g. `existing_3pl`) do not decay. Sum is normalized against a ceiling (default: 110 points).
- **AI Score**: Model's estimated `service_probability` ($0.0 - 1.0$) scaled to $0 - 100$.
- **Evidence Score**: Evaluates citation coverage, source type diversity, and off-site independent verification:
  $$\text{Ev}_{\text{score}} = 100 \times (0.45 \times \text{CitationRate} + 0.30 \times \text{Diversity} + 0.25 \times \text{IndependentSources})$$
- **Required Signal Cap**: If a service mandates a required signal (e.g. `physical_products`) and it is missing, the final score is hard-capped at **45** regardless of other metrics.

### Intent Tiers
- `HOT`: $\ge 85$
- `STRONG`: $\ge 75$
- `GOOD`: $\ge 60$
- `POSSIBLE`: $\ge 40$
- `LOW`: $< 40$

Every score includes a complete, line-by-line JSON breakdown (`score_breakdown`) stored in the database and visible in the dashboard detail view.

---

## 5. Provider Abstractions

### Search Providers (`app/providers/search/`)
Interfaces with web search APIs via a unified `SearchProvider` base class.
- Supported Providers: **Serper.dev**, **SerpAPI**, **Brave Search**, **Exa.ai**.
- Features: Multi-key rotation, Postgres caching (`search_cache`), rate limiting.

### LLM Providers (`app/providers/llm/`)
Provides structured JSON generation via LLMs.
- Supported Providers: **Groq**, **Google Gemini**, **OpenAI**.
- Features: Fallback chain configuration (`AI_FALLBACK_PROVIDERS`), token/cost tracking logged to `api_usage`.

---

## 6. REST API Reference

Built with FastAPI. Interactive documentation available at `/docs` when running.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/services` | List all active services |
| `GET` | `/api/services/{slug}/config` | Get resolved runtime service configuration |
| `GET` | `/api/companies` | List disovered/classified companies with filters |
| `GET` | `/api/companies/{id}` | Get detailed company profile & signals |
| `GET` | `/api/services/{slug}/opportunities` | Paginated lead list filtered by intent level & country |
| `GET` | `/api/opportunities/{id}` | Get full lead details including complete score arithmetic |
| `POST`| `/api/opportunities/{id}/review` | Submit human feedback label (excellent/good/bad) |
| `POST`| `/api/discovery/run` | Trigger on-demand candidate discovery run |
| `POST`| `/api/pipeline/process-queue` | Execute time-bounded synchronous batch queue processing |
| `POST`| `/api/companies/add` | Manually seed and enqueue a company URL |
| `GET` | `/api/pipeline/status` | Real-time queue and background execution status |
| `GET` | `/api/stats` | High-level system & pipeline metrics |
| `GET` | `/api/export` | Download CSV export of qualified leads (No email fields) |

---

## 7. Operations & Background Processing

### Worker Modes

1. **Celery + Redis (Standard Production)**:
   - `discover_companies` (Daily 02:00)
   - `process_queue_task` (Hourly)
   - `recalculate_scores_task` (Daily 03:00 - recalculates signal decay)
   - `refresh_stale_task` (Daily 04:30 - re-crawls active leads)
   - `enforce_retention_task` (Weekly Sun 06:00 - GDPR data retention)
2. **Synchronous Time-Bounded Processor (Free-tier / Serverless Hosts)**:
   - Host environments that kill background threads on HTTP response return (e.g. Render/Railway free tiers) use `POST /api/pipeline/process-queue?max_seconds=240`.
   - Bounded by wall-clock time, committing work per company, returning cleanly with `stopped_reason: "time_budget_reached"`.

---

## 8. Configuration & Environment Reference

All settings loaded from `backend/.env` via `pydantic-settings` (`app/config.py`):

| Parameter | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | - | Primary database connection string (PostgreSQL/SQLite) |
| `DATABASE_MIGRATION_URL` | - | Direct migration connection string (handles raw SQL) |
| `SEARCH_PROVIDER` | `serper` | Active search vendor (`serper`, `serpapi`, `brave`, `exa`) |
| `AI_PROVIDER` | `groq` | Primary LLM provider (`groq`, `gemini`, `openai`) |
| `AI_FALLBACK_PROVIDERS` | `gemini,openai` | Ordered fallback providers for LLM calls |
| `CRAWL_MAX_PAGES_PER_COMPANY` | `12` | Crawl limit per domain |
| `CRAWL_MAX_SECONDS_PER_COMPANY`| `45` | Hard timeout ceiling per domain crawl |
| `RESPECT_ROBOTS_TXT` | `true` | Hard compliance gate for crawling |
| `MAX_COMPANIES_PER_DISCOVERY_RUN`| `200` | Discovery safety ceiling |
| `DEFAULT_SERVICE_SLUG` | `pet_specialty_food_treats_supplements` | Default target service (`3pl` = legacy) |
| `VITE_SERVICE_SLUG` | `pet_specialty_food_treats_supplements` | Service the dashboard shows (frontend build) |

---

## 9. Verification & Testing

The platform includes 45 unit & integration tests (`backend/tests/`):
- `test_scoring.py`: Arithmetic correctness, decay calculations, score capping.
- `test_no_email.py`: Structural verification that no email fields exist in models or CSV exports.
- `test_service_config.py`: Verifies that introducing a new service requires zero code changes.
- `test_pipeline.py`: Pipeline fault isolation and mock web crawls.

Execute tests via:
```bash
cd backend && pytest
```

---

## 10. Quickstart & Deployment

### Local Development Setup

```bash
# 1. Install Python dependencies
cd backend && pip install -r requirements.txt

# 2. Seed database & service configuration
python -m scripts.seed

# 3. Start Backend API
uvicorn app.main:app --reload   # http://localhost:8000/docs

# 4. Start Dashboard UI (in frontend/)
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

### Deployment Topology
- **Frontend**: Hosted on Vercel / Netlify (`VITE_API_BASE_URL` pointing to backend).
- **Backend API**: Railway / Render / AWS ECS.
- **Database**: Supabase PostgreSQL with RLS enabled (`001_init.sql`, `002_rls.sql`, `003_seed_3pl.sql` ... `007_powersports_aftermarket_sourcing.sql` ... `010_pet_specialty_food_treats_supplements.sql`).
