"""Payment & Closure Agent — invoicing, payment tracking, warranty generation.

This agent handles the financial lifecycle of a project:
  1. Generate invoices at milestone completion
  2. Send payment links via SMS (Stripe embedded)
  3. Track payment status and send reminders
  4. Handle payment failures / overdue accounts
  5. Generate warranty documents on project completion
  6. Schedule post-job follow-up reminders

All financial operations are logged in the audit trail for liability protection.
"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.events import Event, EventType, emit_event
from app.integrations.llm.router import LLMRequest, ModelTier, llm_router


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class PaymentState(TypedDict):
    """State for the Payment & Closure Agent."""

    company_id: str
    project_id: str
    trigger: dict

    # Project context
    project_status: str
    contract_amount: float
    amount_paid: float
    amount_due: float
    customer_phone: str
    customer_email: str
    from_phone: str
    property_address: str

    # Payment context
    payment_schedule: list[dict]  # [{milestone, amount, status}]
    current_milestone_payment: dict
    days_overdue: int

    # Outputs
    actions: Annotated[list[dict], operator.add]
    events_to_emit: Annotated[list[dict], operator.add]
    messages_to_send: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def load_payment_context(state: PaymentState) -> dict:
    """Load project financial state."""
    from app.agents.tools.project_tools import get_project_details

    project = await get_project_details.ainvoke({
        "company_id": state["company_id"],
        "project_id": state["project_id"],
    })

    contract_amount = project.get("contract_amount", 0) or 0
    # Placeholder: in production, query actual payments from Stripe
    amount_paid = 0.0

    return {
        "project_status": project.get("status", "unknown"),
        "contract_amount": contract_amount,
        "amount_paid": amount_paid,
        "amount_due": contract_amount - amount_paid,
        "property_address": project.get("property_address", ""),
    }


async def determine_payment_action(state: PaymentState) -> dict:
    """Decide what payment action to take based on trigger and context."""
    trigger = state.get("trigger", {})
    trigger_type = trigger.get("event_type", "")
    amount_due = state.get("amount_due", 0)

    if trigger_type == EventType.MILESTONE_QC_PASSED.value or trigger_type == EventType.MILESTONE_HUMAN_APPROVED.value:
        return {"current_milestone_payment": {
            "type": "milestone_invoice",
            "amount": amount_due,  # Simplified: full amount at completion
            "description": f"Milestone payment: {trigger.get('data', {}).get('milestone', 'Progress')}",
        }}

    elif trigger_type == EventType.JOB_COMPLETED.value:
        return {"current_milestone_payment": {
            "type": "final_invoice",
            "amount": amount_due,
            "description": "Final payment for project completion",
        }}

    elif trigger_type == EventType.PAYMENT_OVERDUE.value:
        return {"current_milestone_payment": {
            "type": "reminder",
            "amount": amount_due,
            "description": "Payment reminder",
        }}

    return {"current_milestone_payment": {"type": "none"}}


async def send_invoice(state: PaymentState) -> dict:
    """Generate and send an invoice/payment link via SMS."""
    payment = state.get("current_milestone_payment", {})
    if payment.get("type") == "none" or payment.get("amount", 0) <= 0:
        return {}

    amount = payment["amount"]
    description = payment["description"]
    customer_phone = state.get("customer_phone", "")

    if not customer_phone:
        return {"actions": [{"action": "invoice_skipped", "reason": "no customer phone"}]}

    from app.integrations.stripe.payments import create_payment_link

    payment_url = await create_payment_link(
        amount_cents=int(amount * 100),
        description=description,
        metadata={
            "project_id": state["project_id"],
            "company_id": state["company_id"],
        },
    )

    messages = [{
        "to": customer_phone,
        "body": (
            f"Invoice: ${amount:,.2f}\n"
            f"{description}\n"
            f"Property: {state.get('property_address', 'N/A')}\n\n"
            f"Pay securely: {payment_url}\n\n"
            f"Thank you for your business! Reply HELP for questions."
        ),
    }]

    events = [{
        "type": EventType.INVOICE_SENT.value,
        "data": {
            "amount": amount,
            "payment_url": payment_url,
            "description": description,
        },
        "description": f"Invoice sent: ${amount:,.2f} — {description}",
    }]

    return {
        "messages_to_send": messages,
        "events_to_emit": events,
        "actions": [{"action": "invoice_sent", "amount": amount}],
    }


async def send_reminder(state: PaymentState) -> dict:
    """Send payment reminder for overdue invoices."""
    amount_due = state.get("amount_due", 0)
    days_overdue = state.get("days_overdue", 0)
    customer_phone = state.get("customer_phone", "")

    if not customer_phone or amount_due <= 0:
        return {}

    # Escalate tone based on days overdue
    if days_overdue <= 3:
        tone = "friendly"
        body = (
            f"Friendly reminder: You have an outstanding balance of ${amount_due:,.2f}. "
            f"Please let us know if you have any questions!"
        )
    elif days_overdue <= 7:
        tone = "firm"
        body = (
            f"Payment reminder: ${amount_due:,.2f} is now {days_overdue} days past due. "
            f"Please process payment at your earliest convenience."
        )
    else:
        tone = "urgent"
        body = (
            f"Urgent: Your payment of ${amount_due:,.2f} is {days_overdue} days overdue. "
            f"Please contact us immediately to arrange payment and avoid further action."
        )

    events = [{
        "type": EventType.PAYMENT_REMINDER_SENT.value,
        "data": {"amount_due": amount_due, "days_overdue": days_overdue, "tone": tone},
        "description": f"Payment reminder ({tone}): ${amount_due:,.2f}, {days_overdue} days overdue",
    }]

    return {
        "messages_to_send": [{"to": customer_phone, "body": body}],
        "events_to_emit": events,
        "actions": [{"action": f"reminder_sent_{tone}"}],
    }


async def generate_warranty(state: PaymentState) -> dict:
    """Generate warranty document on project completion + full payment."""
    if state.get("amount_due", 0) > 0:
        return {"actions": [{"action": "warranty_deferred", "reason": "balance remaining"}]}

    # Generate warranty text using LLM
    response = await llm_router.complete(
        LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a professional roofing/siding warranty document summary. "
                        "Include: workmanship warranty (typically 5 years), manufacturer material "
                        "warranty reference, what's covered, what's excluded, and how to file a claim.\n\n"
                        "Keep it concise (suitable for SMS follow-up + PDF generation).\n"
                        f"Property: {state.get('property_address', 'N/A')}\n"
                        f"Project Type: {state.get('project_status', 'N/A')}\n"
                        f"Contract Amount: ${state.get('contract_amount', 0):,.2f}"
                    ),
                },
                {"role": "user", "content": "Generate the warranty summary."},
            ],
            tier=ModelTier.STANDARD,
            temperature=0.2,
            max_tokens=500,
            tenant_id=state.get("company_id"),
        )
    )

    warranty_text = response.content

    events = [{
        "type": EventType.WARRANTY_GENERATED.value,
        "data": {
            "warranty_text": warranty_text,
            "property": state.get("property_address", ""),
        },
        "description": "Warranty document generated",
    }]

    messages = []
    if state.get("customer_phone"):
        messages.append({
            "to": state["customer_phone"],
            "body": (
                f"Your project is complete and paid in full! 🎉\n\n"
                f"Your warranty details have been saved. We'll check in at "
                f"6 and 12 months to ensure everything is holding up.\n\n"
                f"Thank you for choosing us!"
            ),
        })

    return {
        "events_to_emit": events,
        "messages_to_send": messages,
        "actions": [{"action": "warranty_generated"}],
    }


async def send_notifications(state: PaymentState) -> dict:
    """Send all queued messages and emit events."""
    from app.agents.tools.messaging import send_text_message

    from_phone = state.get("from_phone", "")

    for msg in state.get("messages_to_send", []):
        await send_text_message.ainvoke({
            "to_phone": msg["to"],
            "body": msg["body"],
            "from_phone": from_phone,
        })

    for event_data in state.get("events_to_emit", []):
        await emit_event(
            company_id=state["company_id"],
            event=Event(
                event_type=EventType(event_data["type"]),
                agent_name="payment",
                project_id=state["project_id"],
                data=event_data.get("data", {}),
                description=event_data.get("description", ""),
            ),
        )

    return {}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_determine(state: PaymentState) -> str:
    payment = state.get("current_milestone_payment", {})
    ptype = payment.get("type", "none")

    if ptype == "reminder":
        return "reminder"
    elif ptype in ("milestone_invoice", "final_invoice"):
        return "invoice"
    elif ptype == "none" and state.get("amount_due", 0) <= 0:
        return "warranty"
    return "notify"  # Nothing to do


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def build_payment_graph() -> StateGraph:
    """Build the Payment & Closure Agent graph.

    Flow:
        load_context → determine_action → invoice → notify
                                        → reminder → notify
                                        → warranty → notify
    """
    graph = StateGraph(PaymentState)

    graph.add_node("load_context", load_payment_context)
    graph.add_node("determine", determine_payment_action)
    graph.add_node("invoice", send_invoice)
    graph.add_node("reminder", send_reminder)
    graph.add_node("warranty", generate_warranty)
    graph.add_node("notify", send_notifications)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "determine")

    graph.add_conditional_edges("determine", route_after_determine, {
        "invoice": "invoice",
        "reminder": "reminder",
        "warranty": "warranty",
        "notify": "notify",
    })

    graph.add_edge("invoice", "notify")
    graph.add_edge("reminder", "notify")
    graph.add_edge("warranty", "notify")
    graph.add_edge("notify", END)

    return graph


payment_graph = build_payment_graph().compile()
