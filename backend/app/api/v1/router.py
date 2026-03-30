"""API v1 router — aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.v1.endpoints import health, measurement_webhooks, photos, projects, webhooks

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(photos.router)
api_router.include_router(webhooks.router)
api_router.include_router(measurement_webhooks.router)
