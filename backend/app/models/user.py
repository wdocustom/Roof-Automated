"""User model with role-based access."""

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class UserRole(enum.StrEnum):
    OWNER = "owner"
    SALES_MANAGER = "sales_manager"
    CREW_LEAD = "crew_lead"
    CREW_MEMBER = "crew_member"
    CUSTOMER = "customer"


class User(BaseModel, TenantMixin):
    """Platform user. Synced from Clerk; role determines access."""

    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True)
