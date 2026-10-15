"""Comments and attachments (Phase 6, MOD-006 + MOD-005).

Both are nested task resources: every operation is authorized through the task
access engine (COMMENT / ATTACH / VIEW / UPDATE), evaluated with fresh actor
state, so restricted content stays protected and cross-task access is
structurally impossible (every row is loaded through its owning task and
ids are verified against it before any read or write).

Authorization failures surface as 404, consistent with the rest of the API.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailedError
from app.domain import access_policy
from app.models import Attachment, Comment, Task, User, WorkItem
from app.services import audit_service, task_service


class CollaborationError(Exception):
    def __init__(self, message: str, *, code: str = "collaboration_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _authorize(db: Session, actor: User, task: Task, operation: access_policy.Operation) -> None:
    try:
        access_policy.require_access(
            task_service.build_actor_context(db, actor),
            task_service.build_policy(db, task),
            operation,
        )
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def list_comments(db: Session, *, actor: User, task: Task,
                  work_item_id: uuid.UUID | None = None) -> list[Comment]:
    _authorize(db, actor, task, access_policy.Operation.VIEW)
    stmt = (
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.task_id == task.id, Comment.deleted_at.is_(None))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .limit(500)
    )
    if work_item_id is not None:
        stmt = stmt.where(Comment.work_item_id == work_item_id)
    return list(db.scalars(stmt).all())


def create_comment(db: Session, *, actor: User, task: Task, body: str,
                   work_item_id: uuid.UUID | None = None) -> Comment:
    _authorize(db, actor, task, access_policy.Operation.COMMENT)
    text = (body or "").strip()
    if not text:
        raise ValidationFailedError("Comment body must not be empty.")
    if len(text) > 10_000:
        raise ValidationFailedError("Comment body exceeds the 10,000 character limit.")
    if work_item_id is not None:
        item = db.get(WorkItem, work_item_id)
        if item is None or item.task_id != task.id:
            # Do not confirm work items of other tasks (cross-task isolation).
            raise ValidationFailedError("The referenced work item does not exist on this task.")
    comment = Comment(task_id=task.id, work_item_id=work_item_id, author_id=actor.id, body=text)
    db.add(comment)
    db.flush()
    task_service.record_activity(
        db, task=task, actor=actor, activity_type="comment.added",
        summary=f"{actor.full_name} commented on the task",
        detail={"comment_id": str(comment.id)},
    )
    return comment


def delete_comment(db: Session, *, actor: User, task: Task, comment_id: uuid.UUID) -> None:
    _authorize(db, actor, task, access_policy.Operation.VIEW)
    comment = db.scalar(
        select(Comment).options(joinedload(Comment.author))
        .where(Comment.id == comment_id, Comment.task_id == task.id)
    )
    if comment is None or comment.is_deleted:
        raise NotFoundError("Comment not found.")
    is_author = comment.author_id == actor.id
    if not is_author:
        # Only task managers (UPDATE operation) may remove other people's comments.
        _authorize(db, actor, task, access_policy.Operation.UPDATE)
    comment.deleted_at = datetime.now(UTC)
    db.flush()
    audit_service.record_audit_event(
        db, action="comment.deleted", resource_type="comment", resource_id=comment.id,
        actor=actor, change_summary=f"Comment deleted on {task.task_number}",
        metadata={"task_id": str(task.id), "by_author": is_author},
    )


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _validate_upload(db: Session, task: Task, upload: UploadFile, *, work_item_id: uuid.UUID | None) -> tuple[bytes, str]:
    cfg = get_settings()
    filename = Path(upload.filename or "").name.strip()
    if not filename or filename in {".", ".."}:
        raise ValidationFailedError("A valid file name is required.")
    extension = Path(filename).suffix.lower()
    if extension not in cfg.attachment_allowed_extensions:
        raise ValidationFailedError(
            f"Files of type '{extension or 'unknown'}' are not allowed. "
            f"Allowed: {', '.join(cfg.attachment_allowed_extensions)}"
        )
    if work_item_id is not None:
        item = db.get(WorkItem, work_item_id)
        if item is None or item.task_id != task.id:
            raise ValidationFailedError("The referenced work item does not exist on this task.")
    content = upload.file.read()
    if len(content) == 0:
        raise ValidationFailedError("The uploaded file is empty.")
    if len(content) > cfg.attachment_max_bytes:
        limit_mb = cfg.attachment_max_bytes // (1024 * 1024)
        raise ValidationFailedError(f"The uploaded file exceeds the {limit_mb} MB size limit.")
    return content, filename


def create_attachment(db: Session, *, actor: User, task: Task, upload: UploadFile,
                      work_item_id: uuid.UUID | None = None) -> Attachment:
    _authorize(db, actor, task, access_policy.Operation.ATTACH)
    content, filename = _validate_upload(db, task, upload, work_item_id=work_item_id)
    cfg = get_settings()

    task_dir = Path(cfg.attachment_storage_dir) / str(task.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    storage_key = f"tasks/{task.id}/{uuid.uuid4().hex}"
    (Path(cfg.attachment_storage_dir) / str(task.id) / Path(storage_key).name).write_bytes(content)

    attachment = Attachment(
        task_id=task.id,
        work_item_id=work_item_id,
        uploaded_by_id=actor.id,
        original_filename=filename[:255],
        storage_key=storage_key,
        content_type=(upload.content_type or "application/octet-stream")[:120],
        size_bytes=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        scan_status="accepted",  # AV integration point; downloads stay authorization-gated
    )
    db.add(attachment)
    db.flush()
    task_service.record_activity(
        db, task=task, actor=actor, activity_type="attachment.added",
        summary=f"{actor.full_name} attached {attachment.original_filename}",
        detail={"attachment_id": str(attachment.id), "size_bytes": attachment.size_bytes},
    )
    audit_service.record_audit_event(
        db, action="attachment.uploaded", resource_type="attachment", resource_id=attachment.id,
        actor=actor, change_summary=f"{filename} attached to {task.task_number}",
        metadata={"task_id": str(task.id), "size_bytes": attachment.size_bytes},
    )
    return attachment


def list_attachments(db: Session, *, actor: User, task: Task) -> list[Attachment]:
    _authorize(db, actor, task, access_policy.Operation.VIEW)
    return list(db.scalars(
        select(Attachment)
        .options(joinedload(Attachment.uploaded_by))
        .where(Attachment.task_id == task.id, Attachment.deleted_at.is_(None))
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
        .limit(500)
    ).all())


def get_attachment_for_download(db: Session, *, actor: User, task: Task,
                                attachment_id: uuid.UUID) -> Attachment:
    _authorize(db, actor, task, access_policy.Operation.VIEW)
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.task_id != task.id or attachment.is_deleted:
        raise NotFoundError("Attachment not found.")
    return attachment


def attachment_path(attachment: Attachment) -> Path:
    cfg = get_settings()
    key = Path(attachment.storage_key)
    # storage_key is "tasks/<task_id>/<file>"; keep it relative to the storage dir.
    path = (Path(cfg.attachment_storage_dir) / Path(*key.parts[1:])).resolve()
    root = Path(cfg.attachment_storage_dir).resolve()
    if not str(path).startswith(str(root)):
        raise NotFoundError("Attachment not found.")
    if not path.is_file():
        raise NotFoundError("Attachment file is missing from storage.")
    return path


def delete_attachment(db: Session, *, actor: User, task: Task, attachment_id: uuid.UUID) -> None:
    _authorize(db, actor, task, access_policy.Operation.VIEW)
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.task_id != task.id or attachment.is_deleted:
        raise NotFoundError("Attachment not found.")
    if attachment.uploaded_by_id != actor.id:
        _authorize(db, actor, task, access_policy.Operation.UPDATE)
    attachment.deleted_at = datetime.now(UTC)
    db.flush()
    audit_service.record_audit_event(
        db, action="attachment.deleted", resource_type="attachment", resource_id=attachment.id,
        actor=actor, change_summary=f"{attachment.original_filename} removed from {task.task_number}",
        metadata={"task_id": str(task.id)},
    )
