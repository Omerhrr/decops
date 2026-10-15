"""Collaboration endpoints: task comments and private attachments (Phase 6).

Route-level authentication only - every operation is authorized against the
task's access policy inside the service (404, never 403, for outsiders).
"""

import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.collaboration import AttachmentOut, CommentCreate, CommentOut
from app.services import collaboration_service, task_service

router = APIRouter(prefix="/tasks", tags=["Collaboration"])


def _auth(request: Request, user: CurrentUser) -> User:
    request.state.user = user
    return user


def _load_task(db, actor: User, task_id: uuid.UUID):
    return task_service.get_task_for_actor(db, actor, task_id)


@router.get("/{task_id}/comments")
def list_comments(
    task_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
    work_item_id: uuid.UUID | None = Query(default=None),
) -> list[dict]:
    task = _load_task(db, user, task_id)
    comments = collaboration_service.list_comments(db, actor=user, task=task, work_item_id=work_item_id)
    return [CommentOut.model_validate(c).model_dump(mode="json") for c in comments]


@router.post("/{task_id}/comments", status_code=201)
def create_comment(
    task_id: uuid.UUID, payload: CommentCreate, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    task = _load_task(db, user, task_id)
    comment = collaboration_service.create_comment(
        db, actor=user, task=task, body=payload.body, work_item_id=payload.work_item_id,
    )
    db.commit()
    db.refresh(comment)
    return CommentOut.model_validate(comment).model_dump(mode="json")


@router.delete("/{task_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    task_id: uuid.UUID, comment_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> None:
    task = _load_task(db, user, task_id)
    collaboration_service.delete_comment(db, actor=user, task=task, comment_id=comment_id)
    db.commit()


@router.post("/{task_id}/attachments", status_code=201)
def upload_attachment(
    task_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
    file: UploadFile = File(...),
    work_item_id: uuid.UUID | None = None,
) -> dict:
    task = _load_task(db, user, task_id)
    try:
        attachment = collaboration_service.create_attachment(
            db, actor=user, task=task, upload=file, work_item_id=work_item_id,
        )
    except collaboration_service.CollaborationError as exc:
        from app.core.errors import ValidationFailedError

        raise ValidationFailedError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(attachment)
    return AttachmentOut.model_validate(attachment).model_dump(mode="json")


@router.get("/{task_id}/attachments")
def list_attachments(
    task_id: uuid.UUID, request: Request, db: DbSession, user: User = Depends(_auth),
) -> list[dict]:
    task = _load_task(db, user, task_id)
    attachments = collaboration_service.list_attachments(db, actor=user, task=task)
    return [AttachmentOut.model_validate(a).model_dump(mode="json") for a in attachments]


@router.get("/{task_id}/attachments/{attachment_id}/download")
def download_attachment(
    task_id: uuid.UUID, attachment_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> FileResponse:
    task = _load_task(db, user, task_id)
    attachment = collaboration_service.get_attachment_for_download(
        db, actor=user, task=task, attachment_id=attachment_id,
    )
    path = collaboration_service.attachment_path(attachment)
    return FileResponse(
        path,
        filename=attachment.original_filename,
        media_type=attachment.content_type,
    )


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    task_id: uuid.UUID, attachment_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> None:
    task = _load_task(db, user, task_id)
    collaboration_service.delete_attachment(db, actor=user, task=task, attachment_id=attachment_id)
    db.commit()
