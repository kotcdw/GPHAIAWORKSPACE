"""Shared enumerations and small SQLAlchemy model helpers.

Values are stored as VARCHAR + CHECK constraints (native_enum=False), matching
the database schema created by the Alembic migrations.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import Enum


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (MySQL friendly)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Role(str, enum.Enum):
    Admin = "Admin"
    Auditor = "Auditor"
    Auditee = "Auditee"


class AuditStatus(str, enum.Enum):
    Planned = "Planned"
    InProgress = "In Progress"
    Review = "Review"
    Closed = "Closed"


class RiskRating(str, enum.Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"


class FindingStatus(str, enum.Enum):
    Open = "Open"
    Remediating = "Remediating"
    Closed = "Closed"


class ApprovalStatus(str, enum.Enum):
    """E-signature / approval state for a record (nullable on records)."""

    OnHold = "On Hold"
    InApproval = "In Approval"
    Approved = "Approved"


class ApprovalDecision(str, enum.Enum):
    Approve = "Approve"
    Reject = "Reject"


class Severity(str, enum.Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"


class OrganizationStatus(str, enum.Enum):
    Pending = "Pending"
    Approved = "Approved"


class StakeholderStatus(str, enum.Enum):
    Active = "Active"
    Inactive = "Inactive"


class NCStatus(str, enum.Enum):
    Open = "Open"
    Remediating = "Remediating"
    Closed = "Closed"


class CapaStatus(str, enum.Enum):
    Open = "Open"
    InProgress = "In Progress"
    Review = "Review"
    Closed = "Closed"


class FeedbackStatus(str, enum.Enum):
    Open = "Open"
    InProgress = "In Progress"
    Closed = "Closed"


class TaskStatus(str, enum.Enum):
    Open = "Open"
    InProgress = "In Progress"
    Closed = "Closed"


def _enum(enum_cls: type[enum.Enum], length: int = 20) -> Enum:
    """Store Python enums as a VARCHAR column with a CHECK constraint.

    ``values_callable`` makes SQLAlchemy persist the enum *value* (e.g.
    "In Progress") rather than its name, matching the CHECK constraints in the
    database and the JSON API.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )