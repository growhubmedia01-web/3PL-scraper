# Product Overview

**A system that finds companies who are about to need your service — before they start looking for you.**

Launch service: **Third-Party Logistics (3PL)**. Built to be pointed at other B2B services (packaging, freight, insurance, payroll — anything sold to companies that show public warning signs of needing it) without a rebuild.

---

## The problem this solves

Sales teams selling B2B services typically work from one of two bad lists:

- **A cold list of every company that might qualify** — huge, mostly irrelevant, no way to tell who's actually in-market right now.
- **Inbound leads only** — real intent, but you're competing with every other vendor they also found, and you're waiting instead of getting there first.

What's missing is a way to find companies **before they've publicly gone shopping** — while they're still just showing the early signs: hiring for the role that only gets created when volume is a problem, quietly changing warehouses, mentioning they're "outgrowing" their current setup, expanding into a new country. Those signs are public. Almost nobody is systematically reading them.

This system reads them, at scale, continuously, and turns them into a ranked, evidence-backed shortlist.

---

## What it actually delivers

For each qualified company, a lead record contains:

1. **The company** — what they sell, how (their own site, wholesale, marketplaces, subscription), where, roughly how big, what platform they run on.
2. **The intent signal(s)** — the specific, dated, public facts that suggest they need this service right now, each one linked to the exact page or article it came from.
3. **An intent score and tier** (LOW / POSSIBLE / GOOD / STRONG / HOT) — so a sales team can triage in seconds instead of reading every profile.
4. **The likely decision maker** — name and title, sourced only from the company's own "About/Team/Leadership" page, press quotes, or job postings. No guessing, no email address (see "What this deliberately does not do" below).
5. **The evidence trail** — every claim traces back to a URL. Nothing is asserted without a source a rep can open and read for themselves before they reach out.

All of this is browsable in a dashboard, filterable by score/country/industry, and exportable to CSV for a CRM.

---

## How a lead gets qualified — in plain terms

Think of it as a funnel, cheapest checks first, so money is only spent investigating companies worth investigating:

```
Search the public web for candidate companies
        │
Visit their website (politely — no aggressive scraping, robots.txt respected)
        │
Work out what kind of business they are
   (Do they sell physical goods at all? Online store, wholesale, retail,
    subscription, marketplace, their own factory — any of these count.)
        │
Reject anything that clearly isn't a fit (software companies, agencies,
        competing logistics providers) — cheaply, before spending on the
        expensive steps
        │
Look for public evidence beyond their own site
   (job postings, funding announcements, press coverage, expansion news)
        │
Score how strong the signals are, weighing:
   • how many relevant signals were found, and how strong each one is
   • how fresh they are (a signal from 18 months ago counts for much
     less than one from last week)
   • a second opinion from an AI model reading the same evidence
     (deliberately capped in influence — see below)
   • how well-sourced the whole picture is
        │
Only for the strongest matches: identify the person most likely to be
        the decision maker, from the company's own published pages
        │
Show up in the dashboard, ranked, with every claim traceable
```

Nothing about this is a black box — every score comes with a full breakdown of exactly which facts earned it how many points, visible on the lead detail page.

---

## Why the scoring can be trusted

Three design choices exist specifically to prevent the two failure modes every lead-scoring tool eventually hits — **AI overconfidence** and **stale data**:

- **The AI never gets the final word.** It contributes a capped share of the score (30% by default) as a "second opinion" on evidence already gathered — it cannot invent a hot lead out of nothing. If it reports high confidence but the system found zero supporting facts, that confidence is automatically discounted. If no AI model is even configured, the system just leans more heavily on the deterministic evidence — it doesn't quietly under-score everything.
- **Signals expire.** A funding round from a year and a half ago stops counting for much; a warehouse-hiring post from last week counts for a lot. Scores are recalculated nightly from stored evidence so a lead's ranking reflects how current the signal actually is, not just when it was last looked at.
- **An existing competitor doesn't disqualify a company** — it reduces the score, because a brand with an existing 3PL may still need overflow capacity, a second location, or an international partner. The scoring reflects that nuance instead of a blunt yes/no filter.

---

## What this deliberately does not do

**It does not find, verify, or store email addresses. This is a hard product constraint, not an oversight** — enforced in the software itself (an automated test fails the build if an email field is ever added), not just a policy decision that could quietly erode. A qualified lead here is: **Company + Intent + Evidence + Decision Maker** — never an email address to spam.

**It does not scrape LinkedIn or any social network** for profile data. The decision-maker names and titles it surfaces come only from a company's own public website (their team page, a press quote, a job listing) — never a third-party profile. LinkedIn domains are explicitly excluded from candidate discovery entirely.

**It does not ignore a person's request to be left out.** There's a built-in suppression list — anyone (or any company) added to it is never written to, and any existing record is deleted immediately.

**It does not keep data forever.** Records for companies that have gone quiet (no relevant activity in a year) are automatically dropped on a weekly schedule.

Practically, this means the tool hands a sales team a warm, evidenced, named contact and lets them do the outreach part themselves — through email finders, LinkedIn, or however they already prospect — rather than trying to be a data broker.

---

## Why "3PL first" doesn't mean "3PL only"

The product is built so that everything specific to the logistics industry — which signals matter, how much each is worth, which job titles count as a decision maker, what search queries find candidates — lives in configuration, not in the underlying engine. The engine itself only ever answers two generic questions: *"what kind of company is this?"* and *"how strong is the evidence that they need [service]?"*

That means launching a second vertical — packaging suppliers, freight brokers, warehouse insurance, anything sold B2B where public signals predict intent — is a configuration exercise (new signal definitions, new discovery queries, a new scoring prompt), not a new build. The same crawled company data is reused; nothing has to be rediscovered from scratch.

---

## Segments this already covers (3PL launch)

The qualification bar is deliberately broader than "has an online store" — **anyone who physically moves goods** is in scope, because they all eventually need warehousing and fulfillment:

| Who | Why they need a 3PL |
|---|---|
| DTC / ecommerce brands | Order fulfilment, returns handling |
| Wholesale / B2B sellers | Pallet-scale storage, trade-order pick & pack |
| Manufacturers / CPG brands | Warehousing between production and retail |
| Retail / omnichannel brands | Retail-compliant, multi-destination fulfilment |
| Marketplace sellers (Amazon/eBay/Etsy) | Multi-channel inventory management |
| Subscription box companies | Predictable, recurring high-volume waves |
| Importers | Container handling, customs, deconsolidation |

The strongest single signal the system looks for is a company **publicly saying they're already shopping for a fulfilment partner** — at that point they're not a prospect to warm up, they're mid-decision.

---

## Operating model

- **Runs continuously in the background** — a daily discovery pass finds new candidate companies, an hourly pass works through the processing queue, and scores are refreshed nightly so rankings stay current without anyone re-running anything manually.
- **Self-serve tuning** — signal weights, which job titles matter, and the search queries used to find candidates can all be adjusted through the admin API without a code deployment or a release cycle.
- **Cost-aware by design** — the expensive steps (AI analysis, deep evidence lookups, decision-maker research) are gated behind cheaper checks, so spend scales with how promising a company already looks, not with how many companies exist on the internet.
- **A feedback loop is built in** — leads can be labeled (excellent/good/maybe/bad) directly in the dashboard, which is designed to answer the only question that ultimately matters: *what fraction of "HOT" leads are actually good?* — before scaling to more volume or a second vertical.

---

## Compliance posture

Because the system stores named individuals, standard data-protection obligations apply (GDPR/UK GDPR, for any subject based in the EU/UK). The product includes the technical building blocks — a right-to-object/suppression mechanism, an erasure endpoint, automatic retention limits, full source/provenance tracking on every person record. It does **not** include a Legitimate Interests Assessment or a published privacy policy — those remain the operator's responsibility before selling access to leads containing personal data, and a short consult with a privacy lawyer is recommended. This overview is not legal advice.
