"""Database engine, session factory, and RLS tenant isolation.

Every request sets `app.current_company_id` on the connection so PostgreSQL
Row-Level Security policies can enforce tenant isolation automatically.
"""

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_UUID_RE = re.compile(r"^[0-9a-fA-F-]+$")

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_tenant_session(company_id: str) -> AsyncGenerator[AsyncSession]:
    """Yield a session with RLS company_id set for tenant isolation.

    Usage:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(query)
    """
    async with async_session_factory() as session:
        # Validate company_id to prevent SQL injection (should be a UUID)
        if not _UUID_RE.match(company_id):
            raise ValueError(f"Invalid company_id format: {company_id}")
        # Inline the value instead of using a bind parameter because asyncpg's
        # prepared-statement protocol doesn't support parameterized SET commands
        # through Neon's connection pooler.
        await session.execute(text(f"SET LOCAL app.current_company_id = '{company_id}'"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_system_session() -> AsyncGenerator[AsyncSession]:
    """Yield a session without tenant filtering (for system-level operations)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Ensure RLS variable exists even when not set (prevents errors on fresh connections)
@event.listens_for(engine.sync_engine, "connect")
def _set_default_company_id(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SELECT set_config('app.current_company_id', '', false)")
    cursor.close()
