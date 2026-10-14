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
    # Read-only governance access (Audit Committee members, executive reviewers).
    Committee = "Committee"


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


# ---------------------------------------------------------------- planning & RCM


class PlanStatus(str, enum.Enum):
    Draft = "Draft"
    Approved = "Approved"
    Closed = "Closed"


class EngagementStatus(str, enum.Enum):
    Planned = "Planned"
    Started = "Started"
    Cancelled = "Cancelled"


class ControlType(str, enum.Enum):
    Preventive = "Preventive"
    Detective = "Detective"
    Corrective = "Corrective"


class ControlNature(str, enum.Enum):
    Manual = "Manual"
    Automated = "Automated"
    ITDependent = "IT-Dependent Manual"


class ControlFrequency(str, enum.Enum):
    Annual = "Annual"
    Quarterly = "Quarterly"
    Monthly = "Monthly"
    Weekly = "Weekly"
    Daily = "Daily"
    MultipleDaily = "Multiple Daily"
    AdHoc = "Ad Hoc"


class TestType(str, enum.Enum):
    Walkthrough = "Walkthrough"
    Design = "Design"
    OperatingEffectiveness = "Operating Effectiveness"


class TestStatus(str, enum.Enum):
    NotStarted = "Not Started"
    InProgress = "In Progress"
    Completed = "Completed"
    Reviewed = "Reviewed"


class TestConclusion(str, enum.Enum):
    NotTested = "Not Tested"
    Effective = "Effective"
    Ineffective = "Ineffective"


def risk_level(score: int) -> str:
    """Map a likelihood x impact score (1-25) onto a rating band (thresholds on the Configuration screen)."""
    try:
        from app.core.appconfig import cfg

        high, medium = int(cfg("risk_high_threshold")), int(cfg("risk_medium_threshold"))
    except Exception:  # noqa: BLE001 - configuration not reachable: standard bands
        high, medium = 15, 8
    if score >= high:
        return "High"
    if score >= medium:
        return "Medium"
    return "Low"


class ReviewLevel(str, enum.Enum):
    """Supervisory level of a staff member in the report review chain."""

    Manager = "Manager"
    CAE = "CAE"


class ReportStatus(str, enum.Enum):
    Draft = "Draft"
    ManagementReview = "Management Review"
    ManagerReview = "Manager Review"
    CAEApproval = "CAE Approval"
    Issued = "Issued"


class ReportRating(str, enum.Enum):
    Satisfactory = "Satisfactory"
    NeedsImprovement = "Needs Improvement"
    Unsatisfactory = "Unsatisfactory"


class ValidationResult(str, enum.Enum):
    Effective = "Effective"
    NotEffective = "Not Effective"


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