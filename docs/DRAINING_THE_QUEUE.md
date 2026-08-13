# Draining the queue on free-tier hosting

## Why `limit=50` will not work

`/api/pipeline/process-queue` runs synchronously - correctly, because a
FastAPI BackgroundTask is killed the moment the response is flushed on
free-tier hosts. But that makes the request duration equal to the work
duration, and one company is not a fixed cost:

| Per company | Time |
|---|---|
| Crawl, everything fast | ~30 s (12 pages x 2 s politeness delay) |
| Crawl, slow or flaky site | up to 264 s (12 x (2 s + 20 s timeout) + retries) |
| ATS job-board probing | was up to 225 s, now capped at 24 s |
| External SERP lookups | ~8 s |

So `limit=50` is **32 minutes in the good case** and several hours in the bad
one. No HTTP client waits that long.

## What changed

**The batch is bounded by time, not by count.**

```
POST /api/pipeline/process-queue?limit=8&max_seconds=240
```

- Stops cleanly when `max_seconds` is reached, even mid-queue.
- Commits after every company, so a batch cut short keeps everything it did.
- Reports what happened:

```json
{
  "processed": 6,
  "qualified": 4,
  "rejected": 2,
  "errors": 0,
  "elapsed_seconds": 238.4,
  "stopped_reason": "time_budget_reached",
  "queued_remaining": 287
}
```

`stopped_reason` is `completed` or `time_budget_reached`. The latter is not an
error - it means call it again.

**Each company is bounded too** (`CRAWL_MAX_SECONDS_PER_COMPANY`, default 45 s).
Without it one dead site could eat the whole budget: the deadline is only
checked *between* companies, so the true worst case is
`max_seconds + one company`.

**ATS probing is capped.** It was 3 slugs x 5 vendors at a 15 s timeout - 225
seconds of waiting on 404s for a single company. Now 2 slugs, 4 s timeout, and
a 24 s hard ceiling.

## Just drain it: one command

```powershell
cd G:\VE\3PL\backend
py scripts/drain_queue.py
```

Loops until the queue is empty. Leave it running.

```
    #      time   done   left   rate/h        eta  reason
  --------------------------------------------------------------
    1   0:04:12      8    285      114    2:29:00  time_budget_reached
    2   0:08:20     16    277      115    2:24:20  time_budget_reached
    3   0:12:31     23    270      110    2:27:15  time_budget_reached
```

What it handles:

| Situation | Behaviour |
|---|---|
| Host asleep | Waits for the cold start before the first batch, up to 5 min |
| `500/502/503/504` | Waits 10 s and retries, 5 attempts per batch |
| Connection dropped | Same retry path |
| Ctrl-C | Finishes the current batch, prints a summary. Press twice to quit now |
| Nothing progressing | Stops after 3 no-progress rounds instead of spinning forever |
| Restarted later | Resumes - the server commits per company, nothing is redone |
| Older deploy without `/pipeline/status` | Falls back to `/stats` automatically |

Options:

```powershell
py scripts/drain_queue.py --limit 8 --max-seconds 240 --sleep 5
py scripts/drain_queue.py --url https://threepl-scraper.onrender.com/api
py scripts/drain_queue.py --stall-limit 5      # more patient
```

Keep a log:

```powershell
py scripts/drain_queue.py *> drain.log
```

The read timeout is `max_seconds + 180`, because the server checks its deadline
*between* companies - the last one can run past the budget.

---

## Draining 293 companies

Pick a cadence, not a big batch.

| Setting | Value | Why |
|---|---|---|
| `limit` | 8 | Roughly what fits in 4 minutes |
| `max_seconds` | 240 | Comfortably inside any proxy timeout |
| Cron interval | every 10 min | ~48 companies/hour |

That clears the backlog in **about 6 hours**. Raise `max_seconds` if your host
tolerates longer requests, but check `elapsed_seconds` in the response first -
if it consistently equals your budget, you are being cut off rather than
finishing.

### cron-job.org setup

Two jobs:

| | URL | Method | Schedule |
|---|---|---|---|
| Drain | `https://<your-app>/api/pipeline/process-queue?limit=8&max_seconds=240` | POST | every 10 min |
| Discover | `https://<your-app>/api/discovery/run` | POST | daily |

Both need `Content-Type: application/json` and body `{}`.

**Set the cron-job.org timeout as high as it allows** (30 s on the free plan).
The request will usually exceed that and be recorded as a failure - **the work
still completes**, because the server keeps processing after the client hangs
up. Do not judge success by cron-job.org's status; use the endpoint below.

Also add a keep-alive job hitting `GET /health` every 10 minutes if your host
spins down when idle - otherwise the first real call each time is spent on a
cold start.

## Confirming the scheduler is actually firing

This was previously unanswerable: only discovery wrote a `pipeline_runs` row,
so a working `process-queue` cron left no trace beyond a slowly rising crawled
count.

Every invocation now records a run, and there is a single endpoint for it:

```
GET /api/pipeline/status
```

```json
{
  "queue": {"queued": 287, "crawled": 44, "rejected": 7,
            "total_companies": 338, "opportunities": 29},
  "scheduler": {
    "process_queue": {"ever_run": true, "minutes_ago": 3.2,
                      "status": "completed", "runs_last_24h": 141,
                      "stats": {"processed": 6, "stopped_reason": "..."}},
    "discovery":     {"ever_run": true, "minutes_ago": 512.0,
                      "runs_last_24h": 1}
  }
}
```

How to read it:

| Symptom | Meaning |
|---|---|
| `ever_run: false` | Cron has never reached the endpoint. Check the URL and method. |
| `minutes_ago` >> your interval | Cron stopped, or every call is failing before it starts work. |
| `runs_last_24h` far below expected | Calls are being dropped - often cold starts timing out. |
| `runs_last_24h` healthy, `queued` static | Work is running but not completing - check `status` and `error`. |
| `status: "failed"` | Read `error` on the run. |

## Watch for

**`queued` not falling while `crawled` rises slowly** is normal - rejected
companies leave the queue without being counted as crawled. Check `by_status`
for the full picture.

**A high `error` count** means sites are unreachable, not that the pipeline is
broken. `rejection_reason` on each company says which.

**If `elapsed_seconds` is always ~= `max_seconds`**, the queue is draining more
slowly than it looks. Either shorten the interval or raise the budget.
