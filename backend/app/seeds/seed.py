"""Idempotent seed script: system roles + permissions from the approved role
matrix, the initial administrator account, demo departments and staff, and a
demo task register so dashboards and reports show meaningful data.

Run with: uv run python -m app.seeds.seed
Safe to run repeatedly.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Department,
    DepartmentMembership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    Task,
    TaskAssignment,
    TaskDepartment,
    User,
    UserRole,
)
from app.domain.task_lifecycle import TaskStatus
from app.seeds.demo_data import (
    DEMO_DEPARTMENTS,
    DEMO_PASSWORD,
    DEMO_PEOPLE,
    DEMO_TASKS,
    STATUS_CYCLE,
)
from app.seeds.rbac_matrix import AUTHENTICATED_PERMISSIONS, ROLE_MATRIX

logger = logging.getLogger("decops.seed")


def seed_permissions_and_roles(db: Session) -> None:
    permission_cache: dict[str, Permission] = {}

    def ensure_permission(code: str) -> Permission:
        if code in permission_cache:
            return permission_cache[code]
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm is None:
            perm = Permission(code=code, description=code)
            db.add(perm)
            db.flush()
        permission_cache[code] = perm
        return perm

    # Baseline permissions every authenticated user receives
    for code in AUTHENTICATED_PERMISSIONS:
        ensure_permission(code)

    for role_name, spec in ROLE_MATRIX.items():
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=spec["description"], is_system_role=True)
            db.add(role)
            db.flush()
        for perm_code in spec["permissions"]:
            perm = ensure_permission(perm_code)
            exists = any(rp.permission_id == perm.id for rp in role.permissions)
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()


def seed_admin(db: Session) -> None:
    email = settings.seed_admin_email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            employee_code=settings.seed_admin_employee_code,
            full_name=settings.seed_admin_name,
            email=email,
            authentication_reference=hash_password(settings.seed_admin_password),
            account_status="active",
        )
        db.add(user)
        db.flush()
        logger.info("seeded admin user %s", email)

    # Grant Company Administrator + System Administrator (global scope)
    for role_name in ("Company Administrator", "System Administrator"):
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            continue
        existing = db.query(UserRole).filter_by(
            user_id=user.id, role_id=role.id, scope_type="global"
        ).first()
        if existing is None:
            db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global"))


def seed_departments_and_people(db: Session) -> None:
    """Create demo departments and staff accounts (idempotent)."""
    if db.scalar(select(Department).limit(1)) is None:
        for name, description in DEMO_DEPARTMENTS:
            db.add(Department(name=name, description=description))
        db.flush()

    demo_emails = [person["email"].lower() for person in DEMO_PEOPLE]
    if db.scalar(select(User).where(User.email.in_(demo_emails)).limit(1)) is not None:
        return

    role_by_name = {role.name: role for role in db.scalars(select(Role)).all()}
    department_by_name = {d.name: d for d in db.scalars(select(Department)).all()}
    for person in DEMO_PEOPLE:
        email = person["email"].lower()
        if db.scalar(select(User).where(User.email == email)) is not None:
            continue
        user = User(
            employee_code=person["employee_code"],
            full_name=person["full_name"],
            email=email,
            authentication_reference=hash_password(DEMO_PASSWORD),
            account_status="active",
        )
        db.add(user)
        db.flush()
        for role_name in person["roles"]:
            role = role_by_name.get(role_name)
            if role is not None:
                db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global"))
        membership = person.get("department")
        if membership:
            department = department_by_name.get(membership["name"])
            if department is not None:
                db.add(DepartmentMembership(
                    department_id=department.id,
                    user_id=user.id,
                    membership_role=(
                        MembershipRole.lead if membership.get("lead") else MembershipRole.member
                    ),
                ))
                if membership.get("lead") and department.department_lead_user_id is None:
                    department.department_lead_user_id = user.id
    db.flush()


def seed_demo_tasks(db: Session) -> None:
    """Populate a realistic task register (idempotent; skips when data exists)."""
    if db.query(Task).count() > 0:
        return
    department_by_name = {d.name: d for d in db.scalars(select(Department)).all()}
    user_by_email = {u.email: u for u in db.scalars(select(User)).all()}
    admin = user_by_email.get(settings.seed_admin_email.lower())
    if admin is None:
        return
    today = date.today()
    now = datetime.now()

    closed_statuses = {TaskStatus.completed.value, TaskStatus.cancelled.value}
    for index, spec in enumerate(DEMO_TASKS):
        title, description, department_name, assignee_email, priority, created_days_ago, due_in_days, percent = spec
        status = STATUS_CYCLE[index % len(STATUS_CYCLE)]
        department = department_by_name.get(department_name or "")
        assignee = user_by_email.get(assignee_email.lower())
        created_at = now - timedelta(days=created_days_ago)
        task = Task(
            task_number=f"TSK-{index + 1:04d}",
            title=title,
            description=description,
            status=status,
            priority=priority,
            accountable_pm_id=(assignee.id if assignee else admin.id),
            created_by_id=admin.id,
            start_date=(created_at.date()),
            due_date=today + timedelta(days=due_in_days),
            percent_complete=(percent if status not in closed_statuses else (100 if status == TaskStatus.completed.value else 0)),
            visibility_mode="department_scoped",
            created_at=created_at,
            updated_at=created_at,
            completed_at=(
                created_at + timedelta(days=max(1, created_days_ago // 2))
                if status == TaskStatus.completed.value else None
            ),
            cancelled_at=(
                created_at + timedelta(days=1)
                if status == TaskStatus.cancelled.value else None
            ),
        )
        db.add(task)
        db.flush()
        if department is not None:
            db.add(TaskDepartment(task_id=task.id, department_id=department.id))
        if assignee is not None:
            db.add(TaskAssignment(
                task_id=task.id,
                user_id=assignee.id,
                assignment_role="accountable_pm",
                assigned_by_id=admin.id,
            ))
    db.flush()


def run_seed() -> None:
    db = SessionLocal()
    try:
        seed_permissions_and_roles(db)
        seed_admin(db)
        seed_departments_and_people(db)
        seed_demo_tasks(db)
        db.commit()
        logger.info("seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_seed()
