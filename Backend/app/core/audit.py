"""One row per staff action, written in the same transaction as the change.

Content edits and student access are the actions someone later asks about, so the
record shares the caller's commit: a change that rolled back leaves no row
claiming it happened.
"""

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.ratelimit import client_ip
from app.models.admin import Admin, AdminActivityLog


def record(db: Session, admin: Admin, action: str, target: str | None = None,
           request: Request | None = None) -> None:
    db.add(
        AdminActivityLog(
            admin_id=admin.id,
            action=action[:60],
            target=target[:160] if target else None,
            ip=client_ip(request) if request is not None else None,
        )
    )
