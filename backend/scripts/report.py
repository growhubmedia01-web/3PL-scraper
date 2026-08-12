"""What's actually in my database? Run after clicking Discover.

    py -m scripts.report
    py -m scripts.report --leads      # show scored leads in detail
    py -m scripts.report --why        # explain why discovery found nothing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import desc, func, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ApiUsage, Company, CrawlJob, DecisionMaker, DiscoveryQuery, PipelineRun,
    ServiceOpportunity, Signal, Source,
)

BAR = "=" * 68


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads", action="store_true",
                        help="show each scored lead with its signals")
    parser.add_argument("--why", action="store_true",
                        help="diagnose why discovery returned nothing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print(BAR)
        print("  WHAT'S IN THE DATABASE")
        print(f"  {settings.database_url.split('@')[-1]}")
        print(BAR)

        companies = db.execute(select(func.count(Company.id))).scalar_one()
        opps = db.execute(select(func.count(ServiceOpportunity.id))).scalar_one()
        sigs = db.execute(select(func.count(Signal.id))).scalar_one()
        srcs = db.execute(select(func.count(Source.id))).scalar_one()
        dms = db.execute(select(func.count(DecisionMaker.id))).scalar_one()

        section("Totals")
        for label, value in [("companies discovered", companies),
                             ("opportunities scored", opps),
                             ("signals detected", sigs),
                             ("evidence sources", srcs),
                             ("decision makers", dms)]:
            print(f"  {label:24} {value}")

        # ---- discovery runs ----
        section("Discovery runs")
        runs = db.execute(
            select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(5)
        ).scalars().all()
        if not runs:
            print("  None. Discovery has never been triggered.")
        for run in runs:
            stats = run.stats or {}
            print(f"  {run.started_at:%Y-%m-%d %H:%M}  {run.run_type:12} "
                  f"{run.status}")
            if stats:
                print(f"      queries={stats.get('queries_run', 0)} "
                      f"results={stats.get('results_seen', 0)} "
                      f"domains={stats.get('domains_extracted', 0)} "
                      f"created={stats.get('companies_created', 0)} "
                      f"dupes={stats.get('duplicates_skipped', 0)} "
                      f"blocked={stats.get('blocked_skipped', 0)}")
            if run.error:
                print(f"      ERROR: {run.error[:160]}")

        # ---- company pipeline state ----
        if companies:
            section("Company status")
            for status, count in db.execute(
                select(Company.status, func.count(Company.id))
                .group_by(Company.status).order_by(desc(func.count(Company.id)))
            ).all():
                print(f"  {status:14} {count}")

            rejected = db.execute(
                select(Company.rejection_reason, func.count(Company.id))
                .where(Company.rejection_reason.is_not(None))
                .group_by(Company.rejection_reason)
                .order_by(desc(func.count(Company.id))).limit(6)
            ).all()
            if rejected:
                print("\n  Rejection reasons:")
                for reason, count in rejected:
                    print(f"    {count:4}x  {reason[:60]}")

            section(f"Companies found ({min(companies, 25)} of {companies})")
            for c in db.execute(
                select(Company).order_by(desc(Company.created_at)).limit(25)
            ).scalars().all():
                flags = []
                if c.is_ecommerce:
                    flags.append("ecom")
                if c.is_physical_product:
                    flags.append("physical")
                if c.platform:
                    flags.append(c.platform)
                print(f"  {c.domain:34} {c.country or '--':3} "
                      f"{c.status:11} {','.join(flags)}")
                if c.discovered_via:
                    print(f"      via: {c.discovered_via[:62]}")

        # ---- scored leads ----
        if opps:
            section("Scored leads")
            rows = db.execute(
                select(ServiceOpportunity, Company)
                .join(Company, Company.id == ServiceOpportunity.company_id)
                .order_by(desc(ServiceOpportunity.score))
            ).all()
            for opp, company in rows:
                print(f"  {float(opp.score):5.1f}  {opp.intent_level:9} "
                      f"{company.name or company.domain}")
                if args.leads:
                    types = db.execute(
                        select(Signal.signal_type)
                        .where(Signal.company_id == company.id)
                    ).scalars().all()
                    print(f"         signals: {', '.join(sorted(types)) or 'none'}")
                    person = db.execute(
                        select(DecisionMaker)
                        .where(DecisionMaker.company_id == company.id)
                        .order_by(DecisionMaker.role_priority)
                    ).scalars().first()
                    if person:
                        print(f"         contact: {person.name}, "
                              f"{person.job_title} "
                              f"({int(person.confidence * 100)}%)")

        # ---- diagnosis ----
        if args.why or (companies == 0 and runs):
            section("Why discovery found nothing")
            usage = db.execute(
                select(ApiUsage.provider, ApiUsage.success,
                       func.count(ApiUsage.id))
                .where(ApiUsage.operation.like("search%"))
                .group_by(ApiUsage.provider, ApiUsage.success)
            ).all()
            if not usage:
                print("  No search API calls were made at all.")
                print("  -> No search provider is configured, or discovery")
                print("     never actually ran. Check: py -m scripts.check_setup")
            for provider, success, count in usage:
                state = "succeeded" if success else "FAILED"
                print(f"  {provider}: {count} call(s) {state}")
                if not success:
                    print("  -> Your search API key is being rejected.")
                    print("     serper.dev keys are 40-char hex with no prefix;")
                    print("     a 'live_' prefix belongs to a different vendor.")
                    print("     Fix the key, or set SEARCH_PROVIDER=brave and")
                    print("     add BRAVE_SEARCH_API_KEY.")

            queries = db.execute(
                select(func.count(DiscoveryQuery.id))
                .where(DiscoveryQuery.enabled.is_(True))).scalar_one()
            print(f"\n  Enabled discovery queries: {queries}")
            if queries == 0:
                print("  -> No queries to run. Re-run the seed.")

        if companies and not opps:
            section("Companies found but none scored")
            pending = db.execute(
                select(func.count(Company.id))
                .where(Company.status.in_(("queued", "discovered")))).scalar_one()
            print(f"  {pending} companies are still queued.")
            print("  Discovery only creates records; crawling and scoring is")
            print("  a separate step. Click 'Process queue' on the dashboard,")
            print("  or POST /api/pipeline/process-queue?limit=25")

            failed = db.execute(
                select(func.count(CrawlJob.id))
                .where(CrawlJob.status == "failed")).scalar_one()
            skipped = db.execute(
                select(func.count(CrawlJob.id))
                .where(CrawlJob.status == "skipped")).scalar_one()
            if failed or skipped:
                print(f"\n  Crawl jobs: {failed} failed, {skipped} "
                      f"skipped (robots.txt)")

        print("\n" + BAR)
        if opps:
            print(f"  ANSWER: {companies} companies discovered, "
                  f"{opps} scored as leads.")
        elif companies:
            print(f"  ANSWER: {companies} companies discovered, "
                  f"0 scored yet — run 'Process queue'.")
        else:
            print("  ANSWER: 0 companies. See the diagnosis above.")
        print(BAR)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
