# Quickstart — run it, test it, and why your database is empty

## Your connection string — two things to know

You gave me:

```
postgresql://postgres:Shaik@HB1234@db.sgzaelsxfsoohzezpysy.supabase.co:5432/postgres
```

**1. The password contains `@`, which breaks URI parsing.** There are two `@`
signs, so the parser guesses wrong:

| | Parsed as |
|---|---|
| password | `Shaik` ← truncated |
| host | `HB1234@db.sgzaelsxfsoohzezpysy.supabase.co` ← wrong |

That produces a confusing DNS error rather than an auth error. It's written
into `.env` percent-encoded (`@` → `%40`), and `config.py` now auto-encodes and
warns if you paste a raw one again.

**2. It's a different Supabase project than your keys.**

| Setting | Project |
|---|---|
| `DATABASE_URL` | `sgzaelsxfsoohzezpysy` |
| `SUPABASE_URL` + service-role key | `rxpxwaabqrsbrfwwjaeo` |

**The backend works anyway** — it talks to Postgres directly through
SQLAlchemy and never uses the Supabase keys. But update `SUPABASE_URL` and both
keys to `sgzaelsxfsoohzezpysy` before you use supabase-js in the frontend or
call the REST API. `python -m scripts.check_setup` flags this.

**3. Rotate that password.** It's been shared in a chat transcript. Supabase →
Project Settings → Database → Reset database password.

---

## Why nothing is stored in the database

Nothing is stored because **the database was never created**. Three things have
to happen before a single row exists:

| Step | Status | What it does |
|---|---|---|
| 1. `DATABASE_URL` points at a real database | ✅ done — set above | Opens the connection |
| 2. Schema created + service config seeded | ❌ not yet | Creates the 11 tables and the 3PL signal weights |
| 3. Pipeline run at least once | ❌ not yet | Actually discovers and scores companies |

Step 1 was the original blocker — the `.env` shipped with a literal
`YOUR_DB_PASSWORD` placeholder, so no connection could open at all. That's now
fixed. **Steps 2 and 3 are what you need to run.**

Do them in order:

1. **Create the schema** — paste `backend/migrations/ALL_IN_ONE.sql` into the
   Supabase SQL Editor and press Run. No local connection needed.
2. **Point the app at the database** — see Path B below.
3. **Run the pipeline** — start the API and add a company.

```powershell
cd backend
py -m scripts.check_setup        # diagnoses whatever is still wrong
```

`check_setup` is the thing to reach for whenever you're unsure — it checks the
database, the schema, whether the service is seeded, how many rows exist, and
live-tests your search and LLM keys, then tells you what to fix.

---

## Path A — see it working in 3 minutes, zero setup

This uses a local SQLite file. No Supabase password, no search key, no LLM key.
Good for confirming the system works before you wire anything up.

**PowerShell:**

```powershell
cd backend
py -m pip install -r requirements.txt

$env:DATABASE_URL = "sqlite+pysqlite:///./local.db"
py -m scripts.seed --local
py -m uvicorn app.main:app --reload
```

**macOS / Linux:**

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL="sqlite+pysqlite:///./local.db" python -m scripts.seed --local
DATABASE_URL="sqlite+pysqlite:///./local.db" uvicorn app.main:app --reload
```

In a second terminal, run one real company through the whole pipeline:

```bash
curl -X POST http://localhost:8000/api/companies/add \
  -H "Content-Type: application/json" \
  -d '{"url":"https://allbirds.com"}'
```

Wait ~30 seconds (it crawls ~12 pages politely, with delays), then:

```bash
curl "http://localhost:8000/api/services/3pl/opportunities" | python -m json.tool
```

Third terminal for the dashboard:

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

> This path needs no Supabase connection at all — useful for confirming the
> pipeline works while you sort out DNS.

---

## Path B — wire up Supabase

### Step 1 — create the schema (no network needed)

**Do this in the Supabase SQL Editor.** It sidesteps drivers, DNS and IPv6
entirely, and it's the reliable path:

1. Open your project → **SQL Editor** → **New query**
2. Open `backend/migrations/ALL_IN_ONE.sql`, copy the whole file
3. Paste, press **Run**

It's idempotent — safe to run twice. The last statement prints a count so you
can confirm:

```
services | signals | keywords | queries | roles
       1 |      12 |       57 |      15 |    24
```

That's the schema created and the 3PL config seeded. **Your database now has
tables in it.**

### Step 2 — point the app at the database

The API needs a working connection string. If `db.<ref>.supabase.co` doesn't
resolve from your machine (see below), use the **transaction pooler**:

Supabase → Project Settings → Database → Connection string → **Transaction
pooler**. It looks like:

```
postgresql://postgres.sgzaelsxfsoohzezpysy:[PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Put it in `backend/.env` as `DATABASE_URL`, with the password percent-encoded
(`@` → `%40`):

```
DATABASE_URL=postgresql+psycopg://postgres.sgzaelsxfsoohzezpysy:Shaik%40HB1234@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Then:

```powershell
py -m scripts.check_setup
```

### `getaddrinfo failed` / `Errno 11001` / "could not translate host name"

This is a **DNS failure** — the hostname doesn't resolve at all. Check it:

```powershell
nslookup db.sgzaelsxfsoohzezpysy.supabase.co
```

If that returns "Non-existent domain", one of these is true:

| Cause | Fix |
|---|---|
| Direct hostnames are IPv6-only on projects created after early 2024, and often don't resolve on IPv4-only networks | Use the transaction pooler (IPv4), port 6543 |
| The project is **paused** — free Supabase projects pause after ~1 week idle | Open the dashboard and click Restore |
| Wrong project ref | Copy the connection string fresh from the dashboard |

You don't need to solve this to create the schema — Step 1 runs in the browser.
You only need it for the API to read and write.

---

## Windows / PowerShell notes

**`python` opens the Microsoft Store.** Windows ships a fake `python.exe` stub.
Use the launcher instead:

```powershell
py -m scripts.seed
py -m scripts.check_setup
py -m pytest
py -m uvicorn app.main:app --reload
```

Or disable the stub: Settings → Apps → Advanced app settings → App execution
aliases → turn off both `python.exe` entries.

**Environment variables inline don't work.** `DATABASE_URL="..." py script.py`
is bash syntax. In PowerShell:

```powershell
$env:DATABASE_URL = "sqlite+pysqlite:///./local.db"
py -m scripts.seed --local
```

Or just edit `backend/.env`, which is simpler.

**`curl` is an alias for `Invoke-WebRequest`** and takes different flags. Use
`curl.exe` explicitly, or use the dashboard buttons instead:

```powershell
curl.exe -X POST http://localhost:8000/api/companies/add `
  -H "Content-Type: application/json" `
  -d '{\"url\":\"https://allbirds.com\"}'
```

---

## Getting actual leads in there

### Fastest: one company you already know

No search key needed. Best first test — pick a brand you'd genuinely want as a
customer and see whether it scores the way you'd expect.

```bash
curl -X POST http://localhost:8000/api/companies/add \
  -H "Content-Type: application/json" \
  -d '{"url":"https://allbirds.com"}'
```

Or paste the URL into **Test the pipeline** on the dashboard.

### At scale: discovery

Needs a working search key (see below).

```bash
curl -X POST http://localhost:8000/api/discovery/run \
  -H "Content-Type: application/json" \
  -d '{"limit": 25}'

# discovery only creates company records — this crawls and scores them
curl -X POST "http://localhost:8000/api/pipeline/process-queue?limit=25" \
  -H "Content-Type: application/json" -d '{}'
```

Or use the **Run discovery** and **Process queue** buttons on the dashboard.

### Your Serper key needs verifying

```bash
curl -X POST https://google.serper.dev/search \
  -H "X-API-KEY: live_OgsqA9fABgwBIEwMZ1ZRXtDCUIB28Brh" \
  -H "Content-Type: application/json" \
  -d '{"q":"new DTC brand","num":3}'
```

- **200** → you're fine.
- **401/403** → the key is for a different vendor (serper.dev keys are 40-char
  hex, no prefix). Get one at serper.dev, or switch: set
  `SEARCH_PROVIDER=brave` and `BRAVE_SEARCH_API_KEY=...`. No code changes.

`check_setup` runs this test for you.

---

## Testing

### Automated tests — 45 of them

```bash
cd backend && pytest
```

No database, network or API keys needed. Covers scoring maths, freshness decay,
the guarantee that AI can't dominate the score, domain blocklists, signal
evidence, decision-maker ranking and suppression, and the no-email constraint.

```bash
pytest tests/test_scoring.py -v          # one file, verbose
pytest -k "decay or freshness" -v        # by name
```

### Frontend

```bash
cd frontend
npm run typecheck
npm run build
```

### Manual smoke test

```bash
curl http://localhost:8000/api/stats/health   # setup checklist as JSON
curl http://localhost:8000/api/services       # should list "3pl"
curl "http://localhost:8000/api/services/3pl/config"   # resolved weights
open http://localhost:8000/docs               # interactive API docs
```

### Does scoring agree with you?

The test that matters most isn't automated. Add 5–10 companies you already
believe are good 3PL prospects, and 5 you know are bad:

```bash
for url in brand-a.com brand-b.com brand-c.com; do
  curl -s -X POST http://localhost:8000/api/companies/add \
    -H "Content-Type: application/json" -d "{\"url\":\"https://$url\"}"
done
```

Then open each lead and read the score breakdown. If a good prospect scores
low, the breakdown shows you which signal was missed. **Fix that by changing
weights, not code:**

```bash
curl -X PATCH http://localhost:8000/api/admin/signals/{signal_id} \
  -H "X-Admin-Token: dev-secret-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"weight": 25}'
```

Get signal IDs from `GET /api/services/3pl/signals`. Re-score everything from
stored signals — no re-crawl, no API cost:

```bash
celery -A app.workers.celery_app call app.workers.tasks.recalculate_scores_task
```

---

## Background workers (optional)

The API works without Redis — it falls back to in-process background tasks.
For scheduled discovery and re-analysis:

```bash
docker compose up -d redis
cd backend
celery -A app.workers.celery_app worker --loglevel=info   # terminal 1
celery -A app.workers.celery_app beat   --loglevel=info   # terminal 2
```

---

## Troubleshooting

**`[WinError 10013] An attempt was made to access a socket in a way forbidden
by its access permissions`**

Windows is refusing the port bind. Despite the wording it usually is *not*
another app holding the port — Hyper-V, WSL and Docker Desktop reserve large
blocks of TCP ports, and anything inside a reserved block fails this way while
`netstat` shows nothing listening.

Easiest fix — let the app choose a working port:

```powershell
cd backend
py run.py
```

It tests the port first, falls back to the next usable one, and prints the URL
plus the exact `frontend/.env` line to match.

To see the reserved blocks:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

If `8000` falls inside one of those ranges, that's your answer. Other options:

| Fix | Command |
|---|---|
| Pick a port yourself | `py run.py --port 8123` |
| Check whether something really is listening | `netstat -ano \| findstr :8000` |
| Free the Hyper-V reservations (admin, needs reboot) | `net stop winnat` then `net start winnat` |

**If you change the API port**, update `frontend/.env`:

```
VITE_API_BASE_URL=http://localhost:8123
```

and restart `npm run dev`. The dashboard proxies `/api` to that address.


**`SystemExit: DATABASE_URL is not configured`** — the placeholder is still in
`.env`. That's step 1 above.

**`Service '3pl' not found`** — schema exists but wasn't seeded.
`python -m scripts.seed`.

**`connection to server ... failed`** — wrong password, or you're using the
pooler URL for migrations. Migrations need `DATABASE_MIGRATION_URL` (port 5432).

**Company added but no opportunity appears** — check its status:

```bash
curl "http://localhost:8000/api/companies?q=allbirds" | python -m json.tool
```

If `status` is `rejected`, read `rejection_reason`. "No ecommerce or
physical-product evidence found" is *correct* for SaaS and agencies. If a real
store is rejected, it's probably JavaScript-rendered:

```bash
pip install -r requirements-optional.txt
playwright install chromium
# then set PLAYWRIGHT_ENABLED=true in .env
```

**Everything scores ~45** — that's the required-signals cap. Those companies
are missing `ecommerce` or `physical_products`.

**No `urgency` or `likely_need` on any lead** — those come from AI analysis.
Add `GROQ_API_KEY` or `GEMINI_API_KEY` (free tiers available).

**Discovery returns 0 companies** — either the search key is rejected (run
`check_setup`), or every result was a marketplace/social domain, which the
blocklist strips by design.
