"""User administration endpoints (minimal Phase 2 scope; MOD-002 expands in Phase 3)."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_permission
from app.models import User
from app.schemas.common import UserOut, UserPage

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserPage, dependencies=[Depends(require_permission("users.manage"))])
def list_users(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200, description="Filter by name or email"),
) -> UserPage:
    from sqlalchemy import func, or_, select

    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        count_stmt = count_stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))

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
