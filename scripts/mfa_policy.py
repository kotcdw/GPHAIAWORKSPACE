"""Show or change which roles must use two-step verification, from the server.

For an administrator who is locked out because two-step verification became mandatory and no
authenticator app is at hand. Run on the machine that hosts the app (direct database access):
    uv run python -m scripts.mfa_policy                 (show the current setting)
    uv run python -m scripts.mfa_policy --clear         (make two-step optional for every role)
    uv run python -m scripts.mfa_policy --roles Admin   (require it for these roles only)
    uv run python -m scripts.mfa_policy --off           (stop enforcing it; roles are kept)
    uv run python -m scripts.mfa_policy --on            (enforce it for the configured roles)

The change is recorded in the audit log. Prefer setting up two-step verification in the profile;
use this only to recover access, then set the policy again under Configuration > Security.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main  # noqa: E402, F401  (registers every model with SQLAlchemy)
from app.core.appconfig import AppConfig, cfg, invalidate  # noqa: E402
from app.core.audit import log_action  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.dbcheck import ensure_schema  # noqa: E402
from app.core.enums import Role  # noqa: E402

KEY = "mfa_required_roles"


def _set(key: str, value) -> int:  # noqa: ANN001
    db = SessionLocal()
    try:
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=json.dumps(value)))
        else:
            row.value = json.dumps(value)
        log_action(db, user_id=None, action=f"CONFIG_SET {key}={value} (server script)")
        db.commit()
    finally:
        db.close()
    invalidate()
    print(f"{key} is now {value}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--clear", action="store_true", help="two-step verification optional for everyone")
    group.add_argument("--on", action="store_true", help="enforce two-step verification for the configured roles")
    group.add_argument("--off", action="store_true", help="stop enforcing two-step verification")
    group.add_argument(
        "--roles", nargs="+", metavar="ROLE", help=f"roles that must use it ({', '.join(r.value for r in Role)})"
    )
    args = parser.parse_args()
    ensure_schema()
    print(f"Enforced: {'yes' if cfg('mfa_enforced') else 'no'}. "
          f"Roles that must use two-step verification when enforced: {', '.join(cfg(KEY)) or 'none'}")
    if args.on or args.off:
        return _set("mfa_enforced", bool(args.on))
    if not args.clear and not args.roles:
        return 0
    roles = [] if args.clear else args.roles
    unknown = [r for r in roles if r not in {x.value for x in Role}]
    if unknown:
        print(f"Unknown role(s): {', '.join(unknown)}")
        return 1
    db = SessionLocal()
    try:
        row = db.get(AppConfig, KEY)
        if row is None:
            row = AppConfig(key=KEY, value=json.dumps(roles))
            db.add(row)
        else:
            row.value = json.dumps(roles)
        log_action(db, user_id=None, action=f"CONFIG_SET {KEY}={roles} (server script)")
        db.commit()
    finally:
        db.close()
    invalidate()
    print(f"Saved. Roles that must use two-step verification: {', '.join(roles) or 'none'}")
    print("Restart the app (or wait a minute) for every worker to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
