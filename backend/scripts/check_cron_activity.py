"""Check if cron job links are working by querying live DB and hitting endpoints."""
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import PipelineRun, Company

password = urllib.parse.quote("Shaik@HB1234")
url = f"postgresql+psycopg://postgres.sgzaelsxfsoohzezpysy:{password}@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
engine = create_engine(url)
db = Session(engine)

print("=== Latest Pipeline Runs ===")
runs = db.query(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(8).all()
for r in runs:
    started = r.started_at.isoformat() if r.started_at else "N/A"
    print(f"  {r.run_type} | {r.status} | {started} | err={r.error}")

print("\n=== Company Status Counts ===")
from sqlalchemy import func
statuses = db.query(Company.status, func.count(Company.id)).group_by(Company.status).all()
for status, count in statuses:
    print(f"  {status}: {count}")

print("\n=== Most Recently Touched Companies ===")
recent = db.query(Company).filter(Company.last_crawled_at != None).order_by(Company.last_crawled_at.desc()).limit(5).all()
for c in recent:
    crawled = c.last_crawled_at.isoformat() if c.last_crawled_at else "N/A"
    print(f"  {c.domain} | {c.status} | crawled={crawled}")
