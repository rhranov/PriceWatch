"""
Application entry point.
Starts both the FastAPI server and the APScheduler in the same process.
"""

import asyncio
import sys

import structlog
import uvicorn

from backend.config import settings

log = structlog.get_logger(__name__)


async def main():
    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )

    log.info("PriceWatch starting", host=settings.app_host, port=settings.app_port)

    # Close any runs that were left in "running" state by a previous process.
    # No run survives a process restart — they must be marked failed immediately.
    try:
        from datetime import datetime, timezone
        from backend.db.session import get_session
        from backend.db.models import AgentRun
        from sqlalchemy import select as sa_select
        async with get_session() as session:
            result = await session.execute(
                sa_select(AgentRun).where(AgentRun.status == "running")
            )
            stale = result.scalars().all()
            for run in stale:
                run.status = "failed"
                run.finished_at = datetime.now(timezone.utc)
                run.errors = [{"error": "Backend restarted while run was in progress"}]
            if stale:
                await session.commit()
                log.warning("Startup: closed stale runs", count=len(stale))
    except Exception as e:
        log.warning("Startup: failed to close stale runs", error=str(e))

    # Export watchlist immediately so the cloud agent always has fresh data
    # (before starting uvicorn, so the DB is definitely ready)
    try:
        from backend.sync.export_watchlist import main as export_main
        await export_main()
        log.info("Startup watchlist export complete")
    except Exception as e:
        log.warning("Startup watchlist export failed — will retry hourly", error=str(e))

    # Start the scheduler in a background task
    from backend.scheduler.jobs import start_scheduler

    scheduler_task = asyncio.create_task(start_scheduler())

    # Start the FastAPI server
    config = uvicorn.Config(
        "backend.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
        reload=settings.debug,
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
