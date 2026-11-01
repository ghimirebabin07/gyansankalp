"""Staff accounts: who may sign in, in what role, and on which courses.

There is no public route that creates an account. A staff row only exists because
a Super Admin made it here, which is what keeps the sign-in page from becoming a
registration page for the whole backend.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.deps import get_current_admin
from app.core.permissions import Cap, require
from app.core.security import hash_password
from app.db.session import get_db
from app.models.admin import (
    Admin,
    AdminActivityLog,
    AdminOtp,
    AdminRefreshToken,
    AdminRole,
    CourseAssignment,
)
from app.models.course import Course
from app.schemas.admin import (
    AdminOut,
    StaffActivityOut,
    StaffCoursesIn,
    StaffCreate,
    StaffUpdate,
)

# Every route below is a staff-management route, so one dependency covers them all.
router = APIRouter(
    prefix="/admin/staff",
    tags=["admin: staff"],
    dependencies=[Depends(require(Cap.staff_manage))],
)

LAST_SUPER_ADMIN = (
    "This is the last active Super Admin. Promote another account first."
)


def _get_staff(db: Session, admin_id: int) -> Admin:
    admin = db.get(Admin, admin_id)
    if admin is None:
        raise HTTPException(404, "Staff account not found")
    return admin


def _revoke_sessions(db: Session, admin_id: int) -> None:
    """End every live session for this person.

    Roles and activity are re-read from the database on each request, so a change
    already bites. Revoking the refresh tokens is what stops that session being
    silently renewed after its short access token expires.
    """
    now = func.now()
    db.execute(
        update(AdminRefreshToken)
        .where(
            AdminRefreshToken.admin_id == admin_id,
            AdminRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.execute(
        update(AdminOtp)
        .where(AdminOtp.admin_id == admin_id, AdminOtp.consumed_at.is_(None))
        .values(consumed_at=now)
    )


def _active_super_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(Admin.id)).where(
            Admin.role == AdminRole.super_admin, Admin.is_active.is_(True)
        )
    ) or 0


@router.get("", response_model=list[AdminOut])
def list_staff(db: Session = Depends(get_db)):
    return db.scalars(select(Admin).order_by(Admin.id)).all()


@router.post("", response_model=AdminOut, status_code=201)
def create_staff(
    body: StaffCreate, request: Request, db: Session = Depends(get_db),
    actor: Admin = Depends(get_current_admin),
):
    admin = Admin(
        email=body.email.lower(),
        full_name=body.full_name.strip(),
        role=body.role,
        is_active=True,
        # Authentication is Google plus a code, so this column is filled with a
        # hash of a random string nobody knows rather than a real password.
        password_hash=hash_password(secrets.token_urlsafe(32)),
    )
    db.add(admin)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A staff account with that email already exists")
    db.refresh(admin)
    record(db, actor, "staff.created", target=admin.email, request=request)
    db.commit()
    return admin


@router.patch("/{admin_id}", response_model=AdminOut)
def update_staff(
    admin_id: int,
    body: StaffUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(get_current_admin),
):
    admin = _get_staff(db, admin_id)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return admin

    new_email = None
    if "email" in changes:
        new_email = changes["email"].lower()
        if new_email != admin.email:
            # The Google subject was bound to the old address. Leaving it would let
            # a different person's verified account satisfy the new row.
            admin.google_sub = None

    loses_super_admin = (
        admin.role == AdminRole.super_admin
        and admin.is_active
        and (
            changes.get("is_active") is False
            or (changes.get("role") is not None and changes["role"] != AdminRole.super_admin)
        )
    )
    if loses_super_admin and _active_super_admins(db) <= 1:
        raise HTTPException(409, LAST_SUPER_ADMIN)

    if changes.get("is_active") is False and admin.id == actor.id:
        raise HTTPException(409, "You cannot deactivate your own account")

    if "full_name" in changes:
        admin.full_name = changes["full_name"].strip()
    if new_email is not None:
        admin.email = new_email
    if "role" in changes:
        admin.role = changes["role"]
    if "is_active" in changes:
        admin.is_active = changes["is_active"]

    if "role" in changes or "is_active" in changes:
        _revoke_sessions(db, admin.id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A staff account with that email already exists")
    db.refresh(admin)
    record(
        db,
        actor,
        "staff.updated",
        target=f"{admin.email} {changes.get('role', '')} {changes.get('is_active', '')}".strip(),
        request=request,
    )
    db.commit()
    return admin


@router.put("/{admin_id}/courses", response_model=list[int])
def set_courses(
    admin_id: int,
    body: StaffCoursesIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Admin = Depends(get_current_admin),
):
    """The courses this person is allowed to edit. Only an editor is limited by it."""
    admin = _get_staff(db, admin_id)
    ids = sorted(set(body.course_ids))
    if ids:
        found = db.scalars(select(Course.id).where(Course.id.in_(ids))).all()
        missing = set(ids) - set(found)
        if missing:
            raise HTTPException(404, f"Course not found: {sorted(missing)[0]}")

    db.execute(
        delete(CourseAssignment).where(CourseAssignment.admin_id == admin.id)
    )
    for course_id in ids:
        db.add(CourseAssignment(course_id=course_id, admin_id=admin.id))
    _revoke_sessions(db, admin.id)
    db.commit()
    record(db, actor, "staff.courses_set", target=admin.email, request=request)
    db.commit()
    return ids


@router.get("/{admin_id}/courses", response_model=list[int])
def get_courses(admin_id: int, db: Session = Depends(get_db)):
    _get_staff(db, admin_id)
    return sorted(
        db.scalars(
            select(CourseAssignment.course_id).where(
                CourseAssignment.admin_id == admin_id
            )
        ).all()
    )


@router.get("/{admin_id}/activity", response_model=list[StaffActivityOut])
def staff_activity(
    admin_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _get_staff(db, admin_id)
    stmt = (
        select(AdminActivityLog)
        .where(AdminActivityLog.admin_id == admin_id)
        .order_by(AdminActivityLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()
