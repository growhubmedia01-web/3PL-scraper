"""Check if cron job links are working by querying live DB and hitting endpoints."""
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, PipelineRun

engine = create_engine(settings.database_url)
db = Session(engine)

print("=== Latest Pipeline Runs ===")
runs = db.query(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(8).all()
for r in runs:
    started = r.started_at.isoformat() if r.started_at else "N/A"
    print(f"  {r.run_type} | {r.status} | {started} | err={r.error}")

print("\n=== Company Status Counts ===")
statuses = db.query(Company.status, func.count(Company.id)).group_by(Company.status).all()
for status, count in statuses:
    print(f"  {status}: {count}")

print("\n=== Most Recently Touched Companies ===")
recent = db.query(Company).filter(Company.last_crawled_at != None).order_by(Company.last_crawled_at.desc()).limit(5).all()
for c in recent:
    crawled = c.last_crawled_at.isoformat() if c.last_crawled_at else "N/A"
    print(f"  {c.domain} | {c.status} | crawled={crawled}")
