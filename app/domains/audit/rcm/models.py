"""Risk & control matrix (RCM) of an audit project.

Hierarchy (HighBond style): Audit (project) -> Objectives -> Risks and
Controls (many-to-many through ``risk_controls``) -> Control tests
(walkthrough, test of design, test of operating effectiveness) -> Issues
(``findings`` linked to the control/test) -> Actions (remediation).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import (
    ControlFrequency,
    ControlNature,
    ControlType,
    TestConclusion,
    TestStatus,
    TestType,
    _enum,
    risk_level,
    utcnow,
)


class Objective(Base):
    __tablename__ = "objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # The framework (Project Library programme) the objective came from, when it was imported or applied.
    source_program_id: Mapped[int | None] = mapped_column(ForeignKey("audit_programs.id", ondelete="SET NULL"),
                                                          nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    risks: Mapped[list[Risk]] = relationship(back_populates="objective", order_by="Risk.id")
    controls: Mapped[list[Control]] = relationship(back_populates="objective", order_by="Control.id")


class RiskControl(Base):
    __tablename__ = "risk_controls"

    risk_id: Mapped[int] = mapped_column(ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True)


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    likelihood: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # The enterprise risk (Risk Manager) this engagement risk tests, when it came from the entity's risks.
    enterprise_risk_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_risks.id", ondelete="SET NULL"),
                                                           nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    objective: Mapped[Objective] = relationship(back_populates="risks")
    controls: Mapped[list[Control]] = relationship(secondary="risk_controls", back_populates="risks")

    @property
    def inherent_score(self) -> int:
        return self.likelihood * self.impact

    @property
    def inherent_rating(self) -> str:
        return risk_level(self.inherent_score)


class Control(Base):
    __tablename__ = "controls"

    id: Mapped[int] = mapped_column(primary_key=True)
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    control_type: Mapped[ControlType] = mapped_column(
        _enum(ControlType), nullable=False, default=ControlType.Preventive
    )
    nature: Mapped[ControlNature] = mapped_column(_enum(ControlNature), nullable=False, default=ControlNature.Manual)
    frequency: Mapped[ControlFrequency] = mapped_column(
        _enum(ControlFrequency), nullable=False, default=ControlFrequency.Monthly
    )
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Copied from the standard controls library (Frameworks & controls), when it was.
    library_control_id: Mapped[int | None] = mapped_column(ForeignKey("library_controls.id", ondelete="SET NULL"),
                                                           nullable=True)
    # Test plan (HighBond: Testing Method, Total Sample Size, Test Steps / Attributes).
    test_method: Mapped[str | None] = mapped_column(String(60), nullable=True)
    total_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    objective: Mapped[Objective] = relationship(back_populates="controls")
    risks: Mapped[list[Risk]] = relationship(secondary="risk_controls", back_populates="controls")
    tests: Mapped[list[ControlTest]] = relationship(back_populates="control", order_by="ControlTest.id")


class ControlTest(Base):
    __tablename__ = "control_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    test_type: Mapped[TestType] = mapped_column(_enum(TestType, 30), nullable=False)
    procedure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    population_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_items: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exceptions_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[TestStatus] = mapped_column(_enum(TestStatus), nullable=False, default=TestStatus.NotStarted)
    conclusion: Mapped[TestConclusion] = mapped_column(
        _enum(TestConclusion), nullable=False, default=TestConclusion.NotTested
    )
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Testing round (operating-effectiveness tests): 1..testing_rounds of the audit; None for walkthroughs.
    round_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    control: Mapped[Control] = relationship(back_populates="tests", foreign_keys=[control_id])


class ProcedureRisk(Base):
    __tablename__ = "procedure_risks"

    procedure_id: Mapped[int] = mapped_column(ForeignKey("procedures.id", ondelete="CASCADE"), primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True)


class Procedure(Base):
    """A Workplan procedure (HighBond: Objectives -> Risks -> Procedures -> Execute Procedures)."""

    __tablename__ = "procedures"

    id: Mapped[int] = mapped_column(primary_key=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False,
                                              index=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    steps: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Not Started")
    # Execute Procedure: results and "Were issues identified?" -> "No Issues" / "Issue(s) noted".
    results: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    risks: Mapped[list[Risk]] = relationship(secondary="procedure_risks")


class Signoff(Base):
    """One sign-off on a fieldwork page (level 1 = Preparer, then up to four reviewer levels)."""

    __tablename__ = "signoffs"
    __table_args__ = (UniqueConstraint("target_type", "target_id", "level", name="uq_signoffs_target_level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SignoffReviewer(Base):
    """The "Next Reviewer" set on a page, and the level they are asked to sign."""

    __tablename__ = "signoff_reviewers"

    target_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    target_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    set_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class NarrativeControl(Base):
    __tablename__ = "narrative_controls"

    narrative_id: Mapped[int] = mapped_column(ForeignKey("narratives.id", ondelete="CASCADE"), primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True)


class Narrative(Base):
    """A process narrative under an objective (Internal Control workflow), linked to up to 100 controls."""

    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(primary_key=True)
    objective_id: Mapped[int] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False,
                                              index=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    controls: Mapped[list[Control]] = relationship(secondary="narrative_controls")


class AuditFavorite(Base):
    __tablename__ = "audit_favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AuditTypeTerm(Base):
    """A renamed term for one audit type (Terms settings), e.g. Objective -> Section."""

    __tablename__ = "audit_type_terms"

    audit_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    term_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
