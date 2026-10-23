"""Risk Manager & Strategy: strategic objectives, the enterprise risk register, risk assessments and KRIs."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

KRI_FREQUENCIES = ("Monthly", "Quarterly", "Half-yearly", "Annually")


class StrategicObjective(Base):
    __tablename__ = "strategic_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    period: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class EnterpriseRisk(Base):
    __tablename__ = "enterprise_risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    consequence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("strategic_objectives.id", ondelete="SET NULL"),
                                                     nullable=True, index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                                                 index=True)
    inherent_likelihood: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    inherent_impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    residual_likelihood: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    residual_impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    target_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    appetite: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    treatment: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    treatment_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    last_assessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @property
    def inherent_score(self) -> int:
        return self.inherent_likelihood * self.inherent_impact

    @property
    def residual_score(self) -> int:
        return self.residual_likelihood * self.residual_impact


class RiskAssessment(Base):
    """One dated assessment of a risk: the history behind the current scores."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    inherent_likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    inherent_impact: Mapped[int] = mapped_column(Integer, nullable=False)
    residual_likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    residual_impact: Mapped[int] = mapped_column(Integer, nullable=False)
    control_effectiveness: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # manual (a person scored it), kri (driven by key risk indicators) or segments (roll-up of segment scores)
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    assessed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class KeyRiskIndicator(Base):
    __tablename__ = "key_risk_indicators"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # True: a higher value is worse (e.g. incidents); False: a lower value is worse (e.g. uptime %).
    higher_is_worse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    amber_at: Mapped[float] = mapped_column(Float, nullable=False)
    red_at: Mapped[float] = mapped_column(Float, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="Monthly")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Assessment driver: an Amber or Red reading raises the risk's residual likelihood or impact by these steps.
    drives: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # "" | likelihood | impact
    amber_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    red_step: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    def rag(self, value: float | None) -> str:
        if value is None:
            return "No data"
        if self.higher_is_worse:
            return "Red" if value >= self.red_at else "Amber" if value >= self.amber_at else "Green"
        return "Red" if value <= self.red_at else "Amber" if value <= self.amber_at else "Green"


class KriReading(Base):
    __tablename__ = "kri_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    kri_id: Mapped[int] = mapped_column(ForeignKey("key_risk_indicators.id", ondelete="CASCADE"), nullable=False,
                                        index=True)
    period_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RiskTreatment(Base):
    """A strategic risk's treatment: an audit objective whose work gives assurance over the risk (Strategy ›
    Treatment). Assurance on the risk is rolled up from the controls, tests and issues of the linked objectives."""

    __tablename__ = "risk_treatments"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    # Either a project objective, or a framework objective (programme + objective title): linking a framework
    # objective rolls up assurance from every project objective that came from it.
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("objectives.id", ondelete="CASCADE"), nullable=True,
                                                     index=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("audit_programs.id", ondelete="CASCADE"),
                                                   nullable=True)
    program_objective: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RiskSegmentAssessment(Base):
    """A dated assessment of one enterprise risk for one segment of the organisation (a port, division or
    department). The latest assessment per segment rolls up to the risk (worst or average, a setting)."""

    __tablename__ = "risk_segment_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
                                        index=True)
    inherent_likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    inherent_impact: Mapped[int] = mapped_column(Integer, nullable=False)
    residual_likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    residual_impact: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
