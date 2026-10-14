"""RBAC seed data: role matrix from the spec (roles_and_permissions.roles)."""

ROLE_MATRIX: dict[str, dict] = {
    "System Administrator": {
        "description": "Maintains application infrastructure and system configuration.",
        "permissions": [
            "system.config.manage",
            "system.health.inspect",
            "system.settings.manage",
            "audit.security.read",
        ],
    },
    "Company Administrator": {
        "description": "Manages Interdec users, departments, roles, and approved operational settings.",
        "permissions": [
            "users.manage",
            "departments.manage",
            "roles.assign",
            "workflows.configure",
            "settings.org.manage",
        ],
    },
    "Management": {
        "description": "Oversees organizational work and authorized management reporting.",
        "permissions": [
            "dashboards.view",
            "reports.view",
            "tasks.view_authorized",
            "tasks.approve",
        ],
    },
    "Accountable PM": {
        "description": "Owns the outcome of an assigned task.",
        "permissions": [
            "tasks.update_assigned",
            "milestones.manage",
            "progress.update",
            "blockers.report",
            "review.request",
        ],
    },
    "Supporting PM": {
        "description": "Contributes to a task under the accountable PM.",
        "permissions": [
            "tasks.update_assigned",
            "milestones.manage",
            "blockers.report",
            "comments.create",
        ],
    },
    "Department Lead": {
        "description": "Coordinates work for a department.",
        "permissions": [
            "tasks.view_department",
            "workload.view",
            "tasks.assign_department",
            "blockers.escalate",
            "reports.department.view",
        ],
    },
    "Department Member": {
        "description": "Performs assigned operational work.",
        "permissions": [
            "tasks.view_authorized",
            "work_items.update_assigned",
            "comments.create",
            "blockers.report",
            "attachments.upload",
        ],
    },
    "Approver": {
        "description": "Reviews tasks or milestones requiring formal approval.",
        "permissions": [
            "review.view_submitted",
            "review.approve",
            "review.reject",
            "review.request_changes",
        ],
    },
    "Read-Only Auditor": {
        "description": "Reviews authorized records and audit trails.",
        "permissions": [
            "tasks.view_authorized",
            "audit.read",
            "exports.approved",
        ],
    },
}

# Permissions granted by any authenticated, active account (baseline identity)
AUTHENTICATED_PERMISSIONS = ["profile.read", "profile.update"]
