"""Wrong-password lockout, stored in Postgres so it survives restarts.

Rate limiting only slows an IP; a botnet or a shared office NAT walks straight
past it. This is the per-account half of the same defence.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings


def is_locked(account, now: datetime) -> bool:
    until = account.locked_until
    if until is None:
        return False
    if until.tzinfo is None:  # drivers that hand back naive datetimes
        until = until.replace(tzinfo=timezone.utc)
    return until > now


def register_failure(db: Session, account, now: datetime) -> None:
    account.failed_attempts += 1
    if account.failed_attempts >= settings.login_max_attempts:
        account.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        account.failed_attempts = 0
    db.commit()


def register_success(db: Session, account) -> None:
    if account.failed_attempts or account.locked_until:
        account.failed_attempts = 0
        account.locked_until = None
        db.commit()
