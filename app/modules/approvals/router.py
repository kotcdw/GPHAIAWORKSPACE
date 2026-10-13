"""Generic electronic-signature route.

Records an approver's attestation against any record identified by
``record_type`` + ``record_id``. Module-specific routes (organizations approve,
CAPA close, audit close) add their own status transitions on top of this.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.core.access import load_record
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_module_tier
from app.core.enums import Role
from app.modules.approvals.models import ApprovalCycle
from app.modules.approvals.schemas import ApprovalSignIn
from app.modules.users.models import User

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

SignApproval = Depends(require_module_tier("approvals", Role.Admin, Role.Auditor))


@router.post("/sign", response_model=dict)
def sign_record(
    payload: ApprovalSignIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = SignApproval,
) -> dict:
    record = load_record(db, payload.record_type, payload.record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    entry = sign(
        db,
        preparer_id=getattr(record, "created_by", None),
        record_type=payload.record_type,
        record_id=payload.record_id,
        user=user,
        password=payload.password,
        decision=payload.decision.value,
        comment=payload.comment,
        request=request,
    )
    log_action(
        db,
        user_id=user.id,
        action=f"ESIGN {payload.record_type}#{payload.record_id} {payload.decision.value} cycle={entry.cycle_no}",
        request=request,
    )
    db.commit()
    db.refresh(entry)
    return _serialize(entry)


def _serialize(entry: ApprovalCycle) -> dict:
    return {
        "id": entry.id,
        "record_type": entry.record_type,
        "record_id": entry.record_id,
        "cycle_no": entry.cycle_no,
        "approver_id": entry.approver_id,
        "decision": entry.decision.value,
        "comment": entry.comment,
        "timestamp": entry.timestamp.isoformat(),
    }