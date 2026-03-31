"""Health check endpoint — used by load balancers and monitoring."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check with DB and Temporal worker status."""
    from app.main import _worker_task

    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    worker_status = "not configured"
    if _worker_task is not None:
        worker_status = "running" if not _worker_task.done() else "stopped"

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "temporal_worker": worker_status,
    }
