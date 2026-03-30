"""Agent Dispatch Workflow — routes inbound messages to the right LangGraph agent.

This is the bridge between Temporal (durability) and LangGraph (reasoning).
The workflow:
  1. Determines which agent should handle the message
  2. Runs the agent graph inside a Temporal Activity
  3. Logs the agent's actions to the audit trail
  4. Handles human escalation via Temporal signals

Pattern: Each LangGraph graph runs as a Temporal Activity. The Activity
is retryable, timeout-bounded, and its execution is recorded in Temporal's
workflow history for full visibility.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

from app.core.config import settings


# ---------------------------------------------------------------------------
# Input/Output
# ---------------------------------------------------------------------------

@dataclass
class AgentDispatchInput:
    """Input for the agent dispatch workflow."""

    company_id: str
    customer_phone: str
    from_phone: str  # Company's Twilio number
    message_body: str
    media_urls: list[str]
    message_id: str
    project_id: str = ""  # Empty if new lead


@dataclass
class AgentResult:
    """Result from running an agent."""

    agent_name: str
    response_sent: str
    stage: str
    project_id: str
    needs_human_review: bool
    confidence: float
    metadata: dict


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@activity.defn
async def determine_agent(input: AgentDispatchInput) -> str:
    """Determine which agent should handle this message.

    Logic:
    - No project_id → Lead Onboarding Agent (new lead)
    - Has project_id → Customer Engagement Agent (existing conversation)
    """
    if not input.project_id:
        # Check if we can find an existing project by phone number
        from app.core.database import get_tenant_session
        from app.models.project import Project, ProjectStatus
        from app.models.user import User
        from sqlalchemy import select

        async with get_tenant_session(input.company_id) as session:
            # Find customer by phone
            result = await session.execute(
                select(User).where(User.phone == input.customer_phone)
            )
            customer = result.scalar_one_or_none()

            if customer:
                # Find their most recent active project
                result = await session.execute(
                    select(Project)
                    .where(
                        Project.customer_id == customer.id,
                        Project.status.notin_([
                            ProjectStatus.PAID,
                            ProjectStatus.CANCELLED,
                        ]),
                    )
                    .order_by(Project.created_at.desc())
                    .limit(1)
                )
                project = result.scalar_one_or_none()
                if project:
                    return f"engagement:{project.id}"

    if input.project_id:
        return f"engagement:{input.project_id}"

    return "onboarding"


@activity.defn
async def run_lead_onboarding_agent(input: AgentDispatchInput) -> dict:
    """Run the Lead Onboarding Agent (LangGraph) as a Temporal Activity."""
    from app.agents.graphs.lead_onboarding import lead_onboarding_graph

    # Build initial state
    state = {
        "company_id": input.company_id,
        "customer_phone": input.customer_phone,
        "from_phone": input.from_phone,
        "current_input": input.message_body,
        "media_urls": input.media_urls,
        "messages": [{"role": "user", "content": input.message_body}],
        "stage": "new",
        "intent": "",
        "project_type": "",
        "property_address": "",
        "property_city": "",
        "property_state": "",
        "property_zip": "",
        "project_id": "",
        "customer_id": "",
        "photo_analysis": {},
        "estimated_sqft": 0.0,
        "estimate_low": 0.0,
        "estimate_high": 0.0,
        "estimate_text": "",
        "roof_complexity": "moderate",
        "needs_human_review": False,
        "human_review_reason": "",
        "confidence": 0.0,
        "response_text": "",
        "next_action": "",
    }

    # Run the graph
    result = await lead_onboarding_graph.ainvoke(state)

    return {
        "agent_name": "lead_onboarding",
        "response_sent": result.get("response_text", ""),
        "stage": result.get("stage", ""),
        "project_id": result.get("project_id", ""),
        "needs_human_review": result.get("needs_human_review", False),
        "confidence": result.get("confidence", 0.0),
        "metadata": {
            "intent": result.get("intent", ""),
            "project_type": result.get("project_type", ""),
            "estimate_low": result.get("estimate_low", 0),
            "estimate_high": result.get("estimate_high", 0),
        },
    }


@activity.defn
async def run_customer_engagement_agent(input: AgentDispatchInput, project_id: str) -> dict:
    """Run the Customer Engagement Agent (LangGraph) as a Temporal Activity."""
    from app.agents.graphs.customer_engagement import customer_engagement_graph

    state = {
        "company_id": input.company_id,
        "customer_phone": input.customer_phone,
        "from_phone": input.from_phone,
        "project_id": project_id,
        "current_input": input.message_body,
        "media_urls": input.media_urls,
        "messages": [{"role": "user", "content": input.message_body}],
        "project_context": {},
        "intent": "",
        "response_text": "",
        "upsell_offered": "",
        "needs_escalation": False,
        "escalation_reason": "",
        "confidence": 0.0,
    }

    result = await customer_engagement_graph.ainvoke(state)

    return {
        "agent_name": "customer_engagement",
        "response_sent": result.get("response_text", ""),
        "stage": result.get("intent", ""),
        "project_id": project_id,
        "needs_human_review": result.get("needs_escalation", False),
        "confidence": result.get("confidence", 0.0),
        "metadata": {
            "intent": result.get("intent", ""),
            "upsell_offered": result.get("upsell_offered", ""),
            "escalation_reason": result.get("escalation_reason", ""),
        },
    }


@activity.defn
async def log_agent_action(
    company_id: str,
    agent_name: str,
    project_id: str,
    action: str,
    confidence: float,
    metadata: dict,
) -> None:
    """Log agent action to the audit trail."""
    from app.core.database import get_tenant_session
    from app.models.audit import AuditLog

    async with get_tenant_session(company_id) as session:
        log = AuditLog(
            company_id=company_id,
            action=action,
            entity_type="project" if project_id else "message",
            entity_id=project_id if project_id else None,
            actor_type="agent",
            agent_name=agent_name,
            description=f"Agent {agent_name} executed: {action}",
            confidence_score=confidence,
            metadata_json=metadata,
        )
        session.add(log)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

@workflow.defn
class AgentDispatchWorkflow:
    """Dispatch inbound messages to the appropriate LangGraph agent.

    Runs the agent as a Temporal Activity with timeouts and retries.
    Supports human escalation via signals.
    """

    def __init__(self):
        self._human_approved = False

    @workflow.signal
    async def human_approval(self, approved: bool):
        """Signal from human to approve/reject an escalated action."""
        self._human_approved = approved

    @workflow.run
    async def run(self, input: AgentDispatchInput) -> dict:
        # 1. Determine which agent to use
        agent_route = await workflow.execute_activity(
            determine_agent,
            input,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # 2. Run the appropriate agent
        if agent_route.startswith("engagement:"):
            project_id = agent_route.split(":", 1)[1]
            result = await workflow.execute_activity(
                run_customer_engagement_agent,
                args=[input, project_id],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=2),
                ),
            )
        else:
            result = await workflow.execute_activity(
                run_lead_onboarding_agent,
                input,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=2),
                ),
            )

        # 3. Log to audit trail
        await workflow.execute_activity(
            log_agent_action,
            args=[
                input.company_id,
                result["agent_name"],
                result.get("project_id", ""),
                f"processed_message:{result.get('stage', '')}",
                result.get("confidence", 0.0),
                result.get("metadata", {}),
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        return result
