import io
import logging
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import has_course_access
from app.core.deps import get_current_user
from app.core.storage import Storage, get_storage
from app.core.watermark import stamp
from app.db.session import get_db
from app.models.access_log import AccessLog
from app.models.course import Topic
from app.models.material import Material, MaterialStatus
from app.models.user import Role, User
from app.schemas.material import MaterialPublic

log = logging.getLogger(__name__)
router = APIRouter(tags=["materials"])

NO_STORE = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": 'inline; filename="page.jpg"',
}


def _require_access(db: Session, user: User, course_id: int) -> None:
    """Admins may preview everything. Students need an active enrollment."""
    if user.role == Role.admin:
        return
    if not has_course_access(db, user.id, course_id):
        raise HTTPException(403, "You do not have access to this course")


@router.get("/topics/{topic_id}/materials", response_model=list[MaterialPublic])
def list_topic_materials(
    topic_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found")
    _require_access(db, user, topic.course_id)
    stmt = (
        select(Material)
        .where(Material.topic_id == topic_id, Material.status == MaterialStatus.ready)
        .order_by(Material.id)
    )
    return [
        MaterialPublic.model_validate(material).model_copy(update={"topic_title": topic.title})
        for material in db.scalars(stmt).all()
    ]


@router.get("/materials/{material_id}/pages/{page_no}")
def get_page(
    request: Request,
    material_id: int,
    page_no: int = Path(ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    material = db.get(Material, material_id)
    if not material or material.status != MaterialStatus.ready or not material.page_count:
        raise HTTPException(404, "Material not found")

    topic = db.get(Topic, material.topic_id)
    _require_access(db, user, topic.course_id)

    if page_no > material.page_count:
        raise HTTPException(404, "Page not found")

    try:
        raw = storage.get_bytes(f"pages/{material.id}/{page_no}.jpg")
    except ClientError:
        log.exception("Page file missing in storage: material=%s page=%s", material.id, page_no)
        raise HTTPException(404, "Page not found")

    now = datetime.now(timezone.utc)
    stamped = stamp(
        Image.open(io.BytesIO(raw)),
        text=f"{user.phone}  ID{user.id}",
        footer=f"{user.phone} | ID{user.id} | {now:%Y-%m-%d %H:%M} UTC",
    )
    out = io.BytesIO()
    stamped.save(out, "JPEG", quality=80)

    db.add(
        AccessLog(
            user_id=user.id,
            material_id=material.id,
            page_no=page_no,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()

    return Response(content=out.getvalue(), media_type="image/jpeg", headers=NO_STORE)
