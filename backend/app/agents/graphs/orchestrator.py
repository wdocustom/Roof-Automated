"""Orchestrator/Supervisor Agent — the swarm coordinator.

This is the brain of the multi-agent system. It:
  1. Maintains high-level project state
  2. Routes events to specialized agents
  3. Resolves conflicts (scheduling vs. QC vs. weather)
  4. Enforces business rules (milestone order, budget limits)
  5. Logs every decision for audit trail

The Orchestrator runs as a long-lived Temporal Workflow. Each specialized
agent runs as a child workflow or activity. Events flow through the
orchestrator, never directly between agents.

Architecture:
  Temporal Workflow (ProjectLifecycleWorkflow)
    └── LangGraph Orchestrator (decides what to do)
         ├── Project Execution Agent (scheduling, weather, crew)
         ├── Progress & QC Agent (photos, milestones, reports)
         ├── Payment & Closure Agent (invoicing, warranty)
         └── [Existing] Lead Onboarding / Customer Engagement
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.events import Event, EventType, emit_event, get_project_events
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


# ---------------------------------------------------------------------------
# Orchestrator State
# ---------------------------------------------------------------------------

class OrchestratorState(TypedDict):
    """High-level project state managed by the orchestrator."""

    # Context
    company_id: str
    project_id: str

    # Trigger
    trigger_event: dict  # The event that triggered this orchestration cycle
    trigger_type: str  # EventType value

    # Project snapshot (loaded from DB)
    project_status: str
    project_type: str
    milestones: list[dict]
    recent_events: list[dict]

    # Decision
    next_agent: str  # Which agent to dispatch to
    agent_input: dict  # Input for the agent
    decision_reasoning: str
    confidence: float

    # Outputs
    actions_taken: Annotated[list[dict], operator.add]
    events_emitted: Annotated[list[dict], operator.add]
    needs_human_escalation: bool
    escalation_reason: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def load_project_state(state: OrchestratorState) -> dict:
    """Load current project state and recent events from DB."""
    from app.agents.tools.project_tools import get_project_details

    project = await get_project_details.ainvoke({
        "company_id": state["company_id"],
        "project_id": state["project_id"],
    })

    events = await get_project_events(
        company_id=state["company_id"],
        project_id=state["project_id"],
        limit=20,
    )

    # Load milestones
    from app.core.database import get_tenant_session
    from app.models.project import ProjectMilestone
    from sqlalchemy import select
    import uuid

    milestones = []
    async with get_tenant_session(state["company_id"]) as session:
        result = await session.execute(
            select(ProjectMilestone)
            .where(ProjectMilestone.project_id == uuid.UUID(state["project_id"]))
            .order_by(ProjectMilestone.sort_order)
        )
        for m in result.scalars().all():
            milestones.append({
                "id": str(m.id),
                "name": m.name,
                "status": m.status.value,
                "requires_photo": m.requires_photo,
                "requires_human_signoff": m.requires_human_signoff,
            })

    return {
        "project_status": project.get("status", "unknown"),
        "project_type": project.get("project_type", "unknown"),
        "milestones": milestones,
        "recent_events": events,
    }


async def decide_next_action(state: OrchestratorState) -> dict:
    """Use LLM reasoning to decide which agent handles the current trigger.

    This is where the orchestrator's intelligence lives. It considers:
    - The trigger event
    - Current project status
    - Milestone progress
    - Recent event history
    - Business rules
    """
    trigger = state["trigger_event"]
    trigger_type = state["trigger_type"]

    # Build context for the LLM
    milestone_summary = "\n".join(
        f"  - {m['name']}: {m['status']}" for m in state.get("milestones", [])
    )

    recent_events_summary = "\n".join(
        f"  - [{e['event_type']}] {e.get('description', '')} ({e['agent_name']})"
        for e in state.get("recent_events", [])[:10]
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Orchestrator of a roofing/siding project management swarm. "
                        "You decide which specialized agent should handle events.\n\n"
                        "Available agents:\n"
                        "- execution: Handles scheduling, weather checks, crew dispatch, material ordering\n"
                        "- qc: Handles progress photos, milestone verification, QC reports\n"
                        "- payment: Handles invoicing, payment reminders, warranty generation\n"
                        "- engagement: Handles customer communication, objections, updates\n"
                        "- escalate: When human intervention is needed\n\n"
                        f"Project Status: {state.get('project_status', 'unknown')}\n"
                        f"Project Type: {state.get('project_type', 'unknown')}\n\n"
                        f"Milestones:\n{milestone_summary or '  (none configured)'}\n\n"
                        f"Recent Events:\n{recent_events_summary or '  (none)'}\n\n"
                        "Rules:\n"
                        "- Weather alerts → execution agent (check forecast, propose reschedule)\n"
                        "- Photo uploads → qc agent (analyze against milestone specs)\n"
                        "- Milestone completion → check if human sign-off needed\n"
                        "- Payment milestones → payment agent\n"
                        "- Customer messages → engagement agent\n"
                        "- Change order requests → escalate (requires human judgment)\n"
                        "- Measurement/drone reports received → execution agent (update estimates)\n"
                        "- Supplier price updates → no agent (informational only)\n"
                        "- Conflicts (e.g., weather delay + customer expects date) → resolve, "
                        "then notify via engagement\n"
                        "- If unsure → escalate to human\n\n"
                        "Respond:\n"
                        "AGENT: <agent name>\n"
                        "REASONING: <1-2 sentences why>\n"
                        "CONFIDENCE: <0.0-1.0>\n"
                        "NEEDS_ESCALATION: yes|no"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Event: {trigger_type}\n"
                        f"Data: {trigger.get('data', {})}\n"
                        f"Description: {trigger.get('description', '')}"
                    ),
                },
            ],
            tier=ModelTier.FAST,
            temperature=0.1,
            max_tokens=200,
            tenant_id=state.get("company_id"),
        )
    )

    parsed = _parse_response(response.content)

    return {
        "next_agent": parsed.get("agent", "escalate"),
        "decision_reasoning": parsed.get("reasoning", ""),
        "confidence": float(parsed.get("confidence", "0.5")),
        "needs_human_escalation": parsed.get("needs_escalation", "no").lower() == "yes",
    }


async def dispatch_to_agent(state: OrchestratorState) -> dict:
    """Dispatch to the chosen specialized agent.

    This node is a routing point — the actual agent execution happens
    in the Temporal workflow layer (as child workflows/activities).
    Here we prepare the input and record the dispatch decision.
    """
    agent = state["next_agent"]
    trigger = state["trigger_event"]

    # Emit orchestration event
    await emit_event(
        company_id=state["company_id"],
        event=Event(
            event_type=EventType.CREW_DISPATCHED if agent == "execution" else EventType.CUSTOMER_MESSAGE,
            agent_name="orchestrator",
            project_id=state["project_id"],
            data={
                "dispatched_to": agent,
                "trigger_type": state["trigger_type"],
                "reasoning": state["decision_reasoning"],
                "confidence": state["confidence"],
            },
            description=f"Orchestrator dispatched to {agent}: {state['decision_reasoning']}",
        ),
    )

    return {
        "agent_input": {
            "agent": agent,
            "project_id": state["project_id"],
            "company_id": state["company_id"],
            "trigger": trigger,
        },
        "actions_taken": [{
            "action": f"dispatch_to_{agent}",
            "reasoning": state["decision_reasoning"],
        }],
    }


async def handle_escalation(state: OrchestratorState) -> dict:
    """Handle cases requiring human intervention."""
    await emit_event(
        company_id=state["company_id"],
        event=Event(
            event_type=EventType.HUMAN_ESCALATION,
            agent_name="orchestrator",
            project_id=state["project_id"],
            data={
                "trigger_type": state["trigger_type"],
                "reasoning": state["decision_reasoning"],
                "confidence": state["confidence"],
            },
            description=f"Escalated to human: {state.get('escalation_reason', state['decision_reasoning'])}",
        ),
    )

    return {
        "actions_taken": [{"action": "human_escalation", "reasoning": state["decision_reasoning"]}],
        "escalation_reason": state.get("escalation_reason", state["decision_reasoning"]),
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_decision(state: OrchestratorState) -> str:
    if state.get("needs_human_escalation"):
        return "escalate"
    return "dispatch"


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> StateGraph:
    """Build the Orchestrator decision graph.

    Flow:
        load_state → decide → dispatch
                        ↓
                     escalate
    """
    graph = StateGraph(OrchestratorState)

    graph.add_node("load_state", load_project_state)
    graph.add_node("decide", decide_next_action)
    graph.add_node("dispatch", dispatch_to_agent)
    graph.add_node("escalate", handle_escalation)

    graph.set_entry_point("load_state")
    graph.add_edge("load_state", "decide")

    graph.add_conditional_edges("decide", route_after_decision, {
        "dispatch": "dispatch",
        "escalate": "escalate",
    })

    graph.add_edge("dispatch", END)
    graph.add_edge("escalate", END)

    return graph


orchestrator_graph = build_orchestrator_graph().compile()


def _parse_response(content: str) -> dict:
    result: dict[str, str] = {}
    for line in content.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if value:
                result[key] = value
    return result
