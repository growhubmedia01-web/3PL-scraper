"""Drain the crawl queue by calling the deployed API in a loop.

    py scripts/drain_queue.py
    py scripts/drain_queue.py --limit 8 --max-seconds 240
    py scripts/drain_queue.py --url https://threepl-scraper.onrender.com/api

Runs until the queue is empty. Safe to stop with Ctrl-C and restart - the
server commits after every company, so nothing already crawled is repeated.

Why a client-side loop rather than one big request: /pipeline/process-queue
runs synchronously (background tasks get killed on free-tier hosts), so the
request lasts as long as the work. Bounding each call and calling repeatedly
keeps every request short enough to survive gateway timeouts, and gives you
progress you can actually watch.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

DEFAULT_BASE = "https://threepl-scraper.onrender.com/api"

# The POST blocks for the whole batch, so the read timeout must exceed
# max_seconds with room for the server's own overshoot (it checks the
# deadline between companies, so the last one can run past it).
READ_TIMEOUT_MARGIN = 180

_stop = False


def _handle_interrupt(_signum, _frame):
    global _stop
    if _stop:
        print("\n  Force quit.")
        sys.exit(130)
    _stop = True
    print("\n  Interrupt received - finishing the current batch, then stopping."
          "\n  (Ctrl-C again to quit immediately.)")


@dataclass
class Progress:
    started: float = field(default_factory=time.monotonic)
    rounds: int = 0
    processed: int = 0
    errors: int = 0
    retries: int = 0
    start_queue: int | None = None
    last_queue: int | None = None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def rate_per_hour(self) -> float:
        hours = self.elapsed / 3600
        return self.processed / hours if hours > 0 else 0.0

    def eta(self, remaining: int) -> str:
        if self.processed == 0 or remaining <= 0:
            return "--"
        seconds = remaining * (self.elapsed / self.processed)
        return str(timedelta(seconds=int(seconds)))


def fmt_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


class Drainer:
    def __init__(self, base: str, limit: int, max_seconds: float,
                 sleep_between: float, retry_wait: float,
                 max_retries: int, stall_limit: int, service: str):
        self.base = base.rstrip("/")
        self.limit = limit
        self.max_seconds = max_seconds
        self.sleep_between = sleep_between
        self.retry_wait = retry_wait
        self.max_retries = max_retries
        self.stall_limit = stall_limit
        self.service = service
        self.progress = Progress()
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=30.0,
                read=max_seconds + READ_TIMEOUT_MARGIN,
                write=30.0, pool=30.0),
            headers={"Content-Type": "application/json"},
            follow_redirects=True,
        )

    # ---------------------------------------------------------------- status
    def queue_state(self) -> dict | None:
        """Prefer /pipeline/status; fall back to /stats on older deploys."""
        try:
            r = self.client.get(f"{self.base}/pipeline/status", timeout=60)
            if r.status_code == 200:
                q = r.json().get("queue", {})
                return {
                    "queued": q.get("queued", 0),
                    "crawled": q.get("crawled", 0),
                    "rejected": q.get("rejected", 0),
                    "errors": q.get("error", 0),
                    "total": q.get("total_companies", 0),
                    "opportunities": q.get("opportunities", 0),
                }
        except httpx.HTTPError:
            pass

        try:
            r = self.client.get(f"{self.base}/stats",
                                params={"service": self.service}, timeout=60)
            if r.status_code != 200:
                return None
            d = r.json()
            total = d.get("total_companies", 0)
            crawled = d.get("companies_crawled", 0)
            rejected = d.get("companies_rejected", 0)
            return {
                "queued": max(total - crawled - rejected, 0),
                "crawled": crawled, "rejected": rejected, "errors": 0,
                "total": total,
                "opportunities": d.get("total_opportunities", 0),
            }
        except httpx.HTTPError:
            return None

    def wait_until_awake(self, max_wait: float = 300) -> dict | None:
        """Free-tier hosts sleep when idle; the first request pays the cold
        start. Do that here rather than inside the first real batch."""
        print(f"  Waking {self.base} ...")
        deadline = time.monotonic() + max_wait
        attempt = 0
        while time.monotonic() < deadline and not _stop:
            attempt += 1
            state = self.queue_state()
            if state is not None:
                print(f"  Awake after {attempt} attempt(s).\n")
                return state
            wait = min(10 * attempt, 30)
            print(f"    no response (attempt {attempt}); retrying in {wait}s")
            time.sleep(wait)
        return None

    # ----------------------------------------------------------------- batch
    def run_batch(self) -> dict | None:
        """One POST. Returns the result payload, or None if it failed."""
        url = f"{self.base}/pipeline/process-queue"
        params = {"limit": self.limit, "max_seconds": self.max_seconds}

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.post(url, params=params, json={})
            except httpx.HTTPError as exc:
                self.progress.retries += 1
                if attempt == self.max_retries:
                    print(f"    connection failed after {attempt} attempts: "
                          f"{type(exc).__name__}")
                    return None
                print(f"    {type(exc).__name__} - retrying in "
                      f"{self.retry_wait:.0f}s ({attempt}/{self.max_retries})")
                time.sleep(self.retry_wait)
                continue

            if resp.status_code in (500, 502, 503, 504):
                self.progress.retries += 1
                if attempt == self.max_retries:
                    print(f"    HTTP {resp.status_code} after {attempt} "
                          f"attempts; giving up on this batch")
                    return None
                print(f"    HTTP {resp.status_code} - retrying in "
                      f"{self.retry_wait:.0f}s ({attempt}/{self.max_retries})")
                time.sleep(self.retry_wait)
                continue

            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            body = resp.json()
            if body.get("accepted") is False:
                return {"processed": 0, "queued_remaining": 0,
                        "message": body.get("message", ""), "empty": True}
            result = body.get("result") or {}
            result["message"] = body.get("message", "")
            return result

        return None

    # ------------------------------------------------------------------ loop
    def drain(self) -> int:
        state = self.wait_until_awake()
        if state is None:
            print("  Could not reach the API. Is the URL right and the "
                  "service deployed?")
            return 1

        self.progress.start_queue = state["queued"]
        self.progress.last_queue = state["queued"]

        print(f"  {'Queued':<14}{state['queued']}")
        print(f"  {'Crawled':<14}{state['crawled']}")
        print(f"  {'Rejected':<14}{state['rejected']}")
        print(f"  {'Opportunities':<14}{state['opportunities']}")
        print(f"  {'Total':<14}{state['total']}")
        print()
        if state["queued"] == 0:
            print("  Queue is already empty.")
            return 0

        print(f"  Batch size {self.limit}, budget {self.max_seconds:.0f}s, "
              f"{self.sleep_between:.0f}s between rounds. Ctrl-C to stop.\n")
        print(f"  {'#':>3}  {'time':>8}  {'done':>5}  {'left':>5}  "
              f"{'rate/h':>7}  {'eta':>9}  reason")
        print("  " + "-" * 62)

        stalled = 0
        while not _stop:
            self.progress.rounds += 1
            result = self.run_batch()

            if result is None:
                self.progress.errors += 1
                if self.progress.errors >= 5:
                    print("\n  Too many consecutive failures; stopping.")
                    break
                time.sleep(self.retry_wait)
                continue

            self.progress.errors = 0

            if result.get("empty"):
                print(f"\n  {result.get('message', 'Queue empty')}")
                break

            processed = int(result.get("processed", 0) or 0)
            remaining = int(result.get("queued_remaining", 0) or 0)
            reason = result.get("stopped_reason", "")
            self.progress.processed += processed

            print(f"  {self.progress.rounds:>3}  "
                  f"{fmt_duration(self.progress.elapsed):>8}  "
                  f"{self.progress.processed:>5}  {remaining:>5}  "
                  f"{self.progress.rate_per_hour:>7.0f}  "
                  f"{self.progress.eta(remaining):>9}  {reason}")

            if remaining <= 0:
                print("\n  Queue drained.")
                break

            # A batch that processes nothing and leaves the queue unchanged
            # means something is wrong server-side. Without this guard the
            # loop would spin forever.
            if processed == 0 and remaining == self.progress.last_queue:
                stalled += 1
                if stalled >= self.stall_limit:
                    print(f"\n  No progress in {stalled} rounds "
                          f"({remaining} still queued). Stopping.")
                    print("  Check /api/pipeline/status for the last run's "
                          "error.")
                    break
            else:
                stalled = 0
            self.progress.last_queue = remaining

            if _stop:
                break
            time.sleep(self.sleep_between)

        self.summary()
        return 0

    def summary(self) -> None:
        p = self.progress
        final = self.queue_state() or {}
        print()
        print("  " + "=" * 62)
        print("  SUMMARY")
        print("  " + "=" * 62)
        print(f"  {'Elapsed':<20}{fmt_duration(p.elapsed)}")
        print(f"  {'Rounds':<20}{p.rounds}")
        print(f"  {'Companies processed':<20}{p.processed}")
        print(f"  {'Retries':<20}{p.retries}")
        if p.start_queue is not None:
            print(f"  {'Queue at start':<20}{p.start_queue}")
        if final:
            print(f"  {'Queue now':<20}{final.get('queued', '?')}")
            print(f"  {'Crawled':<20}{final.get('crawled', '?')}")
            print(f"  {'Rejected':<20}{final.get('rejected', '?')}")
            print(f"  {'Opportunities':<20}{final.get('opportunities', '?')}")
        if p.processed:
            print(f"  {'Rate':<20}{p.rate_per_hour:.0f} companies/hour")
        print(f"  {'Finished':<20}{datetime.now():%Y-%m-%d %H:%M:%S}")
        print("  " + "=" * 62)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drain the crawl queue via the deployed API.")
    parser.add_argument("--url", default=DEFAULT_BASE, help="API base URL")
    parser.add_argument("--limit", type=int, default=8,
                        help="companies per batch (default 8)")
    parser.add_argument("--max-seconds", type=float, default=240,
                        help="server-side time budget per batch (default 240)")
    parser.add_argument("--sleep", type=float, default=5,
                        help="seconds between batches (default 5)")
    parser.add_argument("--retry-wait", type=float, default=10,
                        help="seconds to wait after a failure (default 10)")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--stall-limit", type=int, default=3,
                        help="stop after this many rounds with no progress")
    parser.add_argument("--service", default="3pl")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_interrupt)

    print()
    print("  " + "=" * 62)
    print("  DRAIN QUEUE")
    print("  " + "=" * 62)

    drainer = Drainer(args.url, args.limit, args.max_seconds, args.sleep,
                      args.retry_wait, args.max_retries, args.stall_limit,
                      args.service)
    try:
        return drainer.drain()
    finally:
        drainer.client.close()


if __name__ == "__main__":
    sys.exit(main())
