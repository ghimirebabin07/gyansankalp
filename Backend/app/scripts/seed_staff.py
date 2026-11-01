"""Seed the staff roster. Run once after `alembic upgrade head`.

    python -m app.scripts.seed_staff

The addresses come from STAFF_ROSTER in Backend/.env, as comma-separated
"email:Full Name:role" entries. They stay out of the repository because they are
the accounts allowed through the admin door:

    STAFF_ROSTER=someone@example.com:Some Name:super_admin, ...

Idempotent: an existing address is left alone, so re-running cannot demote someone
who has since been given a different role in the panel.

Staff authenticate with Google plus a code sent to their mailbox, so no password is
asked for or stored here. The password column still exists for the old rows and is
filled with a hash of a random string nobody knows, which authenticates nothing.

The bound Google account is picked up on that person's first sign-in, so an account
can be created before anyone has tried to log in with it.
"""

import secrets

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin import Admin, AdminRole


def parse_roster(raw: str) -> list[tuple[str, str, AdminRole]]:
    valid_roles = ", ".join(role.value for role in AdminRole)
    roster: list[tuple[str, str, AdminRole]] = []
    seen: set[str] = set()

    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [field.strip() for field in chunk.split(":")]
        if len(parts) != 3:
            raise SystemExit(
                f'STAFF_ROSTER entry "{chunk}" is not "email:Full Name:role"'
            )
        email, full_name, role_name = parts
        if "@" not in email or "." not in email.split("@")[-1]:
            raise SystemExit(f'STAFF_ROSTER address "{email}" is not an email')
        try:
            role = AdminRole(role_name)
        except ValueError:
            raise SystemExit(
                f'STAFF_ROSTER role "{role_name}" is not one of: {valid_roles}'
            )
        if email.lower() in seen:
            raise SystemExit(f"STAFF_ROSTER lists {email.lower()} twice")
        seen.add(email.lower())
        roster.append((email.lower(), full_name, role))

    if not roster:
        raise SystemExit(
            "STAFF_ROSTER is empty. Add the staff list to Backend/.env first, e.g.\n"
            f'  STAFF_ROSTER=you@gmail.com:Your Name:{AdminRole.super_admin.value}'
        )
    return roster


def main() -> None:
    roster = parse_roster(settings.staff_roster)
    db = SessionLocal()
    try:
        for email, full_name, role in roster:
            existing = db.scalar(select(Admin).where(Admin.email == email))
            if existing:
                print(f"exists   {email} ({existing.role.value})")
                continue
            db.add(
                Admin(
                    email=email,
                    full_name=full_name,
                    role=role,
                    is_active=True,
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                )
            )
            print(f"created  {email} ({role.value})")
        db.commit()

        supers = db.scalars(
            select(Admin).where(Admin.role == AdminRole.super_admin,
                                 Admin.is_active.is_(True))
        ).all()
        if not supers:
            print("\nWARNING: no active Super Admin. Staff management is unreachable.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
