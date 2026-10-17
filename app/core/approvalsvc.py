"""Electronic-signature approval engine.

Records an approver's decision in an ``approval_cycles`` row after verifying the
approver's password with bcrypt. The password is an attestation only and is
**never** persisted. A rejection starts a new cycle; approvals stay in the
current cycle. On approval an optional callback can advance the record's status.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import ApprovalDecision
from app.core.history import log_record_history
from app.core.security import verify_password
from app.platform.approvals.models import ApprovalCycle
from app.platform.users.models import User


def current_cycle_no(db: DBSession, record_type: str, record_id: int) -> int:
    """Return the cycle number the next signature will be recorded against."""
    last = db.execute(
        select(ApprovalCycle)
        .where(ApprovalCycle.record_type == record_type, ApprovalCycle.record_id == record_id)
        .order_by(ApprovalCycle.cycle_no.desc(), ApprovalCycle.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return 1
    # A rejection closes the cycle; the next signature opens a new one.
    if last.decision.value == "Reject":
        return last.cycle_no + 1
    return last.cycle_no


def sign(
    db: DBSession,
    *,
    record_type: str,
    record_id: int,
    user: User,
    password: str,
    decision: str,
    comment: str = "",
    request=None,  # noqa: ANN001
    on_approve: Callable[[DBSession], None] | None = None,
    preparer_id: int | None = None,
) -> ApprovalCycle:
    """Verify the password and record an approval/rejection attestation.

    ``decision`` is ``"Approve"`` or ``"Reject"``. On approval ``on_approve``
    (if given) runs in the same transaction, e.g. to close the record.
    """
    if decision not in ("Approve", "Reject"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decision must be Approve or Reject")
    # Segregation of duties: the person who prepared (created) a record may not
    # sign it off. ``preparer_id`` is the record's ``created_by``.
    if preparer_id is not None and preparer_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Segregation of duties: the preparer of a record cannot sign it off",
        )
    if not verify_password(password, user.password_hash):
        from app.core.audit import log_action

        db.rollback()  # the request fails: nothing else from it may be saved with the failure record
        log_action(db, user_id=user.id, request=request, commit=True,
                   action=f"ESIGN_FAILED wrong_password record={record_type} id={record_id}",
                   entity_type=record_type, entity_id=record_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password verification failed")

    decision_enum = ApprovalDecision(decision)
    cycle_no = current_cycle_no(db, record_type, record_id)
    entry = ApprovalCycle(
        record_type=record_type,
        record_id=record_id,
        cycle_no=cycle_no,
        approver_id=user.id,
        decision=decision_enum,
        comment=comment,
    )
    db.add(entry)
    db.flush()

    log_record_history(
        db,
        record_type=record_type,
        record_id=record_id,
        user_id=user.id,
        action=f"E-SIGN {decision_enum.value} cycle={cycle_no}" + (f" comment={comment}" if comment else ""),
        cycle_no=cycle_no,
        request=request,
    )

    if decision_enum == ApprovalDecision.Approve and on_approve is not None:
        on_approve(db)

    return entry