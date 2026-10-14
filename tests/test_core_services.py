"""Unit tests for the core engines: refs, history, tasks and approvals."""

from __future__ import annotations

from app.core.enums import Role
from app.core.history import list_record_history, log_record_history
from app.core.refs import format_reference, next_reference
from app.core.tasksvc import auto_task_for_record, create_task
from app.platform.approvals.models import ApprovalCycle
from app.platform.history.models import RecordHistory
from tests.conftest import make_user


def test_format_reference_pads():
    assert format_reference("NC", 7) == "NC-0007"
    assert format_reference("CAPA", 12345) == "CAPA-12345"


def test_next_reference_is_monotonic_and_unique(db):
    # Other test modules may already have consumed numbers: assert relative order.
    first = next_reference(db, "NC")
    second = next_reference(db, "NC")
    other = next_reference(db, "CAPA")
    assert first.startswith("NC-") and len(first) >= len("NC-0001")
    assert int(second.split("-")[1]) == int(first.split("-")[1]) + 1
    assert other.startswith("CAPA-")
    db.rollback()


def test_record_history_roundtrip(db):
    user = make_user(db, "histuser", Role.Admin)
    log_record_history(
        db, record_type="nc", record_id=1, user_id=user.id, action="CREATED", cycle_no=1
    )
    log_record_history(
        db, record_type="nc", record_id=1, user_id=user.id, action="APPROVED", cycle_no=1
    )
    log_record_history(
        db, record_type="nc", record_id=1, user_id=user.id, action="REJECTED", cycle_no=2
    )
    db.commit()

    all_entries = list_record_history(db, "nc", 1)
    assert [e.action for e in all_entries] == ["CREATED", "APPROVED", "REJECTED"]
    cycle1 = list_record_history(db, "nc", 1, cycle_no=1)
    assert [e.action for e in cycle1] == ["CREATED", "APPROVED"]
    assert db.query(RecordHistory).count() >= 3


def test_create_and_auto_task(db):
    user = make_user(db, "taskuser", Role.Auditor, email="owner@example.com")

    manual = create_task(db, title="Manual task", assignee_id=user.id, assignor_id=user.id)
    assert manual.status.value == "Open"
    assert manual.system_generated is False

    class _Record:
        id = 42
        owner_email = "owner@example.com"

    auto = auto_task_for_record(
        db, record_type="nc", record=_Record(), action="CREATED", assignor_id=user.id
    )
    assert auto.system_generated is True
    assert auto.assignee_id == user.id
    assert auto.source_type == "nc"
    assert auto.source_id == 42
    db.rollback()


def test_sign_approve_and_reject_cycles(db):
    from app.core.approvalsvc import current_cycle_no, sign

    approver = make_user(db, "signer", Role.Admin, password="Passw0rd!")

    entry = sign(
        db,
        record_type="audit",
        record_id=987654,
        user=approver,
        password="Passw0rd!",
        decision="Approve",
        comment="looks good",
    )
    assert entry.decision.value == "Approve"
    assert entry.cycle_no == 1

    # A rejection closes the cycle; the next signature opens cycle 2.
    rejected = sign(
        db,
        record_type="audit",
        record_id=987654,
        user=approver,
        password="Passw0rd!",
        decision="Reject",
    )
    assert rejected.cycle_no == 1
    assert current_cycle_no(db, "audit", 987654) == 2

    db.commit()
    assert db.query(ApprovalCycle).filter_by(record_id=987654).count() == 2
    actions = [e.action for e in list_record_history(db, "audit", 987654)]
    assert any("E-SIGN Approve" in a for a in actions)
    assert any("E-SIGN Reject" in a for a in actions)


def test_sign_rejects_bad_password(db):
    import pytest
    from fastapi import HTTPException

    from app.core.approvalsvc import sign

    approver = make_user(db, "signer2", Role.Admin, password="Passw0rd!")
    with pytest.raises(HTTPException):
        sign(
            db,
            record_type="audit",
            record_id=2,
            user=approver,
            password="wrong-password",
            decision="Approve",
        )
    db.rollback()