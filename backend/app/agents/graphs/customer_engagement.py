"""Customer Engagement Agent — handles ongoing text conversations with customers.

This agent manages all customer interactions after initial lead onboarding:
- Proactive status updates ("Your crew is arriving tomorrow at 8am")
- Answering questions about scheduling, pricing, process
- Handling objections ("That's too expensive")
- Upsells via polls ("Add ice/water shield? Reply YES for $450")
- Escalation on complex/emotional topics

Uses project context + message history + semantic cache for continuity.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------

class EngagementState(TypedDict):
    """State for the customer engagement agent."""

    # Context
    company_id: str
    customer_phone: str
    from_phone: str
    project_id: str

    # Conversation
    messages: Annotated[list[dict], operator.add]
    current_input: str
    media_urls: list[str]

    # Project context (loaded from DB)
    project_context: dict

    # Agent outputs
    intent: str
    response_text: str
    upsell_offered: str
    needs_escalation: bool
    escalation_reason: str
    confidence: float


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def load_project_context(state: EngagementState) -> dict:
    """Load current project status and recent messages for context."""
    from app.agents.tools.project_tools import get_project_details

    project_id = state.get("project_id", "")
    if not project_id:
        return {"project_context": {}}

    details = await get_project_details.ainvoke({
        "company_id": state["company_id"],
        "project_id": project_id,
    })

    return {"project_context": details}


async def classify_and_respond(state: EngagementState) -> dict:
    """Classify the customer's message and generate an appropriate response.

    Handles: questions, objections, scheduling, upsells, simple confirmations.
    """
    project_ctx = state.get("project_context", {})

    # Build conversation context
    recent_messages = "\n".join(
        f"{m.get('role', 'unknown')}: {m.get('content', '')}"
        for m in state.get("messages", [])[-8:]
    )

    project_summary = ""
    if project_ctx:
        project_summary = (
            f"Project Status: {project_ctx.get('status', 'unknown')}\n"
            f"Type: {project_ctx.get('project_type', 'unknown')}\n"
            f"Address: {project_ctx.get('property_address', 'N/A')}\n"
            f"Estimate: ${project_ctx.get('estimate_low', 0):,.0f} – "
            f"${project_ctx.get('estimate_high', 0):,.0f}\n"
            f"Contract: ${project_ctx.get('contract_amount', 0):,.0f}"
        )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly, professional roofing/siding company assistant "
                        "communicating via text message. You represent the company and help "
                        "customers with their ongoing project.\n\n"
                        f"Project Info:\n{project_summary}\n\n"
                        f"Recent Conversation:\n{recent_messages}\n\n"
                        "Rules:\n"
                        "- Keep responses SHORT (under 300 chars for SMS)\n"
                        "- Be warm, professional, and reassuring\n"
                        "- If the customer has a pricing objection, acknowledge it empathetically "
                        "and explain the value (quality materials, warranty, licensed crew)\n"
                        "- If they ask about financing or payment plans, mention milestone-based "
                        "payments (deposit, progress, final) and that we accept all major cards\n"
                        "- If they mention insurance, note that we work with insurance claims "
                        "and can help with documentation, but flag for human follow-up\n"
                        "- If they ask about timing/schedule, give the project status\n"
                        "- If they seem upset or the topic is complex (insurance, legal, major "
                        "scope change), flag for escalation\n"
                        "- Look for natural upsell moments (ice shield, gutter guards, "
                        "ridge vent upgrade) but don't be pushy\n\n"
                        "Respond in this format:\n"
                        "INTENT: question|objection|confirmation|scheduling|upsell_opportunity|complaint|other\n"
                        "RESPONSE: <your message to the customer>\n"
                        "NEEDS_ESCALATION: yes|no\n"
                        "ESCALATION_REASON: <reason or empty>\n"
                        "UPSELL: <product or empty>\n"
                        "CONFIDENCE: <0.0 to 1.0>"
                    ),
                },
                {"role": "user", "content": state["current_input"]},
            ],
            tier=ModelTier.STANDARD,
            temperature=0.4,
            max_tokens=500,
            tenant_id=state.get("company_id"),
        )
    )

    parsed = _parse_response(response.content)

    return {
        "intent": parsed.get("intent", "other"),
        "response_text": parsed.get("response", "Thanks for your message! We'll look into that."),
        "needs_escalation": parsed.get("needs_escalation", "no").lower() == "yes",
        "escalation_reason": parsed.get("escalation_reason", ""),
        "upsell_offered": parsed.get("upsell", ""),
        "confidence": float(parsed.get("confidence", "0.7")),
    }


async def handle_upsell(state: EngagementState) -> dict:
    """If there's an upsell opportunity, add a poll-style offer."""
    upsell = state.get("upsell_offered", "")
    if not upsell:
        return {}

    # Append upsell to response
    upsell_text = f"\n\n💡 Upgrade option: {upsell}. Want details? Reply YES."
    current_response = state.get("response_text", "")

    return {"response_text": current_response + upsell_text}


async def send_response(state: EngagementState) -> dict:
    """Send the response to the customer."""
    from app.agents.tools.messaging import send_text_message

    response_text = state.get("response_text", "")
    if not response_text:
        return {}

    await send_text_message.ainvoke({
        "to_phone": state["customer_phone"],
        "body": response_text,
        "from_phone": state.get("from_phone"),
    })

    return {
        "messages": [{"role": "assistant", "content": response_text}],
    }


async def escalate(state: EngagementState) -> dict:
    """Escalate to human with context."""
    return {
        "response_text": (
            "Great question — let me connect you with a team member who can "
            "help with that. They'll reach out shortly!"
        ),
        "needs_escalation": True,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_classify(state: EngagementState) -> str:
    if state.get("needs_escalation"):
        return "escalate"
    if state.get("upsell_offered"):
        return "upsell"
    return "respond"


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------

def build_customer_engagement_graph() -> StateGraph:
    """Construct the Customer Engagement Agent graph.

    Flow:
        load_context → classify_respond → upsell → respond
                                        ↓
                                     escalate → respond
    """
    graph = StateGraph(EngagementState)

    graph.add_node("load_context", load_project_context)
    graph.add_node("classify_respond", classify_and_respond)
    graph.add_node("upsell", handle_upsell)
    graph.add_node("respond", send_response)
    graph.add_node("escalate", escalate)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify_respond")

    graph.add_conditional_edges("classify_respond", route_after_classify, {
        "escalate": "escalate",
        "upsell": "upsell",
        "respond": "respond",
    })

    graph.add_edge("upsell", "respond")
    graph.add_edge("escalate", "respond")
    graph.add_edge("respond", END)

    return graph


customer_engagement_graph = build_customer_engagement_graph().compile()


def _parse_response(content: str) -> dict:
    result: dict[str, str] = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if value:
                result[key] = value
    return result
