# Who this finds (after migration 004)

## The change

The qualification gate used to require **ecommerce AND physical products**.
Anything else was capped at 45/100 — so a wholesaler doing 10x the shipping
volume of a small Shopify store was invisible.

The gate is now **physical products only**. Selling online is a scoring bonus.

```
before:  ecommerce + physical_products  ->  DTC brands only
after:   physical_products              ->  anyone who moves goods
```

SaaS, agencies and consultancies are still rejected — the gate moved, it
didn't disappear.

## Segments now searched

| Segment | Why they need a 3PL | Detected by |
|---|---|---|
| **DTC / ecommerce** | Order fulfilment, returns | cart, checkout, platform fingerprints |
| **Wholesale / B2B** | Pallet-scale storage, pick and pack for trade orders | MOQ, trade accounts, price lists, "become a stockist" |
| **Manufacturers / CPG** | Finished-goods warehousing between production and retail | "our factory", contract manufacturing, private label |
| **Retail / omnichannel** | Retail-compliant fulfilment, multi-destination | stockists, "available in store", retail partners |
| **Marketplace sellers** | Multi-channel inventory across Amazon/eBay/Etsy | marketplace mentions, seller central, FBA |
| **Subscription** | Recurring monthly waves — predictable heavy volume | subscription box, recurring delivery, meal kit |
| **Importers** | Container handling, customs, deconsolidation | incoterms, customs clearance, container shipments |

`companies.business_model` records the primary one; `sales_channels` records
every channel found. A company matching three or more is tagged
`multi_channel`, which is itself a strong signal — juggling channels is what
pushes brands to outsource.

## New signals and weights

Ordered by weight. Everything is configurable in `service_signals`.

| Signal | Weight | Decays | What it means |
|---|---|---|---|
| `seeking_3pl` | **25** | 180d | Publicly looking for a fulfilment partner. The strongest possible signal — they're already shopping. |
| `fulfillment_hiring` | 20 | 120d | Hiring warehouse/fulfilment roles |
| `capacity_strain` | **20** | 180d | "Outgrowing our warehouse", backorders, shipping delays |
| `operations_hiring` | 15 | 120d | Hiring ops/supply chain |
| `international_expansion` | 15 | 270d | Entering a new market |
| `crowdfunding` | 15 | 365d | Campaign with a fulfilment wave coming |
| `subscription_model` | **15** | — | Recurring shipments |
| `warehouse_move` | **15** | 270d | Relocating to a larger facility |
| `recent_funding` | 12 | 540d | Capital to spend, volume to handle |
| `wholesale_b2b` | **12** | — | Trade orders with MOQs |
| `marketplace_seller` | **12** | — | Multi-channel fulfilment |
| `retail_distribution` | **12** | — | Stocked by physical retailers |
| `importer_exporter` | **12** | — | Container and customs handling |
| `multi_channel` | **10** | — | Three or more sales channels |
| `product_launch` | 10 | 180d | New line coming |
| `peak_season` | **10** | 150d | Seasonal spikes |
| `new_store` | 10 | 365d | Recently launched |
| `physical_products` | 10 | — | **The gate** |
| `rapid_growth` | 10 | 270d | Fast growth |
| `manufacturer` | **8** | — | Makes its own goods |
| `international_shipping` | 8 | — | Ships beyond home market |
| `ecommerce` | 8 | — | Sells online (was 10 — now a bonus, not a gate) |
| `existing_3pl` | **−20** | — | Already has a provider. Reduces, never disqualifies — they may need overflow, a second location, or international. |

**Bold** = new in migration 004.

`normalization_ceiling` is 110, so a company needs roughly 110 raw points to
reach 100. Calibration:

| Profile | Raw | Deterministic |
|---|---|---|
| Bare wholesaler (physical + wholesale only) | 22 | 20 — correctly LOW |
| Wholesaler + retail + intl + ops hire | 57 | 52 — GOOD |
| DTC, funded, hiring fulfilment | 65 | 59 — GOOD |
| Subscription box scaling | 73 | 66 — GOOD/STRONG |

## Discovery queries

66 total. The highest-priority ones target intent rather than category:

```
"looking for a 3PL" brand
"looking for a fulfillment partner"
brand "outgrowing our warehouse"
ecommerce brand "outsourcing fulfillment"
company hiring warehouse manager new facility
```

A company writing those words is mid-decision. The category queries
("new CPG brand launch", "wholesale supplier trade accounts") fill the top
of the funnel.

## Tuning it

None of this needs a code change:

```bash
# see current weights
curl localhost:8000/api/services/3pl/signals

# change one
curl -X PATCH localhost:8000/api/admin/signals/{id} \
  -H "X-Admin-Token: $SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"weight": 30}'

# add a discovery query
curl -X POST localhost:8000/api/admin/services/3pl/queries \
  -H "X-Admin-Token: $SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"query": "new toy brand launch", "priority": 2}'

# re-score everything from stored signals — no re-crawl, no API cost
celery -A app.workers.celery_app call app.workers.tasks.recalculate_scores_task
```

Run `/api/services/3pl/config` to see the resolved configuration the engine
is actually using.
