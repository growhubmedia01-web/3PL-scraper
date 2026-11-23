# Pet Specialty Food, Treats & Supplements

**The default service.** Slug `pet_specialty_food_treats_supplements`,
migration `010`. The source of
truth is `backend/scripts/services/pet_specialty_food_treats_supplements.py`.
The SQL is generated from it:

```bash
cd backend
python -m scripts.build_service_seed pet_specialty_food_treats_supplements
python -m scripts.build_all_in_one
```

Seeding it is additive. The powersports service and the legacy 3PL service
keep all their companies, signals, opportunities and history. Which service
the dashboard, the API defaults and the autopilot use is set by
`DEFAULT_SERVICE_SLUG` / `VITE_SERVICE_SLUG`, not by the migration.

## What it finds

It targets **mid-market (50–500 employees) US pet specialty distributors
and wholesalers**: the companies that buy pet food, treats, chews and
supplements from brands and sell them to independent pet retailers. For each
one it records public evidence that the company is buying, onboarding or
expanding these products, and which products that evidence names.

The commercial direction decides how a page is scored:

| Direction | Example | Treated as |
|---|---|---|
| distributor → brand (buying) | "currently seeking new suppliers of freeze-dried treats", a new distribution agreement, "now available through" | **positive buying intent** |
| distributor vendor program | "become a vendor", a new vendor application | **supplier onboarding** (+20, evergreen, revalidated every 180 days). Never product demand. |
| distributor → retailer (selling) | "open a wholesale account", retailer application | **fit only**. Never supplier onboarding. |
| brand → distributor | "looking for distributors", "distributor inquiries" | **negative** (−25) |
| retailer, vet clinic, groomer | store hours, appointments | **rejected** |

## Who qualifies

- Company type comes from on-page markers. The eligible types are
  `pet_specialty_distributor`, the hybrids `hybrid_distributor_manufacturer`
  and `hybrid_distributor_retailer`, and `veterinary_supplier`. An unknown
  type is allowed.
- Location: US only.
  - A site with no address, on a `.com`/`.net`/`.us`/`.org`/`.biz` domain,
    found by a US-scoped search and showing no foreign evidence, is kept.
    It is flagged **location unverified**.
  - Foreign evidence always rejects the company.
- Size:
  - A company that **states** a size outside 50–500 is rejected and keeps
    the reason. Large national distributors therefore sit in their own
    rejected-by-size group.
  - Unknown size is never rejected.
  - Size never raises intent.
- Industry: at least one pet marker. A pet-industry company counts as
  selling physical products, so no checkout is required.

## Signals

There are 22 buying signals, in four tiers. Weights and decay are the
starting configuration, not calibrated probabilities.

| Tier | Signals |
|---|---|
| 1 Direct demand | `active_supplier_request` 35, `active_product_category_request` 35, `active_product_rfq` 35 (90 days); `supplier_application_open` 20 (180) |
| 2 Portfolio expansion | `new_supplier_partnership` 27, `new_brand_added` 25, `food_category_expansion` 23, `treats_category_expansion` 23, `supplement_category_expansion` 25, `premium_natural_portfolio_expansion` 20, `catalog_linecard_expansion` 15 (180); `product_line_launch` 18 (150) |
| 3 Purchasing capability | `category_manager_hiring` 17, `purchasing_manager_hiring` 17, `procurement_hiring` 15, `merchandising_hiring` 13 (120); `vendor_relations_expansion` 15 (150). These count only on careers or job pages. |
| 4 Business expansion | `distribution_center_expansion` 13 (270), `regional_distribution_expansion` 15, `retail_network_expansion` 12, `private_label_expansion` 16 (180), `acquisition_expansion` 12 (270) |

Other signals:

- **Fit:** `pet_specialty_participation`, `b2b_retailer_distribution`. These
  show what the company is, never that it is buying.
- **Negative:** `brand_seeking_distribution` −25, `retail_only_pet_store`
  −15, `pet_service_or_clinic` −15.

Intent is capped at 40 points, so a vendor page plus a few expansion hits
cannot reach HOT without a current, specific request.

## Products of interest

- **Taxonomy:** Specialty Dog Food, Specialty Cat Food, Dog and Cat Treats,
  Chews, and Pet Supplements.
- **Exclusions:** prescription diets, flea/tick products and other drugs are
  deliberately left out.
- **Species:** stored in the generic segments field and shown as
  **Species**.
- **Attributes:** read from the evidence sentence: format, protein source,
  life stage and positioning.
- **Claims:** stored **only as the company's stated claim**. Examples:
  "NASC Quality Seal - stated", "Supports joint health - company claim".
  Nothing is described as verified, veterinary or FDA-approved.

Each product record has an evidence class, shown under these names:

| Stored code | Dashboard label | Comes from |
|---|---|---|
| `EXPLICITLY_SEEKING` | Explicitly seeking | supplier, category or RFQ requests |
| `RECENTLY_ADDED` | Recently onboarded | partnerships, new brands, category expansions |
| `CURRENTLY_CARRIED` | Currently carried | the company's own brand or catalog pages |
| `INFERRED_FIT` | Inferred category fit | adjacency only; a hypothesis, not demand |

When no product is named, the lead says *"Specific product demand not
publicly disclosed."*

## Discovery

- **Query library:** 228 queries in four tiers:
  - 14 supplier-intent queries;
  - 29 portfolio and category-expansion queries;
  - 177 distributor-discovery queries, including 144 state-by-state ones;
  - 8 hiring and expansion queries.
- **Blocked domains:** regulators (FDA, AAFCO, NASC), trade publications
  (Pet Food Processing, Petfood Industry, Pet Business, Pet Age, Global Pet
  Expo, SuperZoo, Petfood Forum), marketplaces, big-box retailers and
  directories. They are evidence sources, never prospects.

No LinkedIn scraping, no email discovery and no personal contact
enrichment. The CSV export has no email column.

## Switching the default to this service (done)

1. Run `009_product_interest_attributes.sql` and then
   `010_pet_specialty_food_treats_supplements.sql` in the Supabase SQL
   editor. 009 must be applied **before** the code that reads
   `product_interests.attributes` is deployed.
2. Set `DEFAULT_SERVICE_SLUG` and `VITE_SERVICE_SLUG` to
   `pet_specialty_food_treats_supplements`. Run the autopilot with
   `--service pet_specialty_food_treats_supplements`.
3. Start with one controlled discovery batch of about 20–30 queries, and
   review lead quality before scaling.

## Tests

`backend/tests/test_pet_specialty.py` uses synthetic pages patterned on
public examples. It covers:

- qualification;
- vendor programs vs. retailer-account pages;
- brand-seeks-distributor;
- recently onboarded chew and supplement brands;
- stated claims;
- category routing;
- hiring;
- growth without products;
- geography and size;
- regulatory and trade-press blocking;
- the query library;
- preservation of powersports and 3PL;
- dashboard labels and the CSV export.
