"""Customer review model — ratings and feedback for completed projects."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class CustomerReview(BaseModel, TenantMixin):
    """A customer's review of a completed project."""

    __tablename__ = "customer_reviews"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, unique=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Rating (1-5 stars)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    # Written review
    review_text: Mapped[str | None] = mapped_column(Text)

    # Individual scores (1-5)
    quality_rating: Mapped[int | None] = mapped_column(Integer)
    communication_rating: Mapped[int | None] = mapped_column(Integer)
    timeliness_rating: Mapped[int | None] = mapped_column(Integer)
    cleanup_rating: Mapped[int | None] = mapped_column(Integer)

    # Reviewer info
    reviewer_name: Mapped[str | None] = mapped_column(String(255))
