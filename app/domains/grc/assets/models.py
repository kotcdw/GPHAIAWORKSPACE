"""Asset Inventory: IT systems, infrastructure, data, facilities, equipment and third parties, with owners,
criticality and (for third parties) contracts and periodic due-diligence assessments."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

CRITICALITY = ("Low", "Medium", "High", "Critical")
ASSET_STATUSES = ("Planned", "Active", "Retired")
DUE_DILIGENCE = ("Not started", "In progress", "Approved", "Approved with conditions", "Rejected")
TP_RATINGS = ("Low", "Medium", "High", "Critical")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                                                 index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    location: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    classification: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    # Third parties
    vendor_contact: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    services: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contract_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    contract_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_diligence: Mapped[str] = mapped_column(String(40), nullable=False, default="Not started")
    risk_rating: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    last_assessed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @property
    def title(self) -> str:
        return self.name

    @property
    def is_third_party(self) -> bool:
        return "third party" in self.asset_type.lower()


class ThirdPartyAssessment(Base):
    __tablename__ = "third_party_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    assessed_on: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    areas: Mapped[str] = mapped_column(Text, nullable=False, default="")
    findings: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
