"""User administration endpoints (): employee lifecycle and
global role assignment. All routes require users.manage; permission changes
are audited by the service layer."""

import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import DbSession, require_permission
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import AccountStatus, Role, User
from app.schemas.admin import (
    RoleAssignRequest,
    UserCreateRequest,
    UserDetailOut,
    UserStatusRequest,
    UserUpdateRequest,
)
from app.schemas.common import UserOut, UserPage
from app.services import user_admin_service

router = APIRouter(prefix="/users", tags=["Users"])


def _get_user_or_404(db, user_id: uuid.UUID) -> User:
    from sqlalchemy import select

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        # 404, not 403: avoid confirming the existence of protected resources
        raise NotFoundError("User not found.")
    return user


def _detail_out(user: User) -> UserDetailOut:
    from app.schemas.admin import MembershipOut
    from app.schemas.common import RoleBrief

    return UserDetailOut(
        id=user.id,
        employee_code=user.employee_code,
        full_name=user.full_name,
        email=user.email,
        account_status=user.account_status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        roles=[RoleBrief.model_validate(ur.role) for ur in user.roles],
        memberships=[MembershipOut.model_validate(m) for m in user.memberships],
    )


@router.get("", response_model=UserPage, dependencies=[Depends(require_permission("users.manage"))])
def list_users(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200, description="Filter by name or email"),
    status: AccountStatus | None = Query(None),
) -> UserPage:
    from sqlalchemy import func, or_, select

    stmt = select(User)
    count_stmt = select(func.count(User.id))
    filters = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if status is not None:
        filters.append(User.account_status == status)
    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return UserPage(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserDetailOut,
            dependencies=[Depends(require_permission("users.manage"))])
def get_user(db: DbSession, user_id: uuid.UUID) -> UserDetailOut:
    user = _get_user_or_404(db, user_id)
    return _detail_out(user)


@router.post("", response_model=UserDetailOut, status_code=201,
             dependencies=[Depends(require_permission("users.manage"))])
def create_user(payload: UserCreateRequest, request: Request, db: DbSession) -> UserDetailOut:
    actor: User = request.state.user
    try:
        user = user_admin_service.create_user(
            db,
            actor=actor,
            email=payload.email,
            full_name=payload.full_name,
            employee_code=payload.employee_code,
            password=payload.password,
            role_ids=payload.role_ids,
            request_id=current_request_id(),
        )
    except user_admin_service.UserAdminError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(user)
    return _detail_out(user)


@router.patch("/{user_id}", response_model=UserDetailOut,
              dependencies=[Depends(require_permission("users.manage"))])
def update_user(
    user_id: uuid.UUID, payload: UserUpdateRequest, request: Request, db: DbSession
) -> UserDetailOut:
    actor: User = request.state.user
    user = _get_user_or_404(db, user_id)
    try:
        user_admin_service.update_user(
            db, actor=actor, user=user,
            full_name=payload.full_name, email=payload.email,
            request_id=current_request_id(),
        )
    except user_admin_service.UserAdminError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(user)
    return _detail_out(user)


@router.post("/{user_id}/status", response_model=UserDetailOut,
             dependencies=[Depends(require_permission("users.manage"))])
def change_status(
    user_id: uuid.UUID, payload: UserStatusRequest, request: Request, db: DbSession
) -> UserDetailOut:
    actor: User = request.state.user
    user = _get_user_or_404(db, user_id)
    if actor.id == user.id and payload.status != AccountStatus.active:
        raise ValidationFailedError("You cannot deactivate your own account.")
    user_admin_service.set_account_status(
        db, actor=actor, user=user, status=payload.status, reason=payload.reason,
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(user)
    return _detail_out(user)


@router.post("/{user_id}/roles", response_model=UserDetailOut,
             dependencies=[Depends(require_permission("roles.assign"))])
def assign_role(
    user_id: uuid.UUID, payload: RoleAssignRequest, request: Request, db: DbSession
) -> UserDetailOut:
    actor: User = request.state.user
    user = _get_user_or_404(db, user_id)
    role = db.get(Role, payload.role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    user_admin_service.assign_global_role(
        db, actor=actor, user=user, role=role,
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(user)
    return _detail_out(user)


@router.delete("/{user_id}/roles/{role_id}", response_model=UserDetailOut,
               dependencies=[Depends(require_permission("roles.assign"))])
def revoke_role(
    user_id: uuid.UUID, role_id: uuid.UUID, request: Request, db: DbSession
) -> UserDetailOut:
    actor: User = request.state.user
    user = _get_user_or_404(db, user_id)
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    user_admin_service.revoke_global_role(
        db, actor=actor, user=user, role=role,
        request_id=current_request_id(),
    )
    db.commit()
    db.refresh(user)
    return _detail_out(user)
