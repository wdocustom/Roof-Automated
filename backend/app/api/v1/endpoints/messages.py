"""Message thread endpoints — list conversations and view threads."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.database import get_tenant_session
from app.middleware.tenant import get_company_id
from app.models.message import Message
from app.schemas.message import ConversationThread, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


class ConversationSummary(BaseModel):
    phone_number: str
    message_count: int
    last_message: str | None
    last_message_at: str | None


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    company_id: str = Depends(get_company_id),
):
    """List conversation summaries grouped by phone number."""
    try:
        async with get_tenant_session(company_id) as session:
            subq = (
                select(
                    Message.from_phone.label("phone_number"),
                    func.count(Message.id).label("msg_count"),
                    func.max(Message.created_at).label("latest"),
                )
                .group_by(Message.from_phone)
                .subquery()
            )

            result = await session.execute(
                select(
                    subq.c.phone_number,
                    subq.c.msg_count,
                    subq.c.latest,
                ).order_by(subq.c.latest.desc())
            )
            rows = result.all()

            summaries: list[ConversationSummary] = []
            for phone, count, latest in rows:
                # Get last message body
                last_msg_result = await session.execute(
                    select(Message.body)
                    .where(
                        (Message.from_phone == phone) | (Message.to_phone == phone)
                    )
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                last_body = last_msg_result.scalar_one_or_none()

                summaries.append(
                    ConversationSummary(
                        phone_number=phone,
                        message_count=count,
                        last_message=last_body,
                        last_message_at=latest.isoformat() if latest else None,
                    )
                )

        return summaries
    except (ProgrammingError, DBAPIError):
        logger.warning("list_conversations: tables not yet created — returning empty list")
        return []


@router.get("/{phone_number}", response_model=ConversationThread)
async def get_conversation_thread(
    phone_number: str,
    company_id: str = Depends(get_company_id),
):
    """Get the conversation thread for a specific phone number."""
    try:
        async with get_tenant_session(company_id) as session:
            result = await session.execute(
                select(Message)
                .where(
                    (Message.from_phone == phone_number)
                    | (Message.to_phone == phone_number)
                )
                .order_by(Message.created_at.asc())
            )
            messages = result.scalars().all()

        project_id = next((m.project_id for m in messages if m.project_id), None)

        return ConversationThread(
            project_id=project_id,
            phone_number=phone_number,
            messages=[MessageResponse.model_validate(m) for m in messages],
            total=len(messages),
        )
    except (ProgrammingError, DBAPIError):
        logger.warning("get_conversation_thread: tables not yet created — returning empty thread")
        return ConversationThread(
            project_id=None,
            phone_number=phone_number,
            messages=[],
            total=0,
        )
