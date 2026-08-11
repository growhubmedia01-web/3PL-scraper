# Architecture notes

## The one rule

> The crawler does not know what 3PL is.
> The company database does not know what 3PL is.
> The generic intelligence engine does not know what 3PL is.

Grep test:

```bash
grep -rn "3pl" backend/app/ --include="*.py" \
  | grep -viE "§|PRD|migrations/003|Service '|third.party"
```

Should return exactly two lines, both of which are correct:

```
app/config.py:82:    default_service_slug: str = "3pl"        # a setting
app/deps.py:15:      description="Service slug, e.g. '3pl'"   # a docstring
```

`default_service_slug` is an environment variable — point it at `packaging`
and every default flips, with no code change. All real 3PL knowledge lives in
`backend/migrations/003_seed_3pl.sql` and `backend/scripts/seed.py`.

Things that could easily have leaked into code but didn't:

- **Signal weights** → `service_signals.weight`
- **Which job titles matter** → `service_roles`
- **Score thresholds and weights** → `services.config`
- **The AI prompt** → `services.config.ai_system_prompt`
- **Which page types make a keyword meaningful** →
  `services.config.signal_page_affinity` (the `existing_3pl` mapping lives
  there, not in `signals.py`)
- **The model's probability field name** → derived from the service slug

## Layer boundaries

| Layer | Knows about | Never knows about |
|---|---|---|
| `utils/` | URLs, text, robots.txt | services, signals, scoring |
| `providers/` | vendor APIs | what a company is |
| `engine/crawler,extractor` | HTML, HTTP | services |
| `engine/classifier` | what a company IS | whether it's a good lead |
| `engine/signals,scoring` | ServiceConfig | which service it is |
| `engine/pipeline` | orchestration | vendor details |
| `api/` | HTTP contracts | crawling internals |

`classifier.py` answers "what is this company?" — `scoring.py` answers "is it
a good lead for service X?". Keeping those separate is what makes company
intelligence reusable across services (§70: discover once, understand once).

## Adding a second service

No code. Insert rows:

```sql
insert into services (name, slug, status, config) values
  ('Packaging', 'packaging', 'active', '{
     "required_signals": ["physical_products"],
     "score_weights": {"deterministic": 0.6, "ai": 0.2, "evidence": 0.2},
     "ai_system_prompt": "You are a packaging industry analyst..."
   }'::jsonb);

insert into service_signals (service_id, signal_type, signal_name, weight, decay_days)
select id, 'product_launch', 'Product Launch', 30, 180 from services where slug='packaging';

insert into service_roles (service_id, title_pattern, role_priority)
select id, 'head of design', 1 from services where slug='packaging';
```

Then `GET /api/services/packaging/opportunities`. The same crawled company data
is reused — no re-crawling, no new tables.

## Why the AI is deliberately constrained

Three mechanisms stop the model from driving the product:

1. **Weight cap** — 30% by default, so max model confidence moves the score
   ~30 points.
2. **Schema validation** — `AIAnalysis` rejects malformed output; a failed
   parse degrades to deterministic-only rather than poisoning the score.
3. **Signal guardrail** — high probability with zero detected signals gets
   clamped to 0.2 and flagged in `evidence_gaps`.

If the model is unavailable entirely, weights renormalize so scores stay
comparable rather than all sinking by 30%.

## Freshness decay

Every signal carries `detected_at` and `expires_at`. `effective_strength()`
decays linearly to zero at expiry. Negative signals (an incumbent 3PL) are
exempt — an existing provider doesn't become less true over time.

`recalculate_scores_task` runs nightly and re-scores from stored signals
without re-crawling. Without it, decay would only apply when a company happened
to be re-analyzed, and stale leads would sit at the top of the list forever.

## Error philosophy (§55)

- One failing site never aborts a batch — `process_batch` commits per company.
- Every crawl attempt writes a `crawl_jobs` row with status, attempt count and
  error. Robots-blocked fetches are `skipped`, not `failed`, so the two are
  distinguishable in metrics.
- Rejected companies keep a `rejection_reason` so they are never blindly
  reprocessed.
- LLM failure walks the fallback chain, then returns `None` — the pipeline
  continues on deterministic scoring.
