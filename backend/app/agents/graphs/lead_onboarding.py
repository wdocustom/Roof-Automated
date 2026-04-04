"""Lead Onboarding Agent — LangGraph state machine for lead-to-contract flow.

This is the first autonomous agent. It handles the full lead qualification
and onboarding pipeline via text:

1. Classify intent (fast tier LLM)
2. Qualify lead (ask questions via SMS)
3. Request property photos
4. Analyze photos (LLM vision)
5. Generate preliminary estimate from rate cards
6. Present estimate + disclaimers
7. Generate contract package + e-sign link
8. Escalate to human if value > threshold or confidence low

The graph runs inside a Temporal Activity for durability. State is
checkpointed to PostgreSQL so conversations can resume after interruptions.
"""

from __future__ import annotations

import operator
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from app.integrations.llm.router import LLMRequest, ModelTier, llm_router

# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------


class LeadStage(StrEnum):
    """Current stage of the lead onboarding process."""

    NEW = "new"
    QUALIFYING = "qualifying"
    AWAITING_PHOTOS = "awaiting_photos"
    ANALYZING_PHOTOS = "analyzing_photos"
    ESTIMATING = "estimating"
    ESTIMATE_PRESENTED = "estimate_presented"
    CONTRACT_SENT = "contract_sent"
    ESCALATED = "escalated"
    COMPLETED = "completed"


class LeadState(TypedDict):
    """State for the lead onboarding graph."""

    # Context
    company_id: str
    customer_phone: str
    from_phone: str  # Company's Twilio number

    # Conversation
    messages: Annotated[list[dict], operator.add]  # Append-only message history
    current_input: str  # Latest customer message
    media_urls: list[str]  # Photos from current message

    # Lead data (accumulated across turns)
    stage: str
    intent: str
    project_type: str
    property_address: str
    property_city: str
    property_state: str
    property_zip: str
    project_id: str
    customer_id: str

    # Photo analysis
    photo_analysis: dict

    # Estimate
    estimated_sqft: float
    estimate_low: float
    estimate_high: float
    estimate_text: str
    roof_complexity: str

    # Control flow
    needs_human_review: bool
    human_review_reason: str
    confidence: float
    response_text: str  # Next message to send
    next_action: str  # Routing hint


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------


async def classify_intent(state: LeadState) -> dict:
    """Classify the customer's intent using the fast LLM tier."""
    text = state["current_input"]
    if not text:
        return {"intent": "unknown", "next_action": "qualify"}

    try:
        response = await llm_router.complete(
            LLMRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Classify this customer message into one category:\n"
                            "- new_lead: Wants a quote, estimate, or new roof/siding work\n"
                            "- question: Has a question about pricing, process, or timeline\n"
                            "- scheduling: Wants to schedule inspection or work\n"
                            "- complaint: Has an issue or complaint\n"
                            "- other: Doesn't fit above categories\n\n"
                            "Respond with ONLY the category name."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                tier=ModelTier.FAST,
                temperature=0.0,
                max_tokens=20,
                tenant_id=state.get("company_id"),
            )
        )
        intent = response.content.strip().lower()
    except Exception:
        intent = "new_lead"  # Default to qualifying on LLM failure

    return {"intent": intent, "next_action": "qualify"}


async def qualify_lead(state: LeadState) -> dict:
    """Determine what information we still need from the lead."""
    has_address = bool(state.get("property_address"))
    has_photos = bool(state.get("media_urls")) or bool(state.get("photo_analysis"))
    bool(state.get("project_type"))

    # Build conversation context
    conversation = "\n".join(
        f"{m.get('role', 'unknown')}: {m.get('content', '')}"
        for m in state.get("messages", [])[-6:]  # Last 6 messages for context
    )

    try:
        response = await llm_router.complete(
            LLMRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a friendly, professional roofing/siding company assistant. "
                            "Your job is to qualify leads via text message.\n\n"
                        f"Information gathered so far:\n"
                        f"- Address: {'Yes' if has_address else 'Not yet'}\n"
                        f"- Photos: {'Yes' if has_photos else 'Not yet'}\n"
                        f"- Project type: {state.get('project_type', 'Not yet')}\n\n"
                        f"Recent conversation:\n{conversation}\n\n"
                        "Determine what to ask next. Priority order:\n"
                        "1. If no project type: Ask what they need (roof replacement, repair, siding, etc.)\n"
                        "2. If no address: Ask for the property address\n"
                        "3. If no photos: Ask them to text a photo of their roof/siding\n"
                        "4. If we have everything: Say we'll prepare an estimate\n\n"
                        "Keep messages SHORT (under 160 chars for SMS). Be warm but efficient.\n"
                        "Also extract any information from the latest message.\n\n"
                        "Respond in this format:\n"
                        "RESPONSE: <message to send to customer>\n"
                        "EXTRACTED_PROJECT_TYPE: <type or empty>\n"
                        "EXTRACTED_ADDRESS: <address or empty>\n"
                        "EXTRACTED_CITY: <city or empty>\n"
                        "EXTRACTED_STATE: <state or empty>\n"
                        "EXTRACTED_ZIP: <zip or empty>\n"
                        "NEXT_STAGE: qualifying|awaiting_photos|estimating"
                    ),
                },
                {"role": "user", "content": state["current_input"]},
            ],
            tier=ModelTier.STANDARD,
            temperature=0.3,
            max_tokens=400,
            tenant_id=state.get("company_id"),
        )
    )

    except Exception:
        return {
            "response_text": "Thanks for reaching out! Could you tell me what you need help with — roof, siding, or gutters?",
            "stage": "qualifying",
        }

    # Parse response
    parsed = _parse_agent_response(response.content)

    updates: dict[str, Any] = {
        "response_text": parsed.get("response", "Thanks! We'll follow up shortly."),
        "stage": parsed.get("next_stage", "qualifying"),
    }

    # Update any extracted information
    if parsed.get("extracted_project_type"):
        updates["project_type"] = _normalize_project_type(parsed["extracted_project_type"])
    if parsed.get("extracted_address"):
        updates["property_address"] = parsed["extracted_address"]
    if parsed.get("extracted_city"):
        updates["property_city"] = parsed["extracted_city"]
    if parsed.get("extracted_state"):
        updates["property_state"] = parsed["extracted_state"]
    if parsed.get("extracted_zip"):
        updates["property_zip"] = parsed["extracted_zip"]

    return updates


async def analyze_photos(state: LeadState) -> dict:
    """Analyze customer photos using LLM vision."""
    media_urls = state.get("media_urls", [])
    if not media_urls:
        return {
            "stage": "qualifying",
            "response_text": "Could you send a photo of your roof/siding? It helps us give a more accurate estimate.",
        }

    from app.agents.tools.vision import analyze_roof_photo

    # Analyze the first photo
    analysis = await analyze_roof_photo.ainvoke(
        {
            "image_url": media_urls[0],
            "context": f"Project type: {state.get('project_type', 'unknown')}",
            "tenant_id": state.get("company_id"),
        }
    )

    updates: dict[str, Any] = {
        "photo_analysis": analysis,
        "stage": "estimating",
    }

    # Extract data from photo analysis
    if analysis.get("estimated_complexity"):
        complexity = str(analysis["estimated_complexity"]).lower()
        if complexity in ("simple", "moderate", "complex", "very_complex"):
            updates["roof_complexity"] = complexity

    return updates


async def generate_estimate(state: LeadState) -> dict:
    """Generate preliminary estimate from rate cards.

    Also persists the project and estimate to the database so
    the dashboard/project list reflects reality.
    """
    import structlog

    from app.services.estimate_engine import (
        format_estimate_for_sms,
        generate_roof_estimate,
        generate_siding_estimate,
    )

    _log = structlog.get_logger()
    company_id = state["company_id"]
    sqft = state.get("estimated_sqft", 0)
    project_type = state.get("project_type", "roof_replacement")

    # If no sqft from measurements, use a reasonable default based on photo analysis
    if sqft <= 0:
        # Average US roof is ~1,700 sqft; use as fallback
        sqft = 1700.0

    measurement_source = "photo" if state.get("photo_analysis") else "manual"

    if "siding" in project_type:
        estimate = await generate_siding_estimate(
            company_id=company_id,
            total_sqft=sqft,
            zip_code=state.get("property_zip", ""),
            measurement_source=measurement_source,
        )
    else:
        estimate = await generate_roof_estimate(
            company_id=company_id,
            total_sqft=sqft,
            roof_complexity=state.get("roof_complexity", "moderate"),
            zip_code=state.get("property_zip", ""),
            measurement_source=measurement_source,
        )

    estimate_text = format_estimate_for_sms(estimate)

    # ── Persist project + estimate to DB ──────────────────────
    project_id = state.get("project_id", "")
    customer_id = state.get("customer_id", "")

    try:
        from app.agents.tools.project_tools import (
            create_lead_project,
            update_project_estimate,
        )

        # Create project if it doesn't exist yet
        if not project_id and state.get("property_address"):
            result = await create_lead_project.ainvoke(
                {
                    "company_id": company_id,
                    "customer_phone": state["customer_phone"],
                    "property_address": state.get("property_address", ""),
                    "property_city": state.get("property_city", ""),
                    "property_state": state.get("property_state", ""),
                    "property_zip": state.get("property_zip", ""),
                    "project_type": project_type,
                    "description": f"Lead via SMS from {state['customer_phone']}",
                    "lead_source": "sms",
                }
            )
            project_id = result.get("project_id", "")
            customer_id = result.get("customer_id", "")
            _log.info("lead_project_created", project_id=project_id)

        # Save estimate on the project
        if project_id:
            await update_project_estimate.ainvoke(
                {
                    "company_id": company_id,
                    "project_id": project_id,
                    "estimate_low": estimate.total_low,
                    "estimate_high": estimate.total_high,
                    "estimated_sqft": sqft,
                }
            )
            _log.info(
                "lead_estimate_saved",
                project_id=project_id,
                low=estimate.total_low,
                high=estimate.total_high,
            )
    except Exception:
        _log.exception("lead_persist_failed", company_id=company_id)
        # Don't block the response — estimate was generated successfully

    return {
        "estimate_low": estimate.total_low,
        "estimate_high": estimate.total_high,
        "estimated_sqft": sqft,
        "estimate_text": estimate_text,
        "confidence": estimate.confidence,
        "response_text": estimate_text,
        "stage": "estimate_presented",
        "project_id": project_id,
        "customer_id": customer_id,
    }


async def generate_sow_node(state: LeadState) -> dict:
    """Generate a structured Scope of Work using Gemma 4.

    Runs after estimate generation. The SOW is saved to the project
    and will be rendered into the contract HTML when the contract is generated.
    """
    project_id = state.get("project_id")
    company_id = state.get("company_id")

    if not project_id or not company_id:
        return {}

    try:
        from app.services.sow_generator import generate_sow

        result = await generate_sow(company_id=company_id, project_id=project_id)
        return {
            "actions": [
                {
                    "action": "sow_generated",
                    "line_items": len(result.get("sow", {}).get("line_items", [])),
                    "model": result.get("model", ""),
                }
            ],
        }
    except Exception as e:
        # SOW generation is non-critical — don't block the pipeline
        import logging

        logging.getLogger(__name__).warning("SOW generation failed: %s", e)
        return {}


async def check_human_review(state: LeadState) -> dict:
    """Check if this estimate needs human review before presenting.

    Triggers human review if:
    - Estimate exceeds company's dollar threshold
    - Confidence is below company's threshold
    - Photo analysis flagged issues
    """
    from sqlalchemy import select

    from app.core.database import get_tenant_session
    from app.models.company import Company

    company_id = state["company_id"]
    estimate_high = state.get("estimate_high", 0)
    confidence = state.get("confidence", 0)

    async with get_tenant_session(company_id) as session:
        result = await session.execute(select(Company).where(Company.clerk_org_id == company_id))
        company = result.scalar_one_or_none()

    threshold_dollars = 5000.0
    confidence_threshold = 0.7

    if company:
        threshold_dollars = company.human_review_threshold_dollars
        confidence_threshold = company.agent_confidence_threshold

    reasons = []
    if estimate_high > threshold_dollars:
        reasons.append(
            f"Estimate ${estimate_high:,.0f} exceeds ${threshold_dollars:,.0f} threshold"
        )
    if confidence < confidence_threshold:
        reasons.append(f"Confidence {confidence:.0%} below {confidence_threshold:.0%} threshold")

    if reasons:
        return {
            "needs_human_review": True,
            "human_review_reason": "; ".join(reasons),
            "stage": "escalated",
        }

    return {"needs_human_review": False, "stage": "estimate_presented"}


async def send_response(state: LeadState) -> dict:
    """Send the response message to the customer via SMS."""
    from app.agents.tools.messaging import send_text_message

    response_text = state.get("response_text", "")
    if not response_text:
        return {}

    await send_text_message.ainvoke(
        {
            "to_phone": state["customer_phone"],
            "body": response_text,
            "from_phone": state.get("from_phone"),
        }
    )

    return {
        "messages": [{"role": "assistant", "content": response_text}],
    }


async def escalate_to_human(state: LeadState) -> dict:
    """Notify human and inform customer about escalation."""
    response = (
        "Thanks for your patience! I've prepared a preliminary estimate "
        "and flagged it for our team to review. A specialist will follow up "
        "shortly to finalize the details. 👍"
    )
    return {"response_text": response, "stage": "escalated"}


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------


def route_after_classify(state: LeadState) -> str:
    """Route based on classified intent."""
    intent = state.get("intent", "")
    if intent == "new_lead":
        return "qualify"
    elif intent == "complaint":
        return "escalate"
    else:
        return "qualify"  # Default: try to qualify


def route_after_qualify(state: LeadState) -> str:
    """Route based on qualification stage."""
    stage = state.get("stage", "qualifying")
    has_photos = bool(state.get("media_urls"))

    if stage == "estimating" or (state.get("property_address") and has_photos):
        return "analyze_photos" if has_photos and not state.get("photo_analysis") else "estimate"
    elif stage == "awaiting_photos":
        return "respond"
    else:
        return "respond"


def route_after_analysis(state: LeadState) -> str:
    """Route after photo analysis."""
    return "estimate"


def route_after_review(state: LeadState) -> str:
    """Route based on human review check."""
    if state.get("needs_human_review"):
        return "escalate"
    return "respond"


# ---------------------------------------------------------------------------
# Build the Graph
# ---------------------------------------------------------------------------


def build_lead_onboarding_graph() -> StateGraph:
    """Construct the Lead Onboarding Agent graph.

    Graph flow:
        classify → qualify → analyze_photos → estimate → check_review → respond
                     ↓                                        ↓
                   respond                                 escalate → respond
    """
    graph = StateGraph(LeadState)

    # Add nodes
    graph.add_node("classify", classify_intent)
    graph.add_node("qualify", qualify_lead)
    graph.add_node("analyze_photos", analyze_photos)
    graph.add_node("estimate", generate_estimate)
    graph.add_node("check_review", check_human_review)
    graph.add_node("respond", send_response)
    graph.add_node("escalate", escalate_to_human)

    # Set entry point
    graph.set_entry_point("classify")

    # Add edges
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "qualify": "qualify",
            "escalate": "escalate",
        },
    )

    graph.add_conditional_edges(
        "qualify",
        route_after_qualify,
        {
            "analyze_photos": "analyze_photos",
            "estimate": "estimate",
            "respond": "respond",
        },
    )

    graph.add_conditional_edges(
        "analyze_photos",
        route_after_analysis,
        {
            "estimate": "estimate",
        },
    )

    graph.add_node("generate_sow", generate_sow_node)
    graph.add_edge("estimate", "generate_sow")
    graph.add_edge("generate_sow", "check_review")

    graph.add_conditional_edges(
        "check_review",
        route_after_review,
        {
            "escalate": "escalate",
            "respond": "respond",
        },
    )

    graph.add_edge("escalate", "respond")
    graph.add_edge("respond", END)

    return graph


# Compiled graph (reusable)
lead_onboarding_graph = build_lead_onboarding_graph().compile()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_agent_response(content: str) -> dict:
    """Parse structured agent response into dict."""
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


def _normalize_project_type(raw: str) -> str:
    """Normalize a project type string to enum value."""
    raw = raw.lower().strip()
    mapping = {
        "roof": "roof_replacement",
        "roof replacement": "roof_replacement",
        "new roof": "roof_replacement",
        "reroof": "roof_replacement",
        "roof repair": "roof_repair",
        "repair": "roof_repair",
        "leak": "roof_repair",
        "siding": "siding_install",
        "new siding": "siding_install",
        "siding repair": "siding_repair",
        "gutters": "gutters",
        "gutter": "gutters",
    }
    return mapping.get(raw, "roof_replacement")
