import logging
import os
import threading
import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import settings
from app.core.permissions import Cap, guard_course, require
from app.core.ratelimit import admin_upload, limit
from app.core.storage import Storage, get_storage
from app.db.session import get_db
from app.models.admin import Admin
from app.models.material import Material, MaterialStatus
from app.schemas.material import MaterialOut, MaterialUpdate

router = APIRouter(
    prefix="/admin", tags=["admin: materials"], dependencies=[Depends(require(Cap.content_read))]
)

log = logging.getLogger("admin.materials")


def _wake_worker() -> None:
    """Ask the conversion worker to start polling for the job just queued.

    A Render free service that gets no traffic sleeps, and a sleeping worker
    would leave a fresh PDF pending until something woke it. Waking takes half a
    minute, so this runs on its own thread: the admin's upload response must not
    wait on it.
    """
    url = settings.worker_url
    if not url:
        return

    def _ping() -> None:
        try:
            httpx.get(url, timeout=120)
        except Exception:
            log.warning("could not wake the conversion worker")

    threading.Thread(target=_ping, daemon=True).start()


def _get_material(db: Session, material_id: int) -> Material:
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.post(
    "/topics/{topic_id}/materials",
    response_model=MaterialOut,
    status_code=201,
    dependencies=[Depends(limit(admin_upload))],
)
def upload_material(
    topic_id: int,
    request: Request,
    title: str = Form(min_length=2, max_length=200),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
    admin: Admin = Depends(require(Cap.content_write)),
):
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Cheap early rejection. The real size limit is also set in the reverse proxy (Phase 9).
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes + 1_000_000:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB)")

    # Before anything is written to storage: an upload to a course this person
    # does not work on must not cost the bucket a file.
    guard_course(db, admin, topic_id=topic_id)

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
    record(db, admin, "material.uploaded", target=f"{topic_id}/{material.title}", request=request)
    db.commit()
    _wake_worker()
    return material


@router.get("/topics/{topic_id}/materials", response_model=list[MaterialOut])
def list_materials(
    topic_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_read)),
):
    guard_course(db, admin, topic_id=topic_id)
    stmt = select(Material).where(Material.topic_id == topic_id).order_by(Material.id)
    return db.scalars(stmt).all()


@router.get("/materials/{material_id}", response_model=MaterialOut)
def get_material(
    material_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_read)),
):
    material = _get_material(db, material_id)
    guard_course(db, admin, material_id=material_id)
    return material


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def rename_material(
    material_id: int,
    body: MaterialUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    material = _get_material(db, material_id)
    guard_course(db, admin, material_id=material_id)
    material.title = body.title.strip()
    db.commit()
    db.refresh(material)
    record(db, admin, "material.renamed", target=material.title, request=request)
    db.commit()
    return material


@router.post("/materials/{material_id}/retry", response_model=MaterialOut)
def retry_material(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    _get_material(db, material_id)
    guard_course(db, admin, material_id=material_id)
    result = db.execute(  # one atomic UPDATE
        update(Material)
        .where(Material.id == material_id, Material.status == MaterialStatus.failed)
        .values(status=MaterialStatus.pending, attempts=0, error=None)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(409, "Only failed materials can be retried")
    record(db, admin, "material.retried", target=str(material_id), request=request)
    db.commit()
    return db.get(Material, material_id)


def _purge(original_key: str, page_prefix: str) -> None:
    """Remove a material's objects, whatever the bucket decides to do about it.

    If this dies partway the remaining objects are unreachable garbage - no row
    names their keys, so no route can serve them - and they cost bucket space
    until the storage is trimmed by hand. A bucket that refuses is not a reason
    to make the admin press delete again.
    """
    try:
        storage = get_storage()
        storage.delete(original_key)
        storage.delete_prefix(page_prefix)
        log.info("purged %s", page_prefix)
    except Exception:
        log.warning("could not purge %s", page_prefix)


def _purge_objects(original_key: str, page_prefix: str) -> None:
    """Delete a material's files after the response, never inside it.

    Supabase's S3 endpoint rejects batched deletes, so one page costs one round
    trip of roughly 200 ms. A 300-page PDF is a minute of that, and an admin
    whose browser times out at 30 s sees a failed delete and presses it again.

    The database row is already committed when this starts, so the request that
    gave up access is never the request that waits on the bucket.
    """
    threading.Thread(target=_purge, args=(original_key, page_prefix), daemon=True).start()


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require(Cap.content_write)),
):
    material = _get_material(db, material_id)
    guard_course(db, admin, material_id=material_id)
    if material.status == MaterialStatus.processing:
        raise HTTPException(409, "Material is being processed. Try again in a minute.")
    title = material.title
    original_key = material.original_key
    page_prefix = f"pages/{material.id}/"
    # The row goes first: access is a property of the row, and refusing to
    # delete files that a request no longer points at keeps a slow bucket from
    # turning into a page a student can still read.
    db.delete(material)
    db.commit()
    record(db, admin, "material.deleted", target=f"{material_id}/{title}", request=request)
    db.commit()
    _purge_objects(original_key, page_prefix)
    return Response(status_code=204)
