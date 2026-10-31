from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.db.session import get_db
from app.models.course import Course, Topic
from app.schemas.course import (
    CourseAdminOut, CourseCreate, CourseUpdate,
    TopicCreate, TopicOut, TopicUpdate,
)

# Every route in this router requires an admin.
router = APIRouter(
    prefix="/admin", tags=["admin: courses"], dependencies=[Depends(get_current_admin)]
)


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    return course


@router.post("/courses", response_model=CourseAdminOut, status_code=201)
def create_course(body: CourseCreate, db: Session = Depends(get_db)):
    course = Course(**body.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug already exists")
    db.refresh(course)
    return course


@router.get("/courses", response_model=list[CourseAdminOut])
def list_courses(db: Session = Depends(get_db)):
    return db.scalars(select(Course).order_by(Course.id)).all()


@router.patch("/courses/{course_id}", response_model=CourseAdminOut)
def update_course(course_id: int, body: CourseUpdate, db: Session = Depends(get_db)):
    course = _get_course(db, course_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug already exists")
    db.refresh(course)
    return course


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: int, db: Session = Depends(get_db)):
    course = _get_course(db, course_id)
    db.delete(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Course has enrollments or materials. Unpublish it instead."
        )
    return Response(status_code=204)


@router.post("/courses/{course_id}/topics", response_model=TopicOut, status_code=201)
def create_topic(course_id: int, body: TopicCreate, db: Session = Depends(get_db)):
    _get_course(db, course_id)
    topic = Topic(course_id=course_id, **body.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicUpdate, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(topic, key, value)
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    db.delete(topic)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Topic still has materials. Delete them first.")
    return Response(status_code=204)
