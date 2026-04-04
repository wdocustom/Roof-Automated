"""Progress & QC Agent — monitors job progress and quality via photo analysis.

This agent:
  1. Ingests crew-uploaded photos and maps them to milestones
  2. Runs LLM vision analysis to verify work quality
  3. Compares progress against contract specs
  4. Prepares QC reports for milestone sign-off
  5. Flags issues with evidence early (before they become costly)
  6. Requests human sign-off only at configured milestones

The QC Agent is conservative by design — it flags for review rather
than auto-approving when uncertain. This protects against liability.
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.events import Event, EventType, emit_event
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class QCState(TypedDict):
    """State for the Progress & QC Agent."""

    company_id: str
    project_id: str
    trigger: dict

    # Milestone context
    milestone_id: str
    milestone_name: str
    milestone_requires_photo: bool
    milestone_requires_human_signoff: bool
    expected_work: str

    # Photo analysis
    photo_urls: list[str]
    photo_analyses: list[dict]

    # QC assessment
    qc_passed: bool
    issues_found: list[str]
    confidence: float
    recommendation: str  # "approve", "flag_for_review", "reject"

    # Report
    qc_report: dict

    # Outputs
    actions: Annotated[list[dict], operator.add]
    events_to_emit: Annotated[list[dict], operator.add]
    messages_to_send: Annotated[list[dict], operator.add]

    # Customer/crew context
    customer_phone: str
    crew_lead_phone: str
    owner_phone: str
    from_phone: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_milestone_context(state: QCState) -> dict:
    """Load the milestone details and contract specs."""
    from sqlalchemy import select

    from app.core.database import get_tenant_session
    from app.models.project import Project, ProjectMilestone

    milestone_id = state.get("milestone_id", "")
    if not milestone_id:
        return {}

    async with get_tenant_session(state["company_id"]) as session:
        result = await session.execute(
            select(ProjectMilestone).where(ProjectMilestone.id == uuid.UUID(milestone_id))
        )
        milestone = result.scalar_one_or_none()

        if not milestone:
            return {"milestone_name": "Unknown", "expected_work": ""}

        # Load project for contract specs
        result = await session.execute(select(Project).where(Project.id == milestone.project_id))
        project = result.scalar_one_or_none()

        expected = _get_expected_work(milestone.name, project)

        return {
            "milestone_name": milestone.name,
            "milestone_requires_photo": milestone.requires_photo,
            "milestone_requires_human_signoff": milestone.requires_human_signoff,
            "expected_work": expected,
        }


async def analyze_photos(state: QCState) -> dict:
    """Run LLM vision analysis on each uploaded photo."""
    from app.agents.tools.vision import analyze_progress_photo

    photos = state.get("photo_urls", [])
    if not photos:
        return {
            "photo_analyses": [],
            "issues_found": ["No photos uploaded for this milestone"],
            "confidence": 0.0,
        }

    analyses = []
    for url in photos[:5]:  # Cap at 5 photos per milestone
        analysis = await analyze_progress_photo.ainvoke(
            {
                "image_url": url,
                "milestone_name": state.get("milestone_name", ""),
                "expected_work": state.get("expected_work", ""),
                "tenant_id": state.get("company_id"),
            }
        )
        analyses.append(analysis)

    return {"photo_analyses": analyses}


async def assess_quality(state: QCState) -> dict:
    """Aggregate photo analyses into an overall QC assessment.

    Uses LLM to synthesize findings and determine pass/fail/review.
    """
    analyses = state.get("photo_analyses", [])
    milestone = state.get("milestone_name", "")
    expected = state.get("expected_work", "")

    if not analyses:
        return {
            "qc_passed": False,
            "recommendation": "flag_for_review",
            "issues_found": ["No photo evidence available"],
            "confidence": 0.0,
        }

    # Synthesize analyses
    analysis_summary = "\n".join(
        f"Photo {i + 1}: {a.get('recommendation', 'unknown')} "
        f"(confidence: {a.get('confidence', 0)}) - "
        f"Issues: {a.get('issues_found', 'none')}"
        for i, a in enumerate(analyses)
    )

    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a roofing/siding QC inspector reviewing multiple progress photos "
                        "for a construction milestone.\n\n"
                        f"Milestone: {milestone}\n"
                        f"Expected Work: {expected}\n\n"
                        f"Individual Photo Analyses:\n{analysis_summary}\n\n"
                        "Synthesize the analyses and provide an overall assessment:\n"
                        "QC_PASSED: yes|no\n"
                        "RECOMMENDATION: approve|flag_for_review|reject\n"
                        "ISSUES: <comma-separated list of issues, or 'none'>\n"
                        "CONFIDENCE: <0.0 to 1.0>\n"
                        "SUMMARY: <1-2 sentence summary for the QC report>\n\n"
                        "Be conservative: flag_for_review if any doubt. Reject only for "
                        "clear quality issues visible in photos."
                    ),
                },
                {"role": "user", "content": "Please provide the overall QC assessment."},
            ],
            tier=ModelTier.STANDARD,
            temperature=0.1,
            max_tokens=300,
            tenant_id=state.get("company_id"),
        )
    )

    parsed = _parse_response(response.content)
    issues = [
        i.strip()
        for i in parsed.get("issues", "none").split(",")
        if i.strip() and i.strip().lower() != "none"
    ]

    return {
        "qc_passed": parsed.get("qc_passed", "no").lower() == "yes",
        "recommendation": parsed.get("recommendation", "flag_for_review"),
        "issues_found": issues,
        "confidence": float(parsed.get("confidence", "0.5")),
        "qc_report": {
            "milestone": milestone,
            "photo_count": len(analyses),
            "qc_passed": parsed.get("qc_passed", "no").lower() == "yes",
            "recommendation": parsed.get("recommendation", "flag_for_review"),
            "issues": issues,
            "confidence": float(parsed.get("confidence", "0.5")),
            "summary": parsed.get("summary", ""),
            "analyses": analyses,
        },
    }


async def handle_qc_result(state: QCState) -> dict:
    """Process the QC result — approve, request human review, or flag issues.

    When auto-approving, also marks the milestone as APPROVED in the DB
    and checks if ALL milestones are now done (triggers project completion).
    """
    recommendation = state.get("recommendation", "flag_for_review")
    requires_human = state.get("milestone_requires_human_signoff", False)
    events: list[dict] = []
    messages: list[dict] = []

    if recommendation == "approve" and not requires_human:
        # Auto-approve — update milestone status in DB
        await _approve_milestone(state["company_id"], state.get("milestone_id", ""))

        events.append(
            {
                "type": EventType.MILESTONE_QC_PASSED.value,
                "data": state.get("qc_report", {}),
                "description": f"Milestone '{state.get('milestone_name', '')}' QC passed (auto-approved)",
            }
        )

        # Check if ALL milestones are now approved → auto-complete project
        from app.services.completion_service import check_project_completion

        completion = await check_project_completion(
            project_id=state["project_id"],
            company_id=state["company_id"],
        )
        if completion.get("completed") and completion.get("customer_token"):
            events.append(
                {
                    "type": EventType.JOB_COMPLETED.value,
                    "data": {
                        "customer_token": completion["customer_token"],
                        "final_amount": completion.get("final_amount", 0),
                    },
                    "description": "All milestones approved — project completed, final invoice sent",
                }
            )

        # Notify customer
        if state.get("customer_phone"):
            messages.append(
                {
                    "to": state["customer_phone"],
                    "body": f"Great news! The {state.get('milestone_name', 'current milestone')} has passed quality inspection. Work is progressing well!",
                }
            )

    elif recommendation == "reject":
        # QC failed — notify crew and flag
        events.append(
            {
                "type": EventType.MILESTONE_QC_FAILED.value,
                "data": {**state.get("qc_report", {}), "issues": state.get("issues_found", [])},
                "description": f"Milestone '{state.get('milestone_name', '')}' QC FAILED: {', '.join(state.get('issues_found', []))}",
            }
        )

        if state.get("crew_lead_phone"):
            issues_text = "\n".join(f"- {i}" for i in state.get("issues_found", []))
            messages.append(
                {
                    "to": state["crew_lead_phone"],
                    "body": f"QC Review — issues found on {state.get('milestone_name', '')}:\n{issues_text}\nPlease address and upload new photos.",
                }
            )

    else:
        # Flag for human review (default conservative path)
        events.append(
            {
                "type": EventType.MILESTONE_HUMAN_APPROVAL_REQUESTED.value,
                "data": state.get("qc_report", {}),
                "description": f"Milestone '{state.get('milestone_name', '')}' ready for human review",
            }
        )

        if state.get("owner_phone"):
            messages.append(
                {
                    "to": state["owner_phone"],
                    "body": (
                        f"QC Review Needed: {state.get('milestone_name', '')}\n"
                        f"Confidence: {state.get('confidence', 0):.0%}\n"
                        f"Reply APPROVE or REJECT"
                    ),
                }
            )

    return {
        "events_to_emit": events,
        "messages_to_send": messages,
        "actions": [
            {"action": f"qc_{recommendation}", "milestone": state.get("milestone_name", "")}
        ],
    }


async def send_notifications(state: QCState) -> dict:
    """Send all queued messages and emit events."""
    from app.agents.tools.messaging import send_text_message

    from_phone = state.get("from_phone", "")

    for msg in state.get("messages_to_send", []):
        await send_text_message.ainvoke(
            {
                "to_phone": msg["to"],
                "body": msg["body"],
                "from_phone": from_phone,
            }
        )

    for event_data in state.get("events_to_emit", []):
        await emit_event(
            company_id=state["company_id"],
            event=Event(
                event_type=EventType(event_data["type"]),
                agent_name="qc",
                project_id=state["project_id"],
                data=event_data.get("data", {}),
                description=event_data.get("description", ""),
            ),
        )

    return {}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_qc_graph() -> StateGraph:
    """Build the Progress & QC Agent graph.

    Flow:
        load_milestone → analyze_photos → assess_quality → handle_result → notify
    """
    graph = StateGraph(QCState)

    graph.add_node("load_milestone", load_milestone_context)
    graph.add_node("analyze_photos", analyze_photos)
    graph.add_node("assess_quality", assess_quality)
    graph.add_node("handle_result", handle_qc_result)
    graph.add_node("notify", send_notifications)

    graph.set_entry_point("load_milestone")
    graph.add_edge("load_milestone", "analyze_photos")
    graph.add_edge("analyze_photos", "assess_quality")
    graph.add_edge("assess_quality", "handle_result")
    graph.add_edge("handle_result", "notify")
    graph.add_edge("notify", END)

    return graph


qc_graph = build_qc_graph().compile()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_expected_work(milestone_name: str, project) -> str:
    """Map milestone name to expected work description for QC comparison."""
    expectations = {
        "tear-off complete": "Old roofing materials fully removed. Deck visible, clean of debris and nails. No damage to deck boards.",
        "underlayment installed": "Synthetic underlayment fully covering deck. Overlaps correct (min 4 inches). Ice/water shield at eaves and valleys.",
        "shingles installed": "Shingles properly installed with correct exposure. Straight lines, proper nailing pattern. Flashing around all penetrations.",
        "mid-install": "Work in progress. Partial installation visible. Materials staged safely.",
        "final walkthrough": "All work complete. Clean site. Correct materials match contract. No visible defects.",
        "siding installed": "Siding panels properly aligned. Correct overlap and nailing. Trim and corners finished.",
        "gutters installed": "Gutters properly pitched. Secure mounting. Downspouts positioned correctly.",
    }

    name_lower = milestone_name.lower()
    for key, desc in expectations.items():
        if key in name_lower:
            return desc

    return f"Complete: {milestone_name}. Work should match contract specifications."


async def _approve_milestone(company_id: str, milestone_id: str) -> None:
    """Mark a milestone as APPROVED in the database."""
    if not milestone_id:
        return

    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.database import get_system_session
    from app.models.project import MilestoneStatus, ProjectMilestone

    async with get_system_session() as session:
        result = await session.execute(
            select(ProjectMilestone).where(ProjectMilestone.id == uuid.UUID(milestone_id))
        )
        milestone = result.scalar_one_or_none()
        if milestone:
            milestone.status = MilestoneStatus.APPROVED
            milestone.approved_at = datetime.now(UTC).isoformat()
            await session.flush()


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
