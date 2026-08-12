# Discovery query library

**6,842 generated Serper queries**, tiered by expected yield.

Generated, not hand-written — regenerate after editing the vocabulary:

```bash
cd backend
python -m scripts.query_library        # preview counts and samples
python -m scripts.build_query_library  # write migrations/005_query_library.sql
```

Source of truth: `backend/scripts/query_library.py`.

## Loading it

`ALL_IN_ONE.sql` does **not** include the library — 320 KB of INSERTs would
make it painful to paste. Run it separately, once:

1. Supabase → SQL Editor → New query
2. Paste `backend/migrations/005_query_library.sql`
3. Run

Idempotent. Verify:

```sql
select priority as tier, count(*) from discovery_queries group by 1 order by 1;
```

The local seed path loads it automatically (`python -m scripts.seed`); skip it
with `--no-library`.

## Tiers

Stored in `discovery_queries.priority`. Discovery runs **one tier at a time**,
least-recently-run first, so repeat runs work through the library instead of
re-paying for the same queries.

| Tier | Queries | Pattern | Why |
|---:|---:|---|---|
| **1** | 630 | `Shopify {cat} brands`, `DTC {cat} brands`, `{cat} ecommerce brands`, `{cat} online stores` | Platform footprint + product category. Returns actual brand domains rather than listicles. **Start here.** |
| 2 | 2,835 | `{model} {cat}`, `{model} {cat} brands/companies/startups` | Business model × category across 6 model prefixes |
| 3 | 2,288 | `top {cat} DTC brands`, `{cat} brands directory`, `growing {cat} DTC brands`, `consumer products company {cat}`, WooCommerce/BigCommerce/Magento footprints, `"Powered by Shopify" {cat}` | Directories, growth signals, alternative terminology. Directory pages are read as *sources* — the brands are extracted, the directory is never stored as a prospect. |
| 4 | 1,089 | `{cat} brands {country}`, broad `{cat} brands`, business-model and fulfilment-signal seeds | Geographic fan-out across 14 markets, plus broad catch-all |

## Coverage

**110 categories** across 10 groups: Fashion (15), Beauty (11), Health &
Wellness (10), Food & Beverage (12), Pet (7), Home (11), Baby & Kids (8),
Sports & Outdoor (10), Electronics (8), Other Physical Products (13).

**Business models:** ecommerce, DTC, direct-to-consumer, online retailer,
online store, consumer brand, CPG, product company, retail brand,
subscription — as both full phrases and query prefixes.

**Platforms:** Shopify, WooCommerce, BigCommerce, Magento, plus the
`"Powered by Shopify"` / `"powered by WooCommerce"` footprints.

**Geographies:** US, CA, GB, AU, DE, FR, NL, ES, IT, AE, SG, IN — applied to
the 28 highest-DTC-density categories rather than all 110, which would have
tripled the library for diminishing returns.

## Exclusions

Two layers, because a query filter alone leaks.

**1 — Negative operators, appended at search time**

```
Shopify skincare brands -3PL -logistics -freight -courier
  -"fulfilment services" -"fulfillment services" -jobs -salary -"hiring agency"
```

A term already present in the query is skipped, so `logistics brands` doesn't
get `-logistics` and return nothing. Tunable in
`services.config.query_exclusion_terms` — every negative costs recall, so the
list is deliberately short.

**2 — Rejection at classification**

A 3PL provider's own website is full of fulfilment vocabulary and would
otherwise outscore a real brand. `classifier.COMPETITOR_MARKERS` rejects
first-person service offerings:

| Rejected | Kept |
|---|---|
| "we are a 3PL", "our fulfillment services" | "dispatched by our fulfillment partner" |
| "freight forwarding services" | "freight charged at cost" |
| "we are a marketing agency" | brand that hired an agency |

That distinction is the whole point: a brand *using* a 3PL is a customer
signal (`existing_3pl`, weight −20 — reduces, never disqualifies). A brand
*selling* 3PL is a competitor. Pinned by
`tests/test_competitor_exclusion.py`.

Marketplaces (Amazon, eBay, Etsy, Walmart, Alibaba, Temu, Shein) are blocked
at domain level in `utils/urls.BLOCKED_DOMAINS`, along with social, news and
ATS domains.

## Cost control

Only **executed** queries cost credits. Seeding all 6,842 costs nothing.

```bash
# tier 1, 60 queries, stop at 200 companies
curl -X POST localhost:8000/api/discovery/run \
  -H "Content-Type: application/json" \
  -d '{"tier": 1, "max_queries": 60, "limit": 200}'

# how much of the library has been used?
curl localhost:8000/api/discovery/queries
```

Defaults: `MAX_QUERIES_PER_DISCOVERY_RUN=50`,
`MAX_COMPANIES_PER_DISCOVERY_RUN=200`. Results are cached in Postgres for a
week, so re-running a query inside that window is free.

The scheduled job runs **tier 1, 60 queries daily** — roughly 11 days to work
through tier 1 once, at ~1,800 results a day.

**Budget before you open the tap.** A full pass is 6,842 Serper credits and
up to ~137,000 raw results. The crawl is the real cost: even at 10% unique
valid domains that's ~10,000 sites to fetch. Run tier 1 first, measure how
many became STRONG/HOT leads, then decide whether tier 2 is worth it.

## Tuning

```bash
# disable a tier entirely
UPDATE discovery_queries SET enabled = false WHERE priority = 4;

# disable queries that never produce anything, after a few runs
UPDATE discovery_queries SET enabled = false
WHERE last_run_at IS NOT NULL AND results_count = 0;

# add your own
curl -X POST localhost:8000/api/admin/services/3pl/queries \
  -H "X-Admin-Token: $SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"query": "new candle brand launch", "priority": 1}'
```

After a few hundred runs, `discovery_queries.results_count` tells you which
patterns actually work. That's the signal worth acting on — not the size of
the library.
