"""SQLAlchemy models for the Roof Automated platform."""

from app.models.base import Base
from app.models.company import Company
from app.models.user import User
from app.models.project import Project, ProjectMilestone, MilestoneTemplate
from app.models.message import Message, MessageMedia
from app.models.rate_card import (
    Material,
    LaborRate,
    PermitFee,
    WasteFactor,
    RateCardVersion,
)
from app.models.consent import SMSConsent
from app.models.audit import AuditLog

__all__ = [
    "Base",
    "Company",
    "User",
    "Project",
    "ProjectMilestone",
    "MilestoneTemplate",
    "Message",
    "MessageMedia",
    "Material",
    "LaborRate",
    "PermitFee",
    "WasteFactor",
    "RateCardVersion",
    "SMSConsent",
    "AuditLog",
]
