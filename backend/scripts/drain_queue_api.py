"""Drain the Render pipeline queue in small, safe batches from your local machine."""
import time
import sys
import httpx

API_URL = "https://threepl-scraper.onrender.com/api"
BATCH_LIMIT = 20  # Safe limit to prevent Render HTTP timeouts
DELAY_BETWEEN_BATCHES_SEC = 5

def get_stats():
    """Fetch current database stats from Render."""
    try:
        resp = httpx.get(f"{API_URL}/stats")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error fetching stats: {e}", file=sys.stderr)
    return None

def process_batch():
    """Trigger one synchronous queue processing batch on Render."""
    try:
        # POST request to process queue synchronous
        resp = httpx.post(
            f"{API_URL}/pipeline/process-queue?limit={BATCH_LIMIT}",
            headers={"Content-Type": "application/json"},
            json={},
            timeout=300.0  # 5 minute timeout for 20 companies
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Server returned status {resp.status_code}: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
    return None

def main():
    print("==================================================")
    print("   3PL Scraper - Queue Drainer Tool (Local)       ")
    print("==================================================")
    
    stats = get_stats()
    if not stats:
        print("❌ Could not connect to Render API. Make sure the server is awake.")
        return
        
    total = stats.get("total_companies", 0)
    crawled = stats.get("companies_crawled", 0)
    rejected = stats.get("companies_rejected", 0)
    leads = stats.get("total_opportunities", 0)
    queued = total - crawled - rejected
    
    print(f"Total Discovered : {total}")
    print(f"Already Crawled  : {crawled}")
    print(f"Total Leads Found: {leads}")
    print(f"Remaining Queue  : {queued}")
    
    if queued <= 0:
        print("\n✅ Queue is already empty!")
        return
        
    print(f"\nStarting to process {queued} companies in batches of {BATCH_LIMIT}...")
    
    batch_count = 1
    while True:
        print(f"\n[Batch {batch_count}] Processing next {BATCH_LIMIT} companies...")
        start_time = time.time()
        
        result = process_batch()
        
        elapsed = time.time() - start_time
        if result:
            message = result.get("message", "")
            print(f"Status: {message} (Took {elapsed:.1f}s)")
            
            # Fetch updated stats to check remaining queue
            stats = get_stats()
            if stats:
                total = stats.get("total_companies", 0)
                crawled = stats.get("companies_crawled", 0)
                rejected = stats.get("companies_rejected", 0)
                leads = stats.get("total_opportunities", 0)
                queued = total - crawled - rejected
                print(f"--> Leads: {leads} | Remaining in queue: {queued}")
                
                if queued <= 0:
                    print("\n🎉 Success! All companies in the queue have been processed.")
                    break
            else:
                # Fallback if stats check fails but response was OK
                if "No companies queued" in message or "0 still queued" in message:
                    print("\n🎉 Success! Queue is drained.")
                    break
        else:
            print("⚠️ Batch failed or timed out. Retrying in 10s...")
            time.sleep(10)
            continue
            
        print(f"Sleeping for {DELAY_BETWEEN_BATCHES_SEC}s before next batch...")
        time.sleep(DELAY_BETWEEN_BATCHES_SEC)
        batch_count += 1

if __name__ == "__main__":
    main()
