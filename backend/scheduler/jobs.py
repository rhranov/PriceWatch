"""
APScheduler 4 setup for the local backend.

Jobs:
  export_watchlist_job  — write data/sync/watchlist_export.json every hour at :50
                          so the Claude agent always has fresh data to read
  import_runs_job       — ingest run-result JSON the Claude agent wrote into
                          data/sync/runs/ (every 5 minutes)
  price_check_job       — scrape all active listings for price updates (every 6 hours)
                          pure Playwright, no LLM calls

Research (discovery of new products) is NOT a backend job.
It is performed by an optional external research workflow at 10:00 Berlin.
"""

from datetime import datetime, timezone
import asyncio

import structlog
from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.eventbrokers.asyncpg import AsyncpgEventBroker
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import settings

log = structlog.get_logger(__name__)

_scheduler: AsyncScheduler | None = None
_price_check_lock = asyncio.Lock()
_background_price_checks: set[asyncio.Task] = set()




async def export_watchlist_job():
    """Refresh the watchlist export the Claude agent reads via the device bridge."""
    from backend.sync.export_watchlist import main as export_main

    log.info("Sync: exporting watchlist", time=datetime.now().isoformat())
    await export_main()

    ir.QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

async def import_runs_job():
    """Ingest any run-result files the Claude agent has written back."""
    from backend.sync import import_run as ir

    ir.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    ir.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pending = sorted(ir.RUNS_DIR.glob("*.json"))
    if not pending:
        return
    for path in pending:
        try:
            target = ir.QUARANTINE_DIR / path.name
            if target.exists():
                target = ir.QUARANTINE_DIR / f"{path.stem}-{int(datetime.now().timestamp())}{path.suffix}"
            path.replace(target)
            summary = await ir.import_run_file(path)
            path.rename(ir.PROCESSED_DIR / path.name)
            log.info("Sync: imported run file", summary=summary)
        except Exception as exc:
            log.error("Sync: import failed", file=path.name, error=str(exc))


async def _run_reserved_price_check():
    try:
        return await _price_check_job_impl()
    finally:
        _price_check_lock.release()


async def start_price_check_background() -> bool:
    """Reserve the shared job lease before returning from a manual trigger."""
    if _price_check_lock.locked():
        return False
    await _price_check_lock.acquire()
    task = asyncio.create_task(_run_reserved_price_check())
    _background_price_checks.add(task)
    task.add_done_callback(_background_price_checks.discard)
    return True


async def price_check_job():
    """Run a scheduled price check only when the shared lease is available."""
    if _price_check_lock.locked():
        log.warning("Price check skipped because another run is active")
        return {"status": "already_running"}
    await _price_check_lock.acquire()
    return await _run_reserved_price_check()


def is_price_check_running() -> bool:
    return _price_check_lock.locked()


async def _price_check_job_impl():
    """
    Scrape all active product listings for current prices and availability.
    Pure Playwright — no LLM calls. Runs every 6 hours.
    """
    import traceback
    from backend.db.session import get_session
    from backend.db.models import AgentRun
    from backend.agents.price_checker import PriceCheckerAgent
    from sqlalchemy import select as sa_select

    log.info("Price check job starting", time=datetime.now().isoformat())

    run_id = None
    try:
        async with get_session() as session:
            run = AgentRun(run_type="price_check")
            session.add(run)
            await session.flush()
            run_id = str(run.id)
        log.info("Price check run created", run_id=run_id)
    except Exception as e:
        log.error("Price check: failed to create run record", error=str(e))
        return

    try:
        checker = PriceCheckerAgent()
        async with get_session() as session:
            result = await checker.check_all_listings(session, run_id)

        async with get_session() as session:
            from backend.db.models import Product, ProductScope, ProductListing
            from sqlalchemy import distinct

            scope_rows = (await session.execute(
                sa_select(distinct(ProductScope.slug))
                .join(Product, Product.scope_id == ProductScope.id)
                .join(ProductListing, ProductListing.product_id == Product.id)
                .where(ProductListing.is_active == True)
            )).scalars().all()
            scope_slugs = sorted(scope_rows)

            run_rec = (await session.execute(
                sa_select(AgentRun).where(AgentRun.id == run_id)
            )).scalar_one_or_none()
            if run_rec:
                has_errors = bool(result.get("errors"))
                run_rec.status = "completed_with_errors" if has_errors else "completed"
                run_rec.finished_at = datetime.now(timezone.utc)
                run_rec.products_checked = result.get("listings_checked", 0)
                run_rec.prices_updated = result.get("prices_updated", 0)
                run_rec.price_changes = result.get("price_changes", [])
                run_rec.errors = result.get("errors", [])
                run_rec.data_checks = result.get("data_checks", [])
                run_rec.scopes_checked = scope_slugs

        log.info("Price check completed", run_id=run_id, **{k: v for k, v in result.items() if k != "price_changes"})

    except Exception as e:
        log.error("Price check job failed", run_id=run_id, error=str(e), traceback=traceback.format_exc())
        try:
            async with get_session() as session:
                run_rec = (await session.execute(
                    sa_select(AgentRun).where(AgentRun.id == run_id)
                )).scalar_one_or_none()
                if run_rec:
                    run_rec.status = "failed"
                    run_rec.finished_at = datetime.now(timezone.utc)
                    run_rec.errors = [{"error": str(e)}]
        except Exception as e2:
            log.error("Failed to mark price check run as failed", error=str(e2))


async def deep_research_job():
    """
    Run deep research using the Software 3.0 ResearchAgent.
    Claude searches x.com, tech news, and German retailers for new products
    that qualify for the active scope. Verified discoveries go directly to
    pending_discoveries. No cron — triggered manually via API.
    """
    import traceback
    from backend.db.session import get_session
    from backend.db.models import AgentRun
    from backend.agents.researcher import ResearchAgent
    from sqlalchemy import select as sa_select

    log.info("Deep research job starting", time=datetime.now().isoformat())

    run_id = None
    try:
        async with get_session() as session:
            run = AgentRun(run_type="deep_research")
            session.add(run)
            await session.flush()
            run_id = str(run.id)
        log.info("Deep research run created", run_id=run_id)
    except Exception as e:
        log.error("Deep research: failed to create run record", error=str(e))
        return

    try:
        agent = ResearchAgent()
        async with get_session() as session:
            result = await agent.run(session, run_id)

        async with get_session() as session:
            run_rec = (await session.execute(
                sa_select(AgentRun).where(AgentRun.id == run_id)
            )).scalar_one_or_none()
            if run_rec:
                has_errors = bool(result.get("errors"))
                run_rec.status = "completed_with_errors" if has_errors else "completed"
                run_rec.finished_at = datetime.now(timezone.utc)
                run_rec.discoveries_found = result.get("discoveries_found", 0)
                run_rec.errors = result.get("errors", [])

        log.info("Deep research completed", run_id=run_id,
                 discoveries=result.get("discoveries_found", 0),
                 errors=len(result.get("errors", [])))

    except Exception as e:
        log.error("Deep research job failed", run_id=run_id, error=str(e),
                  traceback=traceback.format_exc())
        try:
            async with get_session() as session:
                run_rec = (await session.execute(
                    sa_select(AgentRun).where(AgentRun.id == run_id)
                )).scalar_one_or_none()
                if run_rec:
                    run_rec.status = "failed"
                    run_rec.finished_at = datetime.now(timezone.utc)
                    run_rec.errors = [{"error": str(e)}]
        except Exception as e2:
            log.error("Failed to mark research run as failed", error=str(e2))


async def stale_run_cleanup_job():
    """
    Mark any AgentRun still in 'running' state after 2 hours as failed.
    Price checks take ~10 minutes; research takes up to 1 hour. 2 hours is
    generous enough to never interrupt a legitimate run, but prevents runs
    from staying stuck for days if the process crashed or was interrupted.
    """
    from datetime import timedelta
    from backend.db.session import get_session
    from backend.db.models import AgentRun
    from sqlalchemy import select as sa_select

    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    async with get_session() as session:
        result = await session.execute(
            sa_select(AgentRun).where(
                AgentRun.status == "running",
                AgentRun.started_at < cutoff,
            )
        )
        stale = result.scalars().all()
        if not stale:
            return
        for run in stale:
            age_hours = (datetime.now(timezone.utc) - run.started_at).total_seconds() / 3600
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.errors = [{"error": f"Run timed out — stuck in 'running' state for {age_hours:.1f}h. Process likely crashed or was interrupted."}]
            log.warning("Stale run closed", run_id=str(run.id), run_type=run.run_type, age_hours=round(age_hours, 1))
        await session.commit()
        log.info("Stale run cleanup done", closed=len(stale))


async def get_scheduler() -> AsyncScheduler:
    global _scheduler
    if _scheduler is None:
        # Single-process deployment: the defaults (MemoryDataStore +
        # LocalEventBroker) are correct. Schedules are re-registered on every
        # startup, so nothing needs to persist. The previous SQLAlchemyDataStore
        # (sync URL) and AsyncpgEventBroker both break on apscheduler 4.0.0a5:
        # the store awaits a sync engine's dispose(), the broker's LISTEN
        # callback raises NoEventLoopError on Windows.
        _scheduler = AsyncScheduler()
    return _scheduler


async def start_scheduler():
    """Call on application startup."""
    scheduler = await get_scheduler()

    async with scheduler:
        existing = {s.id for s in await scheduler.get_schedules()}

        if "pricewatch_export" not in existing:
            await scheduler.add_schedule(
                export_watchlist_job,
                CronTrigger(minute=50, timezone=settings.scheduler_timezone),
                id="pricewatch_export",
                max_running_jobs=1,
            )
            log.info("Export job registered (hourly at :50)")

        if "pricewatch_import" not in existing:
            await scheduler.add_schedule(
                import_runs_job,
                IntervalTrigger(minutes=5),
                id="pricewatch_import",
                max_running_jobs=1,
            )
            log.info("Import job registered (every 5 minutes)")

        if "pricewatch_price_check" not in existing:
            await scheduler.add_schedule(
                price_check_job,
                CronTrigger(
                    hour="*/6",
                    minute=23,
                    timezone=settings.scheduler_timezone,
                ),
                id="pricewatch_price_check",
                max_running_jobs=1,
            )
            log.info("Price check job registered (every 6 hours)")

        if "pricewatch_stale_cleanup" not in existing:
            await scheduler.add_schedule(
                stale_run_cleanup_job,
                IntervalTrigger(minutes=30),
                id="pricewatch_stale_cleanup",
                max_running_jobs=1,
            )
            log.info("Stale-run cleanup job registered (every 30 minutes)")

        # Export immediately so the agent has data on first launch
        await export_watchlist_job()

        log.info("Scheduler started — export, import, price-check jobs active")
        await scheduler.run_until_stopped()
