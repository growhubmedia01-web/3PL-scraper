"""Autopilot runner for automated discovery and pipeline queue processing.

Continuously searches the web and crawls companies until the target number of
LEADS (scored opportunities, default 500) is reached - or until the discovery
query library stops producing new companies, so it never re-buys the same
search results forever.

Usage:
    # Discover & enrich until 500 leads (or the library is exhausted):
    python autopilot.py --target-leads 500

    # Optional hard cap on companies added to the database:
    python autopilot.py --target-leads 500 --target-companies 3000

    # Custom speed or batch sizes:
    python autopilot.py --target-companies 500 --batch-size 15 --pause-seconds 10
"""
import argparse
import datetime
import sys
import time
import requests

DEFAULT_SERVICE = "powersports_aftermarket_sourcing"


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def get_status(base_url: str) -> dict:
    try:
        r = requests.get(f"{base_url}/pipeline/status", timeout=15)
        if r.status_code == 200:
            return r.json().get("queue", {})
    except Exception:
        pass
    return {}


def count_leads(base_url: str, service: str) -> int | None:
    """Opportunities for THIS service only. /pipeline/status counts every
    service, so on a shared database it includes legacy 3PL leads."""
    try:
        r = requests.get(f"{base_url}/services/{service}/opportunities",
                         params={"page_size": 1}, timeout=30)
        if r.status_code == 200:
            return int(r.json().get("total", 0))
    except Exception:
        pass
    return None


def run_discovery(base_url: str, service: str, limit: int = 50) -> dict:
    url = f"{base_url}/discovery/run"
    payload = {
        "service_slug": service,
        "limit": limit,
        "max_queries": 20,
        "run_async": False,
    }
    log(f"🔎 [AUTOMATED SEARCH] Running discovery queries to find new companies...")
    try:
        res = requests.post(url, json=payload, timeout=300)
        if res.status_code == 200:
            data = res.json().get("result", {})
            log(f"✅ [SEARCH DONE] Queries run: {data.get('queries_run', 0)} | "
                f"New companies added: {data.get('companies_created', 0)} | "
                f"Domains checked: {data.get('domains_extracted', 0)}")
            return data
        else:
            log(f"❌ Discovery HTTP {res.status_code}: {res.text[:200]}")
    except Exception as e:
        log(f"❌ Discovery failed: {e}")
    return {}


def process_queue(base_url: str, service: str, limit: int = 10, max_seconds: int = 180) -> dict:
    url = f"{base_url}/pipeline/process-queue?limit={limit}&max_seconds={max_seconds}"
    payload = {"service_slug": service}
    log(f"⚙️ [AUTOMATED CRAWLER] Crawling websites & extracting buying signals (batch size: {limit})...")
    try:
        # The server finishes the company in progress after max_seconds, which
        # can take another minute or two; each company is committed as it goes.
        res = requests.post(url, json=payload, timeout=max_seconds + 180)
        if res.status_code == 200:
            data = res.json().get("result", {})
            log(f"✅ [CRAWL DONE] Processed: {data.get('processed', 0)} | "
                f"Qualified: {data.get('qualified', 0)} | "
                f"Rejected: {data.get('rejected', 0)} | "
                f"Errors: {data.get('errors', 0)} | "
                f"Queued remaining: {data.get('queued_remaining', '?')}")
            return data
        else:
            log(f"❌ Crawler HTTP {res.status_code}: {res.text[:200]}")
    except Exception as e:
        log(f"❌ Crawler failed: {e}")
    return {}


def main():
    parser = argparse.ArgumentParser(description="Aggressive Local Autopilot for 500 Companies")
    parser.add_argument("--url", default="http://localhost:8000/api",
                        help="Base API URL (default: http://localhost:8000/api)")
    parser.add_argument("--service", default=DEFAULT_SERVICE,
                        help=f"Target service slug (default: {DEFAULT_SERVICE})")
    parser.add_argument("--target-leads", type=int, default=500,
                        help="Stop once this many opportunities exist (default: 500)")
    parser.add_argument("--target-companies", type=int, default=0,
                        help="Optional cap on companies in the DB (0 = no cap)")
    parser.add_argument("--max-empty-discoveries", type=int, default=2,
                        help="Stop after this many discovery runs in a row add "
                             "no new companies while the queue is empty")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Companies to crawl per batch (default: 10)")
    parser.add_argument("--pause-seconds", type=int, default=5,
                        help="Seconds to pause between crawl batches (default: 5)")
    args = parser.parse_args()

    api_base = args.url.rstrip("/")
    service = args.service
    target = args.target_leads
    company_cap = args.target_companies
    empty_discoveries = 0
    batch_size = args.batch_size
    pause_sec = args.pause_seconds

    print("=" * 65)
    print(" 🚀 LOCAL AUTOPILOT: AUTOMATED 500-COMPANY INGESTION ENGINE")
    print("=" * 65)
    print(f" Target Service:      {service}")
    print(f" Target Goal:         {target} leads (opportunities)")
    print(f" Company cap:         {company_cap or 'none'}")
    print(f" Target API:          {api_base}")
    print(f" Crawl Batch Size:    {batch_size} companies/batch")
    print("=" * 65, flush=True)

    # 1. Verify API Connection
    log("Checking connection to local backend (http://localhost:8000)...")
    connected = False
    for attempt in range(12):
        try:
            r = requests.get(f"{api_base.replace('/api', '')}/health", timeout=5)
            if r.status_code == 200:
                connected = True
                log("Backend connected successfully!")
                break
        except Exception:
            pass
        log(f"Waiting for backend to start... ({attempt + 1}/12)")
        time.sleep(3)

    if not connected:
        log("❌ Could not connect to backend. Make sure uvicorn is running:")
        log("   python -m uvicorn app.main:app --reload --port 8000")
        sys.exit(1)

    while True:
        try:
            status = get_status(api_base)
            total = status.get("total_companies", 0)
            queued = status.get("queued", 0)
            crawled = status.get("crawled", 0)
            opps = count_leads(api_base, service)
            if opps is None or not status:
                log("⚠️ API not answering - retrying in 15s")
                time.sleep(15)
                continue

            print("-" * 65)
            log(f"📊 [STATUS REPORT] Leads: {opps}/{target} | Companies in DB: {total} | Queued to crawl: {queued} | Crawled: {crawled}")
            print("-" * 65)

            if opps >= target:
                log(f"🎉 GOAL ACHIEVED: {opps} leads!")
                log("Autopilot complete. View all your leads in the frontend: http://localhost:5173")
                break

            capped = bool(company_cap) and total >= company_cap
            if queued == 0 and (capped or empty_discoveries >= args.max_empty_discoveries):
                reason = ("company cap reached" if capped else
                          "the discovery query library is exhausted "
                          f"({empty_discoveries} searches in a row found no new companies)")
                log(f"🛑 STOPPING with {opps} leads: {reason}. Add or widen queries "
                    "to find more.")
                break

            # Need more companies? Run a discovery search!
            if queued < 30 and not capped:
                log(f"⚡ {opps}/{target} leads. Running automatic search...")
                found = run_discovery(api_base, service, limit=50)
                if found.get("companies_created", 0) == 0:
                    empty_discoveries += 1
                else:
                    empty_discoveries = 0
                time.sleep(3)

            # Crawl pending companies in queue
            process_queue(api_base, service, limit=batch_size, max_seconds=180)

            log(f"Pausing {pause_sec}s before next batch...")
            time.sleep(pause_sec)

        except KeyboardInterrupt:
            log("Autopilot paused by user.")
            sys.exit(0)
        except Exception as exc:
            log(f"⚠️ Error in autopilot loop: {exc}")
            time.sleep(10)


if __name__ == "__main__":
    main()
