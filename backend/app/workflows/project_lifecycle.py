"""Project Lifecycle Workflow — the long-running Temporal orchestration.

This is the outer durable layer that wraps the entire project lifecycle:
  Contract Signed → Scheduling → Execution → QC at milestones → Payment → Closure

Each phase runs specialized LangGraph agents as Temporal Activities.
Human sign-offs are handled via Temporal Signals (pause/resume pattern).
The workflow can run for days or weeks — Temporal persists all state.

Key patterns:
  - Activities for agent execution (retryable, timeout-bounded)
  - Signals for human approvals (non-blocking wait)
  - Child workflows for complex sub-processes
  - Timers for scheduled checks (weather, payment reminders)
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class ProjectLifecycleInput:
    """Input to start a project lifecycle workflow."""

    company_id: str
    project_id: str
    customer_phone: str
    crew_lead_phone: str
    owner_phone: str
    from_phone: str
    property_zip: str
    scheduled_start: str
    contract_amount: float


@dataclass
class MilestoneSignoffRequest:
    """Data sent when human sign-off is requested."""

    milestone_id: str
    milestone_name: str
    qc_report: dict


# ---------------------------------------------------------------------------
# Activities — each wraps a LangGraph agent execution
# ---------------------------------------------------------------------------


@activity.defn
async def run_orchestrator(company_id: str, project_id: str, trigger_event: dict) -> dict:
    """Run the Orchestrator agent to decide what to do."""
    from app.agents.graphs.orchestrator import orchestrator_graph

    state = {
        "company_id": company_id,
        "project_id": project_id,
        "trigger_event": trigger_event,
        "trigger_type": trigger_event.get("event_type", ""),
        "project_status": "",
        "project_type": "",
        "milestones": [],
        "recent_events": [],
        "next_agent": "",
        "agent_input": {},
        "decision_reasoning": "",
        "confidence": 0.0,
        "actions_taken": [],
        "events_emitted": [],
        "needs_human_escalation": False,
        "escalation_reason": "",
    }

    result = await orchestrator_graph.ainvoke(state)
    return {
        "next_agent": result.get("next_agent", ""),
        "agent_input": result.get("agent_input", {}),
        "actions": result.get("actions_taken", []),
        "needs_escalation": result.get("needs_human_escalation", False),
    }


@activity.defn
async def run_execution_agent(
    company_id: str,
    project_id: str,
    property_zip: str,
    scheduled_start: str,
    customer_phone: str,
    crew_lead_phone: str,
    from_phone: str,
    trigger: dict,
) -> dict:
    """Run the Project Execution Agent."""
    from app.agents.graphs.project_execution import execution_graph

    state = {
        "company_id": company_id,
        "project_id": project_id,
        "trigger": trigger,
        "project_status": "",
        "property_zip": property_zip,
        "scheduled_start": scheduled_start,
        "crew_lead_phone": crew_lead_phone,
        "customer_phone": customer_phone,
        "from_phone": from_phone,
        "forecast": [],
        "weather_alerts": [],
        "weather_safe": True,
        "proposed_date": "",
        "reschedule_reason": "",
        "reschedule_approved": False,
        "actions": [],
        "messages_to_send": [],
        "events_to_emit": [],
    }

    result = await execution_graph.ainvoke(state)
    return {"actions": result.get("actions", []), "weather_safe": result.get("weather_safe", True)}


@activity.defn
async def run_qc_agent(
    company_id: str,
    project_id: str,
    milestone_id: str,
    photo_urls: list[str],
    customer_phone: str,
    crew_lead_phone: str,
    owner_phone: str,
    from_phone: str,
) -> dict:
    """Run the Progress & QC Agent."""
    from app.agents.graphs.progress_qc import qc_graph

    state = {
        "company_id": company_id,
        "project_id": project_id,
        "trigger": {},
        "milestone_id": milestone_id,
        "milestone_name": "",
        "milestone_requires_photo": True,
        "milestone_requires_human_signoff": False,
        "expected_work": "",
        "photo_urls": photo_urls,
        "photo_analyses": [],
        "qc_passed": False,
        "issues_found": [],
        "confidence": 0.0,
        "recommendation": "flag_for_review",
        "qc_report": {},
        "actions": [],
        "events_to_emit": [],
        "messages_to_send": [],
        "customer_phone": customer_phone,
        "crew_lead_phone": crew_lead_phone,
        "owner_phone": owner_phone,
        "from_phone": from_phone,
    }

    result = await qc_graph.ainvoke(state)
    return {
        "qc_passed": result.get("qc_passed", False),
        "recommendation": result.get("recommendation", "flag_for_review"),
        "qc_report": result.get("qc_report", {}),
        "requires_human_signoff": result.get("milestone_requires_human_signoff", False),
    }


@activity.defn
async def run_payment_agent(
    company_id: str,
    project_id: str,
    customer_phone: str,
    from_phone: str,
    trigger: dict,
) -> dict:
    """Run the Payment & Closure Agent."""
    from app.agents.graphs.payment_closure import payment_graph

    state = {
        "company_id": company_id,
        "project_id": project_id,
        "trigger": trigger,
        "project_status": "",
        "contract_amount": 0.0,
        "amount_paid": 0.0,
        "amount_due": 0.0,
        "customer_phone": customer_phone,
        "customer_email": "",
        "from_phone": from_phone,
        "property_address": "",
        "payment_schedule": [],
        "current_milestone_payment": {},
        "days_overdue": 0,
        "actions": [],
        "events_to_emit": [],
        "messages_to_send": [],
    }

    result = await payment_graph.ainvoke(state)
    return {"actions": result.get("actions", [])}


@activity.defn
async def log_lifecycle_event(company_id: str, project_id: str, action: str, data: dict) -> None:
    """Log a lifecycle event to the audit trail."""
    from app.agents.events import Event, EventType, emit_event

    await emit_event(
        company_id=company_id,
        event=Event(
            event_type=EventType.CUSTOMER_MESSAGE,  # Generic; actual type in data
            agent_name="lifecycle_workflow",
            project_id=project_id,
            data=data,
            description=action,
        ),
    )


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@workflow.defn
class ProjectLifecycleWorkflow:
    """Long-running workflow that manages a project from contract to closure.

    This workflow:
    1. Runs the execution agent (weather check + crew dispatch)
    2. Waits for milestone events (photos, completion)
    3. Runs QC on each milestone
    4. Pauses for human sign-off via signals when required
    5. Triggers payments at appropriate milestones
    6. Generates warranty on completion

    The workflow can run for weeks — Temporal persists all state.
    """

    def __init__(self):
        self._human_approvals: dict[str, bool] = {}
        self._milestone_events: list[dict] = []
        self._project_completed = False

    @workflow.signal
    async def milestone_completed(self, milestone_id: str, photo_urls: list[str]):
        """Signal: crew has completed a milestone and uploaded photos."""
        self._milestone_events.append(
            {
                "milestone_id": milestone_id,
                "photo_urls": photo_urls,
            }
        )

    @workflow.signal
    async def human_approval(self, milestone_id: str, approved: bool):
        """Signal: human has approved or rejected a milestone."""
        self._human_approvals[milestone_id] = approved

    @workflow.signal
    async def mark_completed(self):
        """Signal: project marked as complete."""
        self._project_completed = True

    @workflow.run
    async def run(self, input: ProjectLifecycleInput) -> dict:
        actions_log: list[dict] = []

        # 1. Initial weather check + crew dispatch
        exec_result = await workflow.execute_activity(
            run_execution_agent,
            args=[
                input.company_id,
                input.project_id,
                input.property_zip,
                input.scheduled_start,
                input.customer_phone,
                input.crew_lead_phone,
                input.from_phone,
                {"event_type": "job_start"},
            ],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )
        actions_log.append({"phase": "execution", "result": exec_result})

        # 2. Main milestone loop — wait for events and process
        max_iterations = 20  # Safety: prevent unbounded loops
        iteration = 0

        while not self._project_completed and iteration < max_iterations:
            iteration += 1

            # Wait for a milestone event (or timeout after 24 hours for periodic check)
            try:
                await workflow.wait_condition(
                    lambda: len(self._milestone_events) > 0 or self._project_completed,
                    timeout=timedelta(hours=24),
                )
            except TimeoutError:
                # Periodic weather re-check
                await workflow.execute_activity(
                    run_execution_agent,
                    args=[
                        input.company_id,
                        input.project_id,
                        input.property_zip,
                        input.scheduled_start,
                        input.customer_phone,
                        input.crew_lead_phone,
                        input.from_phone,
                        {"event_type": "periodic_check"},
                    ],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=2),
                )
                continue

            if self._project_completed:
                break

            # Process each pending milestone event
            while self._milestone_events:
                event = self._milestone_events.pop(0)
                milestone_id = event["milestone_id"]
                photo_urls = event["photo_urls"]

                # Run QC
                qc_result = await workflow.execute_activity(
                    run_qc_agent,
                    args=[
                        input.company_id,
                        input.project_id,
                        milestone_id,
                        photo_urls,
                        input.customer_phone,
                        input.crew_lead_phone,
                        input.owner_phone,
                        input.from_phone,
                    ],
                    start_to_close_timeout=timedelta(seconds=90),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3),
                )

                actions_log.append(
                    {
                        "phase": "qc",
                        "milestone_id": milestone_id,
                        "result": qc_result,
                    }
                )

                # If human sign-off required, wait for signal
                if (
                    qc_result.get("requires_human_signoff")
                    or qc_result.get("recommendation") == "flag_for_review"
                ):
                    try:
                        await workflow.wait_condition(
                            lambda mid=milestone_id: mid in self._human_approvals,
                            timeout=timedelta(hours=48),
                        )
                    except TimeoutError:
                        actions_log.append(
                            {
                                "phase": "human_signoff_timeout",
                                "milestone_id": milestone_id,
                            }
                        )
                        continue

                    approved = self._human_approvals.get(milestone_id, False)
                    if not approved:
                        actions_log.append(
                            {
                                "phase": "human_rejected",
                                "milestone_id": milestone_id,
                            }
                        )
                        continue

                # Milestone approved — trigger payment if applicable
                if qc_result.get("qc_passed") or self._human_approvals.get(milestone_id):
                    await workflow.execute_activity(
                        run_payment_agent,
                        args=[
                            input.company_id,
                            input.project_id,
                            input.customer_phone,
                            input.from_phone,
                            {
                                "event_type": "milestone_qc_passed",
                                "data": {"milestone": milestone_id},
                            },
                        ],
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=workflow.RetryPolicy(maximum_attempts=3),
                    )

        # 3. Project completion — final payment + warranty
        payment_result = await workflow.execute_activity(
            run_payment_agent,
            args=[
                input.company_id,
                input.project_id,
                input.customer_phone,
                input.from_phone,
                {"event_type": "job_completed"},
            ],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )
        actions_log.append({"phase": "final_payment", "result": payment_result})

        return {
            "status": "completed",
            "iterations": iteration,
            "actions": actions_log,
        }
