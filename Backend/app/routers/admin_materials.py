import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.storage import Storage, get_storage
from app.db.session import get_db
from app.models.course import Topic
from app.models.material import Material, MaterialStatus
from app.schemas.material import MaterialOut, MaterialUpdate

router = APIRouter(
    prefix="/admin", tags=["admin: materials"], dependencies=[Depends(get_current_admin)]
)


def _get_material(db: Session, material_id: int) -> Material:
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.post("/topics/{topic_id}/materials", response_model=MaterialOut, status_code=201)
def upload_material(
    topic_id: int,
    request: Request,
    title: str = Form(min_length=2, max_length=200),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Cheap early rejection. The real size limit is also set in the reverse proxy (Phase 9).
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes + 1_000_000:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB)")

    if not db.get(Topic, topic_id):
        raise HTTPException(404, "Topic not found")

    # Never trust the filename or Content-Type. Check the PDF signature instead.
    if file.file.read(5) != b"%PDF-":
        raise HTTPException(400, "Only PDF files are accepted")
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > max_bytes:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB)")

    key = f"originals/{uuid.uuid4().hex}.pdf"  # random key, the filename is never used
    storage.put_fileobj(key, file.file, "application/pdf")

    material = Material(
        topic_id=topic_id, title=title.strip(), original_key=key, size_bytes=size
    )
    db.add(material)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)  # do not leave an orphan file behind
        raise
    db.refresh(material)
    return material


@router.get("/topics/{topic_id}/materials", response_model=list[MaterialOut])
def list_materials(topic_id: int, db: Session = Depends(get_db)):
    stmt = select(Material).where(Material.topic_id == topic_id).order_by(Material.id)
    return db.scalars(stmt).all()


@router.get("/materials/{material_id}", response_model=MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_db)):
    return _get_material(db, material_id)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def rename_material(material_id: int, body: MaterialUpdate, db: Session = Depends(get_db)):
    material = _get_material(db, material_id)
    material.title = body.title.strip()
    db.commit()
    db.refresh(material)
    return material


@router.post("/materials/{material_id}/retry", response_model=MaterialOut)
def retry_material(material_id: int, db: Session = Depends(get_db)):
    _get_material(db, material_id)
    result = db.execute(  # one atomic UPDATE
        update(Material)
        .where(Material.id == material_id, Material.status == MaterialStatus.failed)
        .values(status=MaterialStatus.pending, attempts=0, error=None)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(409, "Only failed materials can be retried")
    return db.get(Material, material_id)


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    material = _get_material(db, material_id)
    if material.status == MaterialStatus.processing:
        raise HTTPException(409, "Material is being processed. Try again in a minute.")
    # Files first, row second. If storage fails, the row stays and you can retry.
    storage.delete(material.original_key)
    storage.delete_prefix(f"pages/{material.id}/")
    db.delete(material)
    db.commit()
    return Response(status_code=204)
