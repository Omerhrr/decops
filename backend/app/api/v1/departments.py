"""Department management endpoints: CRUD + membership
administration. Requires departments.manage; all changes audited."""

import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import DbSession, require_permission
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError
from app.models import Department, DepartmentStatus, MembershipRole, User
from app.schemas.admin import (
    DepartmentCreateRequest,
    DepartmentDetailOut,
    DepartmentMemberAddRequest,
    DepartmentOut,
    DepartmentUpdateRequest,
)
from app.services import department_service

router = APIRouter(prefix="/departments", tags=["Departments"])


def _get_department_or_404(db, department_id: uuid.UUID) -> Department:
    from sqlalchemy import select

    department = db.scalar(select(Department).where(Department.id == department_id))
    if department is None:
        raise NotFoundError("Department not found.")
    return department


def _count_members(db, department_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    from app.models import DepartmentMembership

    return int(db.scalar(
        select(func.count(DepartmentMembership.id))
        .where(DepartmentMembership.department_id == department_id)
    ) or 0)



def _brief(user: User | None) -> "DepartmentMemberUserBrief | None":
    from app.schemas.admin import DepartmentMemberUserBrief

    return DepartmentMemberUserBrief.model_validate(user) if user is not None else None


def _detail_out(db, department: Department) -> DepartmentDetailOut:
    from app.schemas.admin import DepartmentMembershipOut

    return DepartmentDetailOut(
        id=department.id,
        name=department.name,
        description=department.description,
        status=department.status,
        lead_user_id=department.department_lead_user_id,
        lead=_brief(department.lead),
        member_count=_count_members(db, department.id),
        memberships=[DepartmentMembershipOut.model_validate(m) for m in department.memberships],
    )


def _out(row) -> dict:
    d = row["department"]
    out = DepartmentOut(
        id=d.id,
        name=d.name,
        description=d.description,
        status=d.status,
        lead_user_id=d.department_lead_user_id,
        lead=_brief(d.lead),
        member_count=row["member_count"],
    )
    return out.model_dump(mode="json")


@router.get("", dependencies=[Depends(require_permission("users.manage", "departments.manage"))])
def list_departments(db: DbSession) -> list[dict]:
    return [_out(row) for row in department_service.list_departments(db)]


@router.post("", status_code=201, dependencies=[Depends(require_permission("departments.manage"))])
def create_department(payload: DepartmentCreateRequest, request: Request, db: DbSession) -> dict:
    actor: User = request.state.user
    try:
        department = department_service.create_department(
            db, actor=actor, name=payload.name, description=payload.description,
            lead_user_id=payload.lead_user_id, request_id=current_request_id(),
        )
    except department_service.DepartmentError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(department)
    return _detail_out(db, department).model_dump(mode="json")


@router.get("/{department_id}", dependencies=[Depends(require_permission("users.manage", "departments.manage"))])
def get_department(db: DbSession, department_id: uuid.UUID) -> dict:
    department = _get_department_or_404(db, department_id)
    return _detail_out(db, department).model_dump(mode="json")


@router.patch("/{department_id}", dependencies=[Depends(require_permission("departments.manage"))])
def update_department(
    department_id: uuid.UUID, payload: DepartmentUpdateRequest, request: Request, db: DbSession
) -> dict:
    actor: User = request.state.user
    department = _get_department_or_404(db, department_id)
    try:
        department_service.update_department(
            db, actor=actor, department=department,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            lead_user_id=payload.lead_user_id if "lead_user_id" in payload.model_fields_set else department_service.UNSET,
            request_id=current_request_id(),
        )
    except department_service.DepartmentError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(department)
    return _detail_out(db, department).model_dump(mode="json")


@router.post("/{department_id}/members", status_code=201,
             dependencies=[Depends(require_permission("departments.manage"))])
def add_member(
    department_id: uuid.UUID, payload: DepartmentMemberAddRequest, request: Request, db: DbSession
) -> dict:
    actor: User = request.state.user
    department = _get_department_or_404(db, department_id)
    user = db.get(User, payload.user_id)
    if user is None:
        raise NotFoundError("User not found.")
    try:
        department_service.add_member(
            db, actor=actor, department=department, user=user,
            membership_role=payload.membership_role,
            valid_from=payload.valid_from, valid_until=payload.valid_until,
            request_id=current_request_id(),
        )
    except department_service.DepartmentError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(department)
    return _detail_out(db, department).model_dump(mode="json")


@router.delete("/{department_id}/members/{user_id}", status_code=204,
               dependencies=[Depends(require_permission("departments.manage"))])
def remove_member(
    department_id: uuid.UUID, user_id: uuid.UUID, request: Request, db: DbSession
) -> None:
    actor: User = request.state.user
    department = _get_department_or_404(db, department_id)
    department_service.remove_member(
        db, actor=actor, department=department, user_id=user_id,
        request_id=current_request_id(),
    )
    db.commit()
