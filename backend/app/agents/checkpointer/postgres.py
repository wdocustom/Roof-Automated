"""PostgreSQL-backed checkpointer for LangGraph state persistence.

Stores agent graph state in PostgreSQL so conversations can resume
across interruptions, restarts, and long pauses (customer texts back
days later). Uses JSONB for flexible state storage.
"""

import json
import uuid
from datetime import UTC, datetime

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import async_session_factory
from app.models.base import Base


class AgentCheckpoint(Base):
    """Persisted LangGraph checkpoint."""

    __tablename__ = "agent_checkpoints"

    id = Column(String(255), primary_key=True)
    thread_id = Column(String(255), nullable=False, index=True)
    parent_id = Column(String(255), nullable=True)
    checkpoint_data = Column(JSONB, nullable=False)
    metadata_json = Column(JSONB, nullable=True)
    company_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PostgresCheckpointer(BaseCheckpointSaver):
    """LangGraph checkpointer backed by PostgreSQL.

    Enables agents to persist state between invocations. A customer
    can text back 3 days later and the agent picks up exactly where
    it left off.
    """

    def __init__(self, company_id: str):
        super().__init__()
        self.company_id = company_id

    async def aget(self, config: dict) -> Checkpoint | None:
        """Load the latest checkpoint for a thread."""
        thread_id = config.get("configurable", {}).get("thread_id", "")
        if not thread_id:
            return None

        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, checkpoint_data, metadata_json, parent_id "
                    "FROM agent_checkpoints "
                    "WHERE thread_id = :tid AND company_id = :cid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"tid": thread_id, "cid": self.company_id},
            )
            row = result.first()

            if row is None:
                return None

            return Checkpoint(
                v=1,
                id=row.id,
                ts=datetime.now(UTC).isoformat(),
                channel_values=row.checkpoint_data.get("channel_values", {}),
                channel_versions=row.checkpoint_data.get("channel_versions", {}),
                versions_seen=row.checkpoint_data.get("versions_seen", {}),
            )

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> dict:
        """Save a checkpoint for a thread."""
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_id = checkpoint.get("id", str(uuid.uuid4()))

        checkpoint_data = {
            "channel_values": checkpoint.get("channel_values", {}),
            "channel_versions": checkpoint.get("channel_versions", {}),
            "versions_seen": checkpoint.get("versions_seen", {}),
        }

        async with async_session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO agent_checkpoints "
                    "(id, thread_id, parent_id, checkpoint_data, metadata_json, company_id, created_at) "
                    "VALUES (:id, :tid, :pid, :data, :meta, :cid, :ts) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "checkpoint_data = :data, metadata_json = :meta"
                ),
                {
                    "id": checkpoint_id,
                    "tid": thread_id,
                    "pid": config.get("configurable", {}).get("parent_id"),
                    "data": json.dumps(checkpoint_data),
                    "meta": json.dumps(metadata) if metadata else None,
                    "cid": self.company_id,
                    "ts": datetime.now(UTC),
                },
            )
            await session.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
