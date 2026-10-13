from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.enums import (
    AuditStatus,
    CapaStatus,
    FeedbackStatus,
    FindingStatus,
    NCStatus,
    OrganizationStatus,
    RiskRating,
    Role,
    Severity,
    StakeholderStatus,
    TaskStatus,
    utcnow,
)
from app.core.security import hash_password
from app.modules.audits.models import Audit, Finding, WorkingPaper
from app.modules.capa.models import Capa as CAPA
from app.modules.nonconformances.models import Nonconformance
from app.modules.organizations.models import Organization
from app.modules.service_feedback.models import ServiceFeedback
from app.modules.stakeholders.models import Stakeholder
from app.modules.tasks.models import Task
from app.modules.users.models import User


def _user(db, username: str, role: Role, active: bool = True) -> User:
    u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if u:
        return u
    u = User(
        username=username,
        password_hash=hash_password("DemoPass!123"),
        email=f"{username}@demo.local",
        full_name=username.replace(".", " ").title(),
        role=role,
        is_active=active,
    )
    db.add(u)
    db.flush()
    return u


def run() -> None:
    db = SessionLocal()
    try:
        admin = _user(db, "demo.admin", Role.Admin)
        auditor = _user(db, "demo.auditor", Role.Auditor)
        auditee = _user(db, "demo.auditee", Role.Auditee)

        org = db.execute(select(Organization)).scalar_one_or_none()
        if not org:
            org = Organization(
                org_ref="ORG-0001",
                name="Port Operations Ltd",
                category="Port Authority",
                contact_name="John Mensah",
                contact_email="j.mensah@poltdemo.local",
                contact_phone="+233 20 123 4567",
                status=OrganizationStatus.APPROVED,
                approved_by=admin.id,
                approved_at=utcnow() - timedelta(days=10),
            )
            db.add(org)

        sh = db.execute(select(Stakeholder)).scalar_one_or_none()
        if not sh:
            sh = Stakeholder(
                sh_ref="SH-0001",
                name="Shipping Line Co.",
                stakeholder_type="Shipping",
                contact_name="Ama Boateng",
                contact_email="a.boateng@slcdemo.local",
                status=StakeholderStatus.ACTIVE,
            )
            db.add(sh)

        audit = db.execute(select(Audit)).scalar_one_or_none()
        if not audit:
            audit = Audit(
                title="ISPS/Port Security Audit",
                description="Annual compliance audit against ISPS Code requirements",
                scope="Terminal operations, access control, security procedures",
                status=AuditStatus.IN_PROGRESS,
                approval_status=None,
                organization_id=org.id,
                creator_id=auditor.id,
            )
            db.add(audit)
            db.flush()

        if not db.execute(select(Finding).where(Finding.audit_id == audit.id)).first():
            db.add_all(
                [
                    Finding(
                        audit_id=audit.id,
                        title="Access control log review gaps",
                        description="Physical access logs not reviewed daily as per procedure",
                        risk_rating=RiskRating.MEDIUM,
                        status=FindingStatus.REMEDIATING,
                        assigned_owner_email=auditee.email,
                    ),
                    Finding(
                        audit_id=audit.id,
                        title="Perimeter lighting coverage",
                        description="Minor blind spots observed during night inspection",
                        risk_rating=RiskRating.LOW,
                        status=FindingStatus.OPEN,
                        assigned_owner_email=auditee.email,
                    ),
                ]
            )

        if not db.execute(select(WorkingPaper).where(WorkingPaper.audit_id == audit.id)).first():
            db.add(
                WorkingPaper(
                    audit_id=audit.id,
                    title="Site inspection checklist",
                    version_number=1,
                    file_path="demo/site-inspection-checklist-v1.pdf",
                    original_filename="site-inspection-checklist.pdf",
                    uploaded_by=auditor.id,
                )
            )

        nc = db.execute(select(Nonconformance)).scalar_one_or_none()
        if not nc:
            nc = Nonconformance(
                nc_ref="NC-0001",
                title="Unauthorized access attempt follow-up",
                description="Unreported access event not logged in incident register",
                severity=Severity.MEDIUM,
                disposition="Requires immediate corrective action",
                status=NCStatus.REMEDIATING,
                owner_email=auditee.email,
                audit_id=audit.id,
            )
            db.add(nc)
            db.flush()

        capa = db.execute(select(CAPA)).scalar_one_or_none()
        if not capa:
            capa = CAPA(
                capa_ref="CAPA-0001",
                title="Strengthen access control monitoring",
                description="Implement daily log review and escalation process",
                root_cause="Lack of clear ownership for daily log review",
                corrective_action="Assign daily log review responsibility and checklist",
                preventive_action="Add automated reminder and weekly verification",
                effectiveness_check="Verify 30-day compliance trend",
                severity=Severity.MEDIUM,
                status=CapaStatus.IN_PROGRESS,
                owner_email=auditee.email,
                due_date=utcnow() + timedelta(days=14),
                linked_nc_id=nc.id,
            )
            db.add(capa)
            nc.linked_capa_id = capa.id

        sf = db.execute(select(ServiceFeedback)).scalar_one_or_none()
        if not sf:
            sf = ServiceFeedback(
                sf_ref="SF-0001",
                subject="Vessel clearance turnaround time",
                description="Feedback regarding improved clearance processing time",
                source="Stakeholder feedback",
                status=FeedbackStatus.IN_PROGRESS,
                owner_email=auditee.email,
            )
            db.add(sf)

        if not db.execute(select(Task).where(Task.source_type == "audit", Task.source_id == audit.id)).first():
            db.add_all(
                [
                    Task(
                        title="Review audit findings with auditee",
                        description="Schedule closing meeting to discuss findings and timelines",
                        assignee_id=auditee.id,
                        assignor_id=auditor.id,
                        status=TaskStatus.OPEN,
                        due_date=utcnow() + timedelta(days=7),
                        source_type="audit",
                        source_id=audit.id,
                        system_generated=False,
                    ),
                    Task(
                        title="Verify CAPA implementation progress",
                        description="Check status of corrective actions",
                        assignee_id=auditee.id,
                        assignor_id=auditor.id,
                        status=TaskStatus.OPEN,
                        due_date=utcnow() + timedelta(days=10),
                        source_type="capa",
                        source_id=capa.id,
                        system_generated=True,
                    ),
                ]
            )

        db.commit()
        print("Seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    run()
