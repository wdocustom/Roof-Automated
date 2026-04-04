"""API v1 router — aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    contracts,
    dashboard,
    health,
    measurement_webhooks,
    messages,
    onboarding,
    photos,
    projects,
    settings,
    stripe_webhooks,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(admin.router)
api_router.include_router(onboarding.router)
api_router.include_router(contracts.router)
api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(photos.router)
api_router.include_router(webhooks.router)
api_router.include_router(measurement_webhooks.router)
api_router.include_router(stripe_webhooks.router)
api_router.include_router(dashboard.router)
api_router.include_router(messages.router)
api_router.include_router(settings.router)
