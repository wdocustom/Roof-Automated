"""Base model with common columns and tenant-aware mixin."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class TenantMixin:
    """Mixin that adds company_id for RLS tenant isolation.

    Every tenant-scoped table MUST include this mixin. PostgreSQL RLS policies
    filter rows where company_id = current_setting('app.current_company_id').
    """

    company_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )


class TimestampMixin:
    """Mixin for created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TimestampMixin):
    """Abstract base with UUID primary key and timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
