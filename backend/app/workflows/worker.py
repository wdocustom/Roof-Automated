"""Temporal worker — runs as a separate process alongside FastAPI.

Registers all workflows and activities, then polls the task queue.
Start with: python -m app.workflows.worker
"""

import asyncio

from temporalio.worker import Worker

from app.core.config import settings
from app.workflows.client import get_temporal_client
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

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SMSIntakeWorkflow],
        activities=[
            store_inbound_message,
            check_consent_status,
            handle_opt_out,
            send_help_response,
            send_acknowledgment,
        ],
    )

    print(f"Temporal worker started on queue: {settings.temporal_task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
