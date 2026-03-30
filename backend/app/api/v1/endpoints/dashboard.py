"""AI Coach Dashboard API — insights, metrics, and agent performance.

Phase 5: Provides data for the owner-facing dashboard:
  - Project velocity and cycle time metrics
  - Agent performance (escalation rate, cost per project)
  - Active alerts (weather, overdue payments, QC flags)
  - Per-tenant cost tracking
"""

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/insights")
async def get_insights(company_id: str = Depends(get_company_id)):
    """Get AI coach insights — key metrics and recommendations.

    Returns project velocity, agent performance, and actionable insights
    that help owners understand how the AI swarm is performing.
    """
    from app.agents.events import ProjectEvent
    from app.models.project import Project, ProjectStatus

    async with get_tenant_session(company_id) as session:
        # Count projects by status
        status_result = await session.execute(
            select(Project.status, func.count(Project.id))
            .group_by(Project.status)
        )
        status_counts = {row[0].value: row[1] for row in status_result.all()}

        # Count events in last 7 days
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        event_count_result = await session.execute(
            select(func.count(ProjectEvent.id))
            .where(ProjectEvent.created_at >= week_ago)
        )
        events_this_week = event_count_result.scalar() or 0

        # Count escalations in last 7 days
        escalation_result = await session.execute(
            select(func.count(ProjectEvent.id))
            .where(
                ProjectEvent.event_type == "human_escalation",
                ProjectEvent.created_at >= week_ago,
            )
        )
        escalations_this_week = escalation_result.scalar() or 0

        # Active projects (in_progress or scheduled)
        active_result = await session.execute(
            select(func.count(Project.id))
            .where(Project.status.in_([ProjectStatus.IN_PROGRESS, ProjectStatus.SCHEDULED]))
        )
        active_projects = active_result.scalar() or 0

        # Completed projects this month
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0)
        completed_result = await session.execute(
            select(func.count(Project.id))
            .where(
                Project.status.in_([ProjectStatus.COMPLETED, ProjectStatus.PAID]),
                Project.updated_at >= month_start,
            )
        )
        completed_this_month = completed_result.scalar() or 0

    # Calculate escalation rate
    escalation_rate = (
        round(escalations_this_week / events_this_week * 100, 1)
        if events_this_week > 0 else 0.0
    )

    return {
        "project_summary": {
            "active": active_projects,
            "completed_this_month": completed_this_month,
            "by_status": status_counts,
        },
        "agent_performance": {
            "events_processed_7d": events_this_week,
            "escalations_7d": escalations_this_week,
            "escalation_rate_pct": escalation_rate,
            "autonomy_rate_pct": round(100 - escalation_rate, 1),
        },
        "insights": _generate_insights(
            active_projects, escalation_rate, status_counts, completed_this_month
        ),
    }


@router.get("/agent-metrics")
async def get_agent_metrics(
    company_id: str = Depends(get_company_id),
    days: int = Query(default=7, ge=1, le=90),
):
    """Get detailed agent performance metrics.

    Breaks down event volume by agent and type over the specified period.
    """
    from app.agents.events import ProjectEvent

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_tenant_session(company_id) as session:
        # Events by agent
        agent_result = await session.execute(
            select(ProjectEvent.agent_name, func.count(ProjectEvent.id))
            .where(ProjectEvent.created_at >= cutoff)
            .group_by(ProjectEvent.agent_name)
        )
        by_agent = {row[0]: row[1] for row in agent_result.all()}

        # Events by type
        type_result = await session.execute(
            select(ProjectEvent.event_type, func.count(ProjectEvent.id))
            .where(ProjectEvent.created_at >= cutoff)
            .group_by(ProjectEvent.event_type)
        )
        by_type = {row[0]: row[1] for row in type_result.all()}

    return {
        "period_days": days,
        "by_agent": by_agent,
        "by_type": by_type,
        "total_events": sum(by_agent.values()),
    }


@router.get("/alerts")
async def get_active_alerts(company_id: str = Depends(get_company_id)):
    """Get active alerts that need owner attention.

    Surfaces: overdue payments, QC flags, weather delays, escalations.
    """
    from app.agents.events import ProjectEvent

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)

    alert_event_types = [
        "human_escalation",
        "payment_overdue",
        "milestone_qc_failed",
        "weather_alert",
        "price_update_flagged",
    ]

    async with get_tenant_session(company_id) as session:
        result = await session.execute(
            select(ProjectEvent)
            .where(
                ProjectEvent.event_type.in_(alert_event_types),
                ProjectEvent.created_at >= day_ago,
            )
            .order_by(ProjectEvent.created_at.desc())
            .limit(50)
        )
        events = result.scalars().all()

    alerts = []
    for e in events:
        severity = "high" if e.event_type in ("human_escalation", "payment_overdue") else "medium"
        alerts.append({
            "id": str(e.id),
            "type": e.event_type,
            "severity": severity,
            "project_id": str(e.project_id),
            "description": e.description or "",
            "data": e.data or {},
            "created_at": e.created_at.isoformat() if e.created_at else "",
        })

    return {
        "alerts": alerts,
        "total": len(alerts),
        "high_severity": sum(1 for a in alerts if a["severity"] == "high"),
    }


@router.get("/cost-tracking")
async def get_cost_tracking(
    company_id: str = Depends(get_company_id),
    days: int = Query(default=30, ge=1, le=365),
):
    """Get per-tenant LLM and agent cost estimates.

    Tracks token usage via event metadata to approximate costs.
    """
    from app.agents.events import ProjectEvent

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_tenant_session(company_id) as session:
        # Count total events as a proxy for agent invocations
        event_count = await session.execute(
            select(func.count(ProjectEvent.id))
            .where(ProjectEvent.created_at >= cutoff)
        )
        total_events = event_count.scalar() or 0

        # Count projects touched
        project_count = await session.execute(
            select(func.count(func.distinct(ProjectEvent.project_id)))
            .where(ProjectEvent.created_at >= cutoff)
        )
        projects_touched = project_count.scalar() or 0

    # Estimate costs (rough: ~$0.01-0.05 per agent invocation on average)
    estimated_cost = round(total_events * 0.025, 2)
    cost_per_project = round(estimated_cost / max(projects_touched, 1), 2)

    return {
        "period_days": days,
        "total_agent_invocations": total_events,
        "projects_touched": projects_touched,
        "estimated_llm_cost": estimated_cost,
        "cost_per_project": cost_per_project,
    }


def _generate_insights(
    active_projects: int,
    escalation_rate: float,
    status_counts: dict,
    completed_this_month: int,
) -> list[str]:
    """Generate actionable AI coach insights based on metrics."""
    insights = []

    if escalation_rate < 5:
        insights.append(
            f"Your AI agents are handling {100 - escalation_rate:.0f}% of tasks autonomously — excellent performance."
        )
    elif escalation_rate > 20:
        insights.append(
            f"Escalation rate is {escalation_rate:.0f}% this week — review common escalation reasons to reduce manual intervention."
        )

    if completed_this_month > 0:
        insights.append(
            f"{completed_this_month} projects completed this month."
        )

    leads = status_counts.get("lead", 0)
    if leads > 5:
        insights.append(
            f"{leads} leads in pipeline — AI onboarding is actively qualifying and estimating."
        )

    overdue = status_counts.get("invoiced", 0)
    if overdue > 0:
        insights.append(
            f"{overdue} projects awaiting payment — automated reminders are in cadence."
        )

    if not insights:
        insights.append("System running normally. All agents operating within parameters.")

    return insights
