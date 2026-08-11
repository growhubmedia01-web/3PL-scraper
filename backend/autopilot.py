import time
import requests
import datetime

print("Starting 3PL Auto Pilot (No-Docker Mode)...")
print("This script will run discovery and process the queue periodically.")

def log(msg):
    print(f"[{datetime.datetime.now().isoformat()}] {msg}")

while True:
    try:
        # 1. Run Discovery
        log("Triggering Discovery (finding new companies)...")
        res = requests.post("http://localhost:8000/api/discovery/run", json={"limit": 50})
        log(f"Discovery result: {res.status_code}")
        
        # 2. Process Queue
        log("Triggering Queue Processing (crawling companies)...")
        res = requests.post("http://localhost:8000/api/pipeline/process-queue?limit=40", json={})
        log(f"Queue processing result: {res.status_code}")
        
    except Exception as e:
        log(f"Error during autopilot: {e}")
    
    log("Sleeping for 1 hour... (Running in background)")
    time.sleep(3600)
