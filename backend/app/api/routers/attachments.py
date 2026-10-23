"""Receipt attachments: upload, list, download, delete.

Uploads never trust the client filename: a random internal name is generated and
the resolved path is verified to stay inside UPLOAD_DIR (path-traversal guard).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.config import settings
from app.db import get_db
from app.models import Attachment, PaymentOccurrence, User
from app.schemas import AttachmentOut
from app.services import audit

router = APIRouter(prefix="/attachments", tags=["attachments"])

ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


def _upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(stored_name: str) -> Path:
    root = _upload_root()
    candidate = (root / stored_name).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый путь")
    return candidate


@router.get("/occurrence/{occurrence_id}", response_model=list[AttachmentOut])
def list_attachments(
    occurrence_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[Attachment]:
    if db.get(PaymentOccurrence, occurrence_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Период не найден")
    return list(
        db.query(Attachment)
        .filter(Attachment.occurrence_id == occurrence_id)
        .order_by(Attachment.created_at.desc())
        .all()
    )


@router.post("/occurrence/{occurrence_id}", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    occurrence_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf),
) -> Attachment:
    occurrence = db.get(PaymentOccurrence, occurrence_id)
    if occurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Период не найден")

    extension = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES and extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимы только PNG, JPEG, WEBP или PDF",
        )
    if content_type not in ALLOWED_TYPES:
        content_type = "application/pdf" if extension == ".pdf" else "application/octet-stream"

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    payload = await file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл больше {settings.MAX_UPLOAD_MB} МБ",
        )
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Пустой файл")

    stored_name = f"{uuid.uuid4().hex}{ALLOWED_TYPES.get(content_type, extension or '.bin')}"
    _safe_path(stored_name).write_bytes(payload)

    attachment = Attachment(
        occurrence_id=occurrence_id,
        original_name=(file.filename or "receipt")[:255],
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=len(payload),
        uploaded_by_id=user.id,
    )
    db.add(attachment)
    db.flush()
    audit.record(
        db,
        action="attachment.uploaded",
        entity_type="payment_occurrence",
        entity_id=occurrence_id,
        description=f"Загружен чек «{attachment.original_name}» к периоду {occurrence.due_date.isoformat()}",
        user=user,
    )
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    path = _safe_path(attachment.stored_name)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл отсутствует в хранилище")
    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.original_name,
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment"},
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _csrf: None = Depends(verify_csrf),
) -> Response:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    path = _safe_path(attachment.stored_name)
    if path.exists():
        path.unlink()
    audit.record(
        db,
        action="attachment.deleted",
        entity_type="payment_occurrence",
        entity_id=attachment.occurrence_id,
        description=f"Удалён чек «{attachment.original_name}»",
        user=user,
    )
    db.delete(attachment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
