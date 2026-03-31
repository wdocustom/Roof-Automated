"""FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)

# Global handle for the worker task so we can cancel on shutdown
_worker_task: asyncio.Task | None = None


async def _start_temporal_worker() -> None:
    """Start the Temporal worker as a background coroutine.

    Runs inside the same process as FastAPI on Railway (single-service deploy).
    If Temporal is unreachable, logs a warning and retries with backoff.
    """
    from app.workflows.worker import run_worker

    retry_delay = 5
    max_delay = 60

    while True:
        try:
            logger.info("Temporal worker connecting to %s ...", settings.temporal_host)
            await run_worker()
        except asyncio.CancelledError:
            logger.info("Temporal worker shutting down (cancelled)")
            return
        except Exception:
            logger.warning(
                "Temporal worker failed — retrying in %ds",
                retry_delay,
                exc_info=True,
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application startup and shutdown lifecycle."""
    global _worker_task

    # Start Temporal worker in background (non-blocking)
    if settings.temporal_host and settings.temporal_api_key:
        _worker_task = asyncio.create_task(_start_temporal_worker())
        logger.info("Temporal worker task started (background)")
    else:
        logger.info(
            "Temporal worker skipped (TEMPORAL_HOST=%s, TEMPORAL_API_KEY=%s)",
            settings.temporal_host,
            "set" if settings.temporal_api_key else "not set",
        )

    yield

    # Shutdown: cancel the worker task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        logger.info("Temporal worker stopped")


app = FastAPI(
    title="Roof Automated",
    description="Agentic AI Platform for Roofers & Siders",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    return {
        "service": "roof-automated",
        "version": "0.1.0",
        "status": "operational",
        "temporal_worker": "running" if (_worker_task and not _worker_task.done()) else "not running",
    }
