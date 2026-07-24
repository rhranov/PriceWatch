"""
Create all database tables directly from the SQLAlchemy models.

This project ships no Alembic migration revisions, so table creation is done
straight from the model metadata. `create_all` is idempotent — it only creates
tables that don't already exist, so it's safe to run on every startup.

Run: python -m backend.db.create_tables
"""

import asyncio

import structlog

# Importing models registers every table on Base.metadata
from backend.db.models import Base
from backend.db.session import engine

log = structlog.get_logger(__name__)


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tables = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"Tables ready: {tables}")


if __name__ == "__main__":
    asyncio.run(create_all())
