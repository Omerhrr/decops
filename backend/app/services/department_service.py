"""Department management service : department lifecycle, lead
assignment, and membership changes - all audited."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Department, DepartmentMembership, DepartmentStatus, MembershipRole, User
from app.services import audit_service


class DepartmentError(Exception):
    def __init__(self, message: str, *, code: str = "department_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _enum_value(value) -> str:
    """Columns typed String() may return plain strings or str-enums depending
    on the driver - normalize before comparing or summarizing."""
    return value.value if hasattr(value, "value") else str(value)


def get_department(db: Session, department_id: uuid.UUID) -> Department | None:
    return db.get(Department, department_id)


def get_by_name(db: Session, name: str) -> Department | None:
    return db.scalar(select(Department).where(Department.name == name.strip()))


def list_departments(db: Session, *, include_inactive: bool = True) -> list[dict]:
    """Departments with live member counts for admin listings."""
    stmt = select(Department).order_by(Department.name)
    if not include_inactive:
        stmt = stmt.where(Department.status == DepartmentStatus.active)
    departments = db.scalars(stmt).all()
    counts = dict(
        db.execute(
            select(DepartmentMembership.department_id, func.count(DepartmentMembership.id))
            .group_by(DepartmentMembership.department_id)
        ).all()
    )
    result = []
    for d in departments:
        result.append({
            "department": d,
            "member_count": int(counts.get(d.id, 0)),
        })
    return result


def create_department(
    db: Session,
    *,
    actor: User | None,
    name: str,
    description: str | None = None,
    lead_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> Department:
    if get_by_name(db, name) is not None:
        raise DepartmentError("A department with this name already exists.", code="name_taken")
    lead: User | None = None
    if lead_user_id is not None:
        lead = db.get(User, lead_user_id)
        if lead is None:
            raise DepartmentError("The selected department lead does not exist.", code="lead_not_found")
    department = Department(
        name=name.strip(),
        description=(description or "").strip() or None,
        department_lead_user_id=lead_user_id,
        status=DepartmentStatus.active,
    )
    db.add(department)
    db.flush()
    if lead is not None:
        # The lead is automatically a lead-role member of their department.
        db.add(DepartmentMembership(
            department_id=department.id, user_id=lead.id, membership_role=MembershipRole.lead,
        ))
    audit_service.record_audit_event(
        db,
        action="department.created",
        resource_type="department",
        resource_id=department.id,
        actor=actor,
        request_id=request_id,
        change_summary=f"Created department '{department.name}'",
        metadata={"lead_user_id": str(lead_user_id) if lead_user_id else None},
    )
    return department


UNSET = object()
"""Sentinel: distinguishes "field not sent" from "field explicitly cleared"."""


def update_department(
    db: Session,
    *,
    actor: User | None,
    department: Department,
    name: str | None = None,
    description: str | None = None,
    status: DepartmentStatus | None = None,
    lead_user_id: uuid.UUID | None | object = UNSET,
    request_id: str | None = None,
) -> Department:
    changes: dict[str, dict] = {}
    if name is not None and name.strip() != department.name:
        existing = get_by_name(db, name)
        if existing is not None and existing.id != department.id:
            raise DepartmentError("A department with this name already exists.", code="name_taken")
        changes["name"] = {"from": department.name, "to": name.strip()}
        department.name = name.strip()
    if description is not None and description.strip() != (department.description or ""):
        changes["description"] = {"from": department.description, "to": description.strip() or None}
        department.description = description.strip() or None
    if status is not None and _enum_value(status) != _enum_value(department.status):
        changes["status"] = {"from": _enum_value(department.status), "to": _enum_value(status)}
        department.status = status
    if lead_user_id is not UNSET:
        if lead_user_id != department.department_lead_user_id:
            if lead_user_id is not None and db.get(User, lead_user_id) is None:
                raise DepartmentError("The selected department lead does not exist.", code="lead_not_found")
            changes["lead"] = {
                "from": str(department.department_lead_user_id) if department.department_lead_user_id else None,
                "to": str(lead_user_id) if lead_user_id else None,
            }
            department.department_lead_user_id = lead_user_id

    if changes:
        audit_service.record_audit_event(
            db,
            action="department.updated",
            resource_type="department",
            resource_id=department.id,
            actor=actor,
            request_id=request_id,
            change_summary=", ".join(f"{k} changed" for k in changes),
            metadata={"changes": changes},
        )
    return department


def add_member(
    db: Session,
    *,
    actor: User | None,
    department: Department,
    user: User,
    membership_role: MembershipRole = MembershipRole.member,
    valid_from=None,
    valid_until=None,
    request_id: str | None = None,
) -> DepartmentMembership:
    """Assign an employee to a department (supports multiple memberships if approved)."""
    existing = db.scalar(
        select(DepartmentMembership).where(
            DepartmentMembership.department_id == department.id,
            DepartmentMembership.user_id == user.id,
        )
    )
    if existing is not None:
        raise DepartmentError("This employee is already a member of the department.", code="already_member")

    membership = DepartmentMembership(
        department_id=department.id,
        user_id=user.id,
        membership_role=membership_role,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.add(membership)
    db.flush()
    audit_service.record_audit_event(
        db,
        action="department.member_added",
        resource_type="department",
        resource_id=department.id,
        actor=actor,
        request_id=request_id,
        change_summary=f"Added {user.full_name} to '{department.name}' as {membership_role.value}",
        metadata={"user_id": str(user.id), "membership_role": membership_role.value},
    )
    return membership


def remove_member(
    db: Session,
    *,
    actor: User | None,
    department: Department,
    user_id: uuid.UUID,
    request_id: str | None = None,
) -> None:
    membership = db.scalar(
        select(DepartmentMembership).where(
            DepartmentMembership.department_id == department.id,
            DepartmentMembership.user_id == user_id,
        )
    )
    if membership is None:
        return
    removed_user = db.get(User, user_id)
    db.delete(membership)
    db.flush()
    audit_service.record_audit_event(
        db,
        action="department.member_removed",
        resource_type="department",
        resource_id=department.id,
        actor=actor,
        request_id=request_id,
        change_summary=(
            f"Removed {removed_user.full_name if removed_user else user_id} from '{department.name}'"
        ),
        metadata={"user_id": str(user_id)},
    )


def list_members(db: Session, department: Department) -> list[DepartmentMembership]:
    return list(department.memberships)
