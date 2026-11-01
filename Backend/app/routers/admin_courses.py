from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.permissions import Cap, assigned_course_ids, guard_course, require, guard_unscoped_write
from app.db.session import get_db
from app.models.admin import Admin
from app.models.course import Course, Topic
from app.schemas.course import (
    CourseAdminOut, CourseCreate, CourseUpdate,
    TopicCreate, TopicOut, TopicUpdate,
)

# Reading the catalogue is the floor: any staff role may look, nothing more.
router = APIRouter(
    prefix="/admin", tags=["admin: courses"], dependencies=[Depends(require(Cap.content_read))]
)


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    return course


@router.post("/courses", response_model=CourseAdminOut, status_code=201)
def create_course(
    body: CourseCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    guard_unscoped_write(db, admin, "create")
    course = Course(**body.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug already exists")
    db.refresh(course)
    record(db, admin, "course.created", target=course.slug, request=request)
    db.commit()
    return course


@router.get("/courses", response_model=list[CourseAdminOut])
def list_courses(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_read)),
):
    """An editor sees the courses they were given, not the whole catalogue."""
    allowed = assigned_course_ids(db, admin)
    if allowed is not None and not allowed:
        return []
    stmt = select(Course).order_by(Course.id)
    if allowed is not None:
        stmt = stmt.where(Course.id.in_(allowed))
    return db.scalars(stmt).all()


@router.patch("/courses/{course_id}", response_model=CourseAdminOut)
def update_course(
    course_id: int,
    body: CourseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    course = guard_course(db, admin, course_id=course_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug already exists")
    db.refresh(course)
    record(db, admin, "course.updated", target=course.slug, request=request)
    db.commit()
    return course


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    guard_unscoped_write(db, admin, "delete")
    course = _get_course(db, course_id)
    slug = course.slug
    db.delete(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Course has enrollments or materials. Unpublish it instead."
        )
    record(db, admin, "course.deleted", target=slug, request=request)
    db.commit()
    return Response(status_code=204)


@router.post("/courses/{course_id}/topics", response_model=TopicOut, status_code=201)
def create_topic(
    course_id: int,
    body: TopicCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    guard_course(db, admin, course_id=course_id)
    topic = Topic(course_id=course_id, **body.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    record(db, admin, "topic.created", target=f"course {course_id} / {topic.title}", request=request)
    db.commit()
    return topic


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(
    topic_id: int,
    body: TopicUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    guard_course(db, admin, topic_id=topic_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(topic, key, value)
    db.commit()
    db.refresh(topic)
    record(db, admin, "topic.updated", target=topic.title, request=request)
    db.commit()
    return topic


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    guard_course(db, admin, topic_id=topic_id)
    title = topic.title
    db.delete(topic)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Topic still has materials. Delete them first.")
    record(db, admin, "topic.deleted", target=title, request=request)
    db.commit()
    return Response(status_code=204)
