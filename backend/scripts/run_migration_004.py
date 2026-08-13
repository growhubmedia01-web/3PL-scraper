"""Apply migration 004 via Supabase REST API (pg functions)."""
import httpx
import sys

SUPABASE_URL = "https://sgzaelsxfsoohzezpysy.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNnemFlbHN4ZnNvb2h6ZXpweXN5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NjI3NjQ1NiwiZXhwIjoyMDYxODUyNDU2fQ.RqW2TpTkqXbgMjlAoIhFkJvuOQ3Yn8pGt4FdElLmPDo"

sqls = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS business_model text",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_channels jsonb NOT NULL DEFAULT '[]'::jsonb",
    "CREATE INDEX IF NOT EXISTS idx_companies_business_model ON companies(business_model)",
]

headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

with httpx.Client(timeout=30) as client:
    for sql in sqls:
        print(f"Running: {sql[:70]}...")
        resp = client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
            json={"sql": sql},
            headers=headers,
        )
        if resp.status_code not in (200, 204):
            print(f"  STATUS {resp.status_code}: {resp.text}", file=sys.stderr)
        else:
            print(f"  OK")
