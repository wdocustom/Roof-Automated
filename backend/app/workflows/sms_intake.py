"""SMS Intake Workflow — the core Temporal workflow for processing inbound messages.

This is the entry point for ALL inbound SMS/MMS. The Twilio webhook dispatches
here, and the workflow handles:
  1. Idempotency check (dedup by MessageSid)
  2. Consent verification (TCPA)
  3. Phone → tenant + customer lookup
  4. Message storage with media
  5. Opt-out / help handling
  6. Dispatching to the appropriate agent (Phase 2+)

Pattern: Temporal Workflow orchestrates Activities (I/O, DB calls, Twilio sends).
LangGraph agents will run inside Activities starting in Phase 2.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow

from app.core.config import settings

# ---------------------------------------------------------------------------
# Data classes for workflow input
# ---------------------------------------------------------------------------


@dataclass
class SMSIntakeInput:
    message_sid: str
    from_phone: str
    to_phone: str
    body: str
    media_urls: list[dict]  # [{"url": "...", "content_type": "..."}]
    is_opt_out: bool = False
    is_help_request: bool = False
    messaging_service_sid: str = ""


# ---------------------------------------------------------------------------
# Activities — the actual I/O operations
# ---------------------------------------------------------------------------


@activity.defn
async def store_inbound_message(input: SMSIntakeInput) -> dict:
    """Store the inbound message in the database.

    Returns dict with message_id, company_id, customer_id (if found).
    """
    # Import here to avoid Temporal sandbox issues with SQLAlchemy
    from app.services.message_service import store_message

    result = await store_message(
        message_sid=input.message_sid,
        from_phone=input.from_phone,
        to_phone=input.to_phone,
        body=input.body,
        media_urls=input.media_urls,
        messaging_service_sid=input.messaging_service_sid or None,
    )
    return result


@activity.defn
async def check_consent_status(phone: str, company_id: str) -> dict:
    """Check TCPA consent status for the phone number."""
    from app.services.consent_service import check_consent

    return await check_consent(phone=phone, company_id=company_id)


@activity.defn
async def handle_opt_out(phone: str, company_id: str) -> None:
    """Record opt-out and ensure no further messages are sent."""
    from app.services.consent_service import record_opt_out

    await record_opt_out(phone=phone, company_id=company_id)


@activity.defn
async def send_help_response(to_phone: str, from_phone: str) -> None:
    """Send TCPA-required help response."""
    from app.integrations.twilio.sms import send_sms

    await send_sms(
        to=to_phone,
        from_=from_phone,
        body=(
            "Roof Automated: For help, contact your roofing company directly. "
            "Reply STOP to opt out of messages."
        ),
    )


@activity.defn
async def send_acknowledgment(to_phone: str, from_phone: str, has_media: bool) -> None:
    """Send initial acknowledgment to the customer."""
    from app.integrations.twilio.sms import send_sms

    if has_media:
        body = "Got it — we've received your photo. We'll review it and follow up shortly."
    else:
        body = "Thanks for your message! We're on it and will follow up shortly."

    await send_sms(to=to_phone, from_=from_phone, body=body)


# ---------------------------------------------------------------------------
# Workflow — the durable orchestration
# ---------------------------------------------------------------------------


@workflow.defn
class SMSIntakeWorkflow:
    """Process an inbound SMS/MMS through the full intake pipeline."""

    @workflow.run
    async def run(self, input: SMSIntakeInput) -> dict:
        # 1. Store the message (idempotent via message_sid unique constraint)
        store_result = await workflow.execute_activity(
            store_inbound_message,
            input,
            start_to_close_timeout=timedelta(seconds=10),
        )

        company_id = store_result.get("company_id", "")

        # 1b. No company found — can't process further
        if not company_id or store_result.get("status") == "no_company_found":
            return {
                "status": "no_company_found",
                "from_phone": input.from_phone,
                "to_phone": input.to_phone,
            }

        # 2. Handle opt-out
        if input.is_opt_out and company_id:
            await workflow.execute_activity(
                handle_opt_out,
                args=[input.from_phone, company_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            return {"status": "opted_out", "message_id": store_result.get("message_id")}

        # 3. Handle help request
        if input.is_help_request:
            await workflow.execute_activity(
                send_help_response,
                args=[input.from_phone, input.to_phone],
                start_to_close_timeout=timedelta(seconds=10),
            )
            return {"status": "help_sent", "message_id": store_result.get("message_id")}

        # 4. Check consent
        if company_id:
            consent = await workflow.execute_activity(
                check_consent_status,
                args=[input.from_phone, company_id],
                start_to_close_timeout=timedelta(seconds=5),
            )

            if consent.get("status") == "opted_out":
                return {
                    "status": "blocked_no_consent",
                    "message_id": store_result.get("message_id"),
                }

        # 5. Send immediate acknowledgment so the customer knows we got it
        await workflow.execute_activity(
            send_acknowledgment,
            args=[input.from_phone, input.to_phone, len(input.media_urls) > 0],
            start_to_close_timeout=timedelta(seconds=15),
        )

        # 6. Dispatch to LangGraph agent via Agent Dispatch Workflow
        from app.workflows.agent_dispatch import AgentDispatchInput, AgentDispatchWorkflow

        agent_input = AgentDispatchInput(
            company_id=company_id,
            customer_phone=input.from_phone,
            from_phone=input.to_phone,
            message_body=input.body,
            media_urls=[m["url"] for m in input.media_urls],
            message_id=store_result.get("message_id", ""),
        )

        try:
            agent_result = await workflow.execute_child_workflow(
                AgentDispatchWorkflow.run,
                agent_input,
                id=f"agent-dispatch-{input.message_sid}",
                task_queue=settings.temporal_task_queue,
            )
        except Exception:
            # Agent dispatch failed — acknowledgment was already sent
            return {
                "status": "agent_failed",
                "message_id": store_result.get("message_id"),
                "company_id": company_id,
            }

        return {
            "status": "processed",
            "message_id": store_result.get("message_id"),
            "company_id": company_id,
            "agent_result": agent_result,
        }


# ---------------------------------------------------------------------------
# Helper to start the workflow from the webhook endpoint
# ---------------------------------------------------------------------------


async def start_sms_intake_workflow(
    message_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
    media_urls: list[dict] | None = None,
    is_opt_out: bool = False,
    is_help_request: bool = False,
    messaging_service_sid: str = "",
) -> str:
    """Start an SMS intake workflow. Returns the workflow ID."""
    from app.workflows.client import get_temporal_client

    client = await get_temporal_client()
    workflow_id = f"sms-intake-{message_sid}"

    await client.start_workflow(
        SMSIntakeWorkflow.run,
        SMSIntakeInput(
            message_sid=message_sid,
            from_phone=from_phone,
            to_phone=to_phone,
            body=body,
            media_urls=media_urls or [],
            is_opt_out=is_opt_out,
            is_help_request=is_help_request,
            messaging_service_sid=messaging_service_sid,
        ),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )

    return workflow_id
