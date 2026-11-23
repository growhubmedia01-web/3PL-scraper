# Powersports Aftermarket Product Sourcing

**The default service** (slug `powersports_aftermarket_sourcing`, migration
`007`). It replaces the original Third-Party Logistics (3PL) service *as the
default*. The 3PL service, its configuration and all its historical data
stay in the database, marked `inactive`. Nothing was deleted.

## What it finds

It looks for **mid-market (50–500 employees) US wholesale distributors of
aftermarket powersports parts and accessories**. For each one it records
**public, dated evidence that they are buying**, and **which products** that
evidence names.

The commercial direction matters, and the engine enforces it:

| Direction | Example | Treated as |
|---|---|---|
| distributor → supplier (buying) | "submit your product catalog", "seeking quotes from manufacturers", a vendor application | **positive buying intent** |
| distributor → dealer (selling) | "become a dealer", dealer application, dealer pricing | **fit only**: proves they are a B2B distributor, never buying intent |
| manufacturer → distributor | "looking for a US distributor", "distributors wanted" | **negative** (−25) |

The system never invents products. When no product is named in a source,
the lead says: *"Specific product demand not publicly disclosed."*

## Who qualifies

The classifier assigns a company type from configured on-page markers:
`wholesale_distributor`, `importer`, `manufacturer`, `brand_owner`,
`dealer_retailer`, `service_provider`, plus the hybrids
`hybrid_distributor_manufacturer` and `hybrid_distributor_dealer`.

The qualification gate (`services.config.qualification`) works like this:

- **Eligible:** wholesale distributor, importer, and the two hybrids.
- **Rejected:** dealer/retailer, service/repair provider, manufacturer-only,
  brand owner. The reason is always stored in `companies.rejection_reason`.
- **Geography:** the US only, strictly (`require_country_evidence`). The
  company must be positively located in the US with at least 0.6
  confidence: a US state + ZIP, "City, ST", "City, Statename", a `.us`
  domain or an explicit mention. No location evidence means rejected, and
  so does an ambiguous one. A bare 5-digit postcode does not count, because
  Mexico, Germany and others use them too. Addresses and country domains
  outweigh country names in prose, so a US distributor "serving dealers in
  the US and Canada" stays US.
- **Industry:** at least 2 distinct powersports markers.
- **Unknown type** is allowed, but scored down through the fit multiplier.
- **Shopify is not required.** The platform and ecommerce checks are no
  longer part of the gate for this service.

## Company size, without fabrication

`app/engine/profile.py` reads employee count, dealer count, states served,
facilities, headquarters, stated revenue and the supplier-intake URL. Its
sources are only:

- the company's own pages;
- schema.org `numberOfEmployees` / `address`;
- news or press pages, for everything **except** headcount.

Each fact is stored in `company_facts` with its source URL, the evidence
sentence, a confidence and the date observed.

| Band | Employees | Fit multiplier |
|---|---|---|
| micro | 1–10 | 0.55 |
| small | 11–49 | 0.85 |
| **mid_market** | **50–500** | **1.0** |
| large | 501+ | 0.7 |
| unknown | not publicly stated | 0.8 |

No count means the band stays `NULL` ("unknown"). The system never guesses
it, and the AI is told not to either.

## Signals

All signals use linear freshness decay to zero at expiry.

| Signal | Weight | Decay (days) | Dimension |
|---|---|---|---|
| active_product_rfq | 35 | 90 | intent |
| explicit_supplier_search | 30 | 120 | intent |
| new_distribution_partnership | 27 | 180 | intent |
| new_brand_added | 25 | 180 | intent |
| product_category_expansion | 23 | 180 | intent |
| supplier_application_open | 22 | 180 | intent |
| new_product_line_launch | 18 | 150 | intent |
| category_buyer_hiring | 17 | 120 | intent |
| catalog_or_linecard_expansion | 15 | 180 | intent |
| procurement_hiring | 15 | 120 | intent |
| distribution_center_expansion | 13 | 270 | intent |
| dealer_network_expansion | 12 | 180 | intent |
| acquisition_or_distribution_expansion | 12 | 270 | intent |
| b2b_dealer_distribution | 6 | never | fit |
| powersports_participation | 5 | never | fit (required) |
| manufacturer_seeking_distribution | −25 | never | negative |
| retail_only_operation | −15 | never | negative |
| service_repair_operation | −12 | never | negative |

### Polarity controls

Polarity is enforced by generic, config-driven sentence rules in
`services.config.signal_rules`:

- **`exclude_page_types: ["dealer"]`.** Supplier-sourcing keywords on a
  `/become-a-dealer` page never count.
- **`suppress_phrases`.** A sentence that also says "become a dealer", "looking
  for a distributor", "get a quote" (and similar) is skipped. The next
  allowed sentence is used instead, if there is one.
- **`require_context_phrases`.** An "RFQ" sentence must also mention
  suppliers, manufacturers, vendors or sourcing.
- **`require_page_types`.** Hiring signals count only on careers or job pages.
- **Undated pages.** Intent signals found on undated pages have their
  confidence multiplied by `undated_confidence_factor`.

## Product taxonomy

Categories and subcategories are listed below. Vehicle segments and
platforms are stored separately on each record.

- **ATV/UTV/Side-by-Side Accessories:** bumpers, rock sliders, skid plates,
  roof systems, windshields, wipers, cab enclosures, doors, roof and cargo
  racks, storage, tire carriers, grilles, mirrors, winches, recovery
  accessories, lighting.
- **Tires and Wheels:** ATV, UTV, motorcycle and off-road tires; specialty and
  performance wheels; tire and wheel systems.
- **Motorcycle Aftermarket Accessories:** crash protection, crash bars, frame
  sliders, touring luggage, saddlebags, panniers, top cases, racks,
  windscreens, handguards, styling, adventure touring.
- **Riding Gear and Protection:** helmets, gloves, boots, jerseys, pants,
  jackets, goggles, body armour, knee and neck protection, snowmobile,
  motocross and casual apparel.
- **Electrical and Performance:** batteries, charging, LED lighting,
  electrical accessories, harnesses, exhausts, engine upgrades, tuners, EFI,
  suspension, brakes, tire balancing.
- **Maintenance and Consumables:** lubricants, oils, filters, chains,
  sprockets, maintenance kits, cleaning products, chemicals, workshop
  consumables.

**Vehicle segments:** ATV, UTV/Side-by-Side, Motorcycle – Street/Touring,
Motorcycle – Off-Road/Motocross, Motorcycle – Adventure, Snowmobile.
Platforms such as Polaris, Can-Am, RZR and Maverick are kept as their own
field, and are never treated as a supplier brand.

## Product-interest classes (`product_interests` table)

| Class | Comes from | Meaning |
|---|---|---|
| `EXPLICITLY_SEEKING` | RFQ, supplier search, supplier application | They asked for it |
| `RECENTLY_ADDED` | partnership, new brand, category, line or catalog expansion | They just started buying it |
| `CURRENTLY_CARRIED` | own brands, line-card or catalog pages | What they stock. **Not** a buying signal |
| `INFERRED_FIT` | adjacency to carried or added categories (confidence 0.25) | A hypothesis, clearly labelled |

Every record must carry a `source_id` or `source_url`. The engine drops
records without one, at both the build step and the persist step.
News, press and job pages use the full article text as the evidence
window; other pages use the sentence plus or minus two sentences.

## Scoring

Score inputs:

- **Deterministic** (weight 0.5): Σ weight × freshness × confidence,
  normalised against a ceiling of 90.
- **AI** (weight 0.3).
- **Evidence quality** (weight 0.2).

Adjustments:

- **Fit multiplier:** the employee-band factor × the company-type factor. It
  shows as its own line in the breakdown.
- **Intent cap:** with no live intent-dimension signal, the score is capped
  at 40.
- **Required-signal cap:** without `powersports_participation`, the score is
  capped at 45.
- **Decision-maker research** runs at 40 and above. AI analysis runs at a raw
  score of 20 and above.

## AI analysis guardrails

The prompt includes:

- company type, size band and headquarters;
- a deterministic **STRUCTURED EVIDENCE** block;
- the rule *"no claim without evidence"*.

The model returns extra structured fields: distributor qualification, size
qualification, strongest buying signals, product categories, products
mentioned, supplier onboarding evidence, distribution partnerships, recent
expansion activity, and likely decision roles (titles only).

`ground_analysis()` then removes any product, category or partnership item
that does not appear in the crawled evidence, and records the removal in
`evidence_gaps`.

## External evidence

External evidence uses the six configured search templates: partnerships,
new lines, trade press, supplier pages, purchasing jobs and warehouse or
acquisition news.

For up to 3 results per company, the **full article** is fetched. The fetch
respects robots.txt and falls back to the snippet on failure. The fetchers
are `ats` (job boards); SEC Form D is disabled for this service.

What it never does:

- no LinkedIn or social scraping;
- no email discovery;
- no personal-contact enrichment.

## Decision makers

The roles are purchasing-first: VP or Director of Purchasing or Procurement,
then purchasing and category managers and buyers, then owner, president and
CEO at priority 6. Names come only from the company's own public pages. The
suppression list and the no-email rules are unchanged, and both are enforced
by tests.

## Discovery query library

The library has 98 queries, deliberately small:
`scripts/services/powersports_aftermarket_sourcing.py::build_library()`.

| Tier | Count | Purpose |
|---|---|---|
| 1 | 22 | direct purchasing intent, supplier onboarding |
| 2 | 36 | recent category and brand expansion |
| 3 | 30 | target-distributor discovery and qualification |
| 4 | 10 | hiring, warehouses, acquisitions |

Directories, trade publications, marketplaces and big retailers are listed
in `discovery_blocked_domains`, and are never stored as companies.

## Where it is defined

The single source of truth is
`backend/scripts/services/powersports_aftermarket_sourcing.py`. The
generator writes the migration from it:

```bash
cd backend
python -m scripts.build_service_seed          # writes migrations/007_powersports_aftermarket_sourcing.sql
python -m scripts.build_all_in_one            # refreshes ALL_IN_ONE.sql
```

`tests/test_migrations_sql.py::test_service_migration_matches_its_generator`
fails if either side is edited by hand.

Migration 007 is additive and idempotent:

- **New `companies` columns:** company_type, employee_band, size_* and
  headquarters*.
- **New tables:** `company_facts` and `product_interests`, with RLS read
  policies.
- **Seed rows:** the service, its signals, keywords, roles and queries,
  upserted on their unique keys.
- **3PL:** `update services set status='inactive' where slug='3pl'`.

It never runs `delete`, `drop` or `truncate`.

## Operating it

### Switching services

| Setting | Default | Use it to |
|---|---|---|
| `DEFAULT_SERVICE_SLUG` (backend) | `powersports_aftermarket_sourcing` | set `3pl` to switch the API back to the legacy service |
| `VITE_SERVICE_SLUG` (frontend build) | `powersports_aftermarket_sourcing` | set `3pl` to switch the dashboard back |

### Applying 007 to an existing database (Supabase or Render)

1. Run the schema statements, either by pasting
   `migrations/007_powersports_aftermarket_sourcing.sql` into the Supabase
   SQL editor, or with `POST /api/admin/run-migration` (schema part of
   004/006/007).
2. Seed the service: `POST /api/admin/seed-service?slug=powersports_aftermarket_sourcing`.
   Step 1 already does this if you ran the SQL file. Admin endpoints need
   the `X-Admin-Token: $SECRET_KEY` header.
3. Check `GET /api/services`. The powersports service should be `active`
   and 3PL `inactive`.

### First controlled pilot (small and paid)

Do this only once you have authorised the search and LLM spend.

```bash
API=https://<your-render-service>.onrender.com
curl -X POST $API/api/discovery/run -H "Content-Type: application/json" \
  -d '{"service_slug":"powersports_aftermarket_sourcing","tier":1,"max_queries":5,"limit":20,"country":"US"}'
curl -X POST "$API/api/pipeline/process-queue?limit=10&max_seconds=240" \
  -H "Content-Type: application/json" -d '{"service_slug":"powersports_aftermarket_sourcing"}'
curl "$API/api/services/powersports_aftermarket_sourcing/opportunities?sort=score"
curl "$API/api/stats?service=powersports_aftermarket_sourcing"
```

Then review each lead in the dashboard and label it with
excellent/good/maybe/bad. Measure:

- genuine US distributors;
- how many are in the 50–500 band;
- how many have direct sourcing evidence;
- how many have recent expansion;
- how many have identifiable products;
- how many have decision makers;
- false positives;
- search and LLM cost per qualified opportunity.

Tune the weights and queries in the service module, then regenerate 007.

## Known limitations

- **Rejection status is global.** A classification rejection writes the
  global `companies.status`, which is shared across services. A company
  rejected for powersports is also hidden from a re-run of 3PL.
- **Headcount is often missing.** Mid-market distributors often do not
  publish it, so expect many `unknown` bands. Verifying them needs a
  licensed firmographics source; none is integrated.
- **JavaScript-only pages.** Dates and products on JS-only pages need
  Playwright (`PLAYWRIGHT_ENABLED`).
- **The query library is a hypothesis.** Its yield is unmeasured until the
  pilot runs.

## Remaining "3PL" occurrences, classified

| Where | Class |
|---|---|
| `migrations/001–006`, `ALL_IN_ONE.sql` (3PL seed), `local.db` | Historical reference |
| `scripts/seed.py` (3PL SIGNALS/KEYWORDS/ROLES), `scripts/query_library.py`, `scripts/build_query_library.py` | Legacy compatibility: the inactive 3PL service is still seedable |
| `app/api/admin.py` (`slug == "3pl"` falls back to the legacy query library) | Legacy compatibility |
| `app/engine/classifier.py` logistics-provider markers | Legacy compatibility: governed by `config.exclude_logistics_providers` |
| `app/engine/signals.py` / `evidence.py` default affinity and templates | Legacy compatibility: labelled defaults, used only when a service sets none |
| `app/config.py` comment, `frontend/src/lib/api.ts` comment | Legacy compatibility (how to switch back) |
| `tests/test_competitor_exclusion.py`, `test_scoring.py`, `test_query_library.py`, `conftest.py` 3PL fixture | Historical test references that keep the legacy service working |
| `migrations/007`, `build_service_seed.py`, `sql_parse.py` (`set 3pl inactive`) | Active configuration |
| README, QUICKSTART, PRODUCT_OVERVIEW, TECHNICAL/PROJECT documentation, ARCHITECTURE, RUNBOOK | Documentation: updated to name the new default and to mark 3PL as legacy |
| `SEGMENTS.md`, `QUERY_LIBRARY.md` | Documentation of the legacy 3PL service: kept, with a legacy banner |
| Hardcoded business logic | **None remaining.** The hiring boost, external templates, crawl paths and logistics-competitor rejection are now config-driven. `tests/test_powersports.py::test_14b` guards the generic modules |
