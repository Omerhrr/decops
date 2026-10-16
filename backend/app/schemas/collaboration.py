"""Schemas for collaboration & notification endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tasks import TaskUserBrief


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)
    work_item_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    work_item_id: uuid.UUID | None
    body: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    author: TaskUserBrief


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    work_item_id: uuid.UUID | None
    original_filename: str
    content_type: str
    size_bytes: int
    checksum: str
    scan_status: str
    created_at: datetime
    deleted_at: datetime | None
    uploaded_by: TaskUserBrief


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    resource_type: str
    resource_id: str | None
    payload: dict | None
    read_at: datetime | None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread: int


class UnreadCountOut(BaseModel):
    unread: int


class NotificationPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    in_app_enabled: bool
    email_enabled: bool


class NotificationPreferencesOut(BaseModel):
    preferences: list[NotificationPreferenceOut]


class NotificationPreferenceUpdate(BaseModel):
    event_type: str = Field(min_length=1, max_length=60)
    in_app_enabled: bool
    email_enabled: bool


class WorkerPassOut(BaseModel):
    claimed: int
    processed: int = 0
    retry: int = 0
    permanent: int = 0
    deadline_created: int = 0
