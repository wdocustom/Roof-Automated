"""Temporal worker — runs as a separate process alongside FastAPI.

Registers all workflows and activities, then polls the task queue.
Start with: python -m app.workflows.worker
"""

import asyncio

from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from app.core.config import settings

# Phase 2: Agent dispatch
from app.workflows.agent_dispatch import (
    AgentDispatchWorkflow,
    determine_agent,
    log_agent_action,
    run_customer_engagement_agent,
    run_lead_onboarding_agent,
)
from app.workflows.client import get_temporal_client

# Phase 3: Project lifecycle + swarm agents
from app.workflows.project_lifecycle import (
    ProjectLifecycleWorkflow,
    log_lifecycle_event,
    run_execution_agent,
    run_orchestrator,
    run_payment_agent,
    run_qc_agent,
)

# Phase 1: SMS intake
from app.workflows.sms_intake import (
    SMSIntakeWorkflow,
    check_consent_status,
    handle_opt_out,
    send_acknowledgment,
    send_help_response,
    store_inbound_message,
)


async def run_worker() -> None:
    """Connect to Temporal and start processing workflows."""
    client = await get_temporal_client()

    # Allow pydantic-settings and app.core.config through the Temporal
    # workflow sandbox.  pydantic-settings calls Path.expanduser() to
    # locate .env files, which is forbidden inside the default sandbox.
    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            "pydantic",
            "pydantic_settings",
            "app",
        )
    )

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            # Phase 1
            SMSIntakeWorkflow,
            # Phase 2
            AgentDispatchWorkflow,
            # Phase 3
            ProjectLifecycleWorkflow,
        ],
        activities=[
            # Phase 1: SMS intake
            store_inbound_message,
            check_consent_status,
            handle_opt_out,
            send_help_response,
            send_acknowledgment,
            # Phase 2: Agent dispatch
            determine_agent,
            run_lead_onboarding_agent,
            run_customer_engagement_agent,
            log_agent_action,
            # Phase 3: Swarm agents
            run_orchestrator,
            run_execution_agent,
            run_qc_agent,
            run_payment_agent,
            log_lifecycle_event,
        ],
        workflow_runner=sandbox_runner,
    )

    print(f"Temporal worker started on queue: {settings.temporal_task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
