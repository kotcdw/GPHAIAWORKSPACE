"""Access matrix: what each role may do, module by module and action by action.

GIAW's permissions are capabilities (for example "Fieldwork" or "Approve reports"); this table maps them onto the
familiar actions per module so administrators can read the role design at a glance. Each cell lists the permissions
that grant it; ``tier:staff`` means every internal audit account (Administrator, Manager, Auditor, Read-only User),
``tier:all`` every signed-in account. Deletion follows one rule everywhere and is described per row.
"""

from __future__ import annotations

ACTIONS = ("view", "create", "edit", "approve", "export", "configure")
DELETE_RULE = "Only records still in draft, never e-signed or linked; signed and issued records are kept"

ROWS: list[dict] = [
    {"module": "Users, roles and access", "view": ["system.users", "system.roles"], "create": ["system.users"],
     "edit": ["system.users"], "approve": ["system.users"], "export": ["system.users"],
     "configure": ["system.roles"],
     "delete": "Accounts without recorded activity only; the last administrator can never be removed"},
    {"module": "Organisational structure", "view": ["tier:staff"], "create": ["system.reference", "tier:staff"],
     "edit": ["system.reference", "tier:staff"], "approve": ["system.reference"], "export": ["data.export"],
     "configure": ["system.reference"],
     "delete": "Only pending units nothing uses; approved units are deactivated instead, keeping their history"},
    {"module": "Application settings", "view": ["system.config", "system.workflow", "system.reference"],
     "create": [], "edit": ["system.config", "system.workflow", "system.reference", "method.reporting",
                            "method.audit_types", "method.plan_config"],
     "approve": [], "export": [], "configure": ["system.config", "system.workflow", "system.automation"],
     "delete": "Settings are reset to their default, never deleted"},
    {"module": "Audit universe and libraries", "view": ["tier:staff"], "create": ["method.library"],
     "edit": ["method.library"], "approve": [], "export": ["data.export"],
     "configure": ["method.library", "method.programs"], "delete": DELETE_RULE},
    {"module": "Assurance planning", "view": ["tier:staff", "governance.view"], "create": ["plan.prepare"],
     "edit": ["plan.prepare", "plan.amend"], "approve": ["plan.approve"], "export": ["data.export"],
     "configure": ["method.plan_config"], "delete": DELETE_RULE},
    {"module": "Audit engagements and fieldwork", "view": ["tier:staff"], "create": ["audit.create"],
     "edit": ["audit.plan", "audit.fieldwork", "audit.workpapers", "audit.evidence"],
     "approve": ["audit.memo_approve", "review.workpapers", "audit.close"], "export": ["data.export"],
     "configure": ["method.audit_types", "method.programs"], "delete": DELETE_RULE},
    {"module": "Findings", "view": ["tier:staff"], "create": ["audit.findings"], "edit": ["audit.findings"],
     "approve": ["review.workpapers"], "export": ["data.export"], "configure": ["method.audit_types"],
     "delete": DELETE_RULE},
    {"module": "Audit reports", "view": ["tier:staff", "governance.view"], "create": ["report.prepare"],
     "edit": ["report.prepare"], "approve": ["report.review", "report.approve"], "export": ["data.export"],
     "configure": ["method.reporting"], "delete": "Reports are never deleted once sent to management"},
    {"module": "Follow-up and remediation", "view": ["tier:staff"], "create": ["audit.findings", "followup.manage"],
     "edit": ["followup.manage", "auditee.respond"], "approve": ["followup.validate", "followup.manage"],
     "export": ["data.export"], "configure": ["system.workflow"], "delete": DELETE_RULE},
    {"module": "Audit Committee and governance", "view": ["governance.view"], "create": ["committee.record"],
     "edit": ["committee.record"], "approve": ["committee.record"], "export": ["data.export"],
     "configure": ["governance.charter"], "delete": DELETE_RULE},
    {"module": "Risk and compliance registers", "view": ["grc.view"],
     "create": ["grc.risk", "grc.compliance", "grc.policy", "grc.assets"],
     "edit": ["grc.risk", "grc.compliance", "grc.policy", "grc.assets"], "approve": ["grc.policy_approve"],
     "export": ["data.export"], "configure": ["grc.manage"], "delete": DELETE_RULE},
    {"module": "Audit trail and backups", "view": ["system.technical"], "create": ["system.technical"],
     "edit": [], "approve": [], "export": ["system.technical"], "configure": ["system.technical"],
     "delete": "The audit trail can never be edited or deleted; old backups are removed by retention"},
]


def cell_granted(tokens: list[str], perms: set[str], tier: str, read_only: bool, action: str) -> bool:
    if read_only and action != "view" and action != "export":
        return False  # the server refuses every change from a Read-only User
    for t in tokens:
        if t == "tier:all":
            return True
        if t == "tier:staff" and tier in ("Admin", "Auditor"):
            return True
        if t in perms:
            return True
    return False
