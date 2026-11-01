"""What each staff role is allowed to do, in one place.

Admin routes ask for a capability rather than comparing a role inline, so "who can
delete a course" has exactly one answer, and a new endpoint that forgets to ask is
refused by its router instead of by luck.
"""

from enum import Enum

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.models.admin import Admin, AdminRole, CourseAssignment
from app.models.course import Course, Topic
from app.models.material import Material


class Cap(str, Enum):
    content_read = "content.read"
    content_write = "content.write"
    enrollments_manage = "enrollments.manage"
    staff_manage = "staff.manage"


ROLE_CAPS: dict[AdminRole, frozenset[Cap]] = {
    AdminRole.super_admin: frozenset(Cap),
    AdminRole.content_manager: frozenset(
        {Cap.content_read, Cap.content_write, Cap.enrollments_manage}
    ),
    # The write capability is real but narrowed by course assignment in
    # guard_course(), which is what keeps "editor" from meaning "every course".
    AdminRole.editor: frozenset({Cap.content_read, Cap.content_write}),
}

NOT_STAFF = "This account cannot be used to change content"


def require(cap: Cap):
    """Router- or route-level dependency that answers 403 for the wrong role."""

    def dependency(admin: Admin = Depends(get_current_admin)) -> Admin:
        if cap not in ROLE_CAPS.get(admin.role, frozenset()):
            raise HTTPException(403, NOT_STAFF)
        return admin

    return dependency


def assigned_course_ids(db: Session, admin: Admin) -> set[int] | None:
    """None means "not limited". Only an editor is limited."""
    if admin.role != AdminRole.editor:
        return None
    return set(
        db.scalars(
            select(CourseAssignment.course_id).where(CourseAssignment.admin_id == admin.id)
        ).all()
    )


def _course_of(db: Session, *, course_id: int | None, topic_id: int | None,
               material_id: int | None) -> Course:
    if course_id is not None:
        course = db.get(Course, course_id)
        if course is None:
            raise HTTPException(404, "Course not found")
        return course
    if topic_id is not None:
        topic = db.get(Topic, topic_id)
        if topic is None:
            raise HTTPException(404, "Topic not found")
        return topic.course
    material = db.get(Material, material_id)
    if material is None:
        raise HTTPException(404, "Material not found")
    topic = db.get(Topic, material.topic_id)
    if topic is None:
        raise HTTPException(404, "Topic not found")
    return topic.course


def guard_unscoped_write(db: Session, admin: Admin, verb: str) -> None:
    """Adding and removing a whole course is not assignment-scoped work.

    Someone who could create a course could create one nobody assigned them to and
    edit that freely, so these two actions stay with the unscoped roles.
    """
    if assigned_course_ids(db, admin) is not None:
        raise HTTPException(403, f"Editors cannot {verb} a course")


def guard_course(db: Session, admin: Admin, *, course_id: int | None = None,
                 topic_id: int | None = None, material_id: int | None = None) -> Course:
    """Resolve which course a change lands on, and refuse it if this role may not.

    Every admin call names the object it touches, so this is the one place an
    editor's assignment list is checked - for reads as well as writes, because a
    panel that lists courses they cannot edit still shows other people's work.
    """
    course = _course_of(
        db, course_id=course_id, topic_id=topic_id, material_id=material_id
    )
    allowed = assigned_course_ids(db, admin)
    if allowed is not None and course.id not in allowed:
        raise HTTPException(403, "This course is not assigned to you")
    return course
