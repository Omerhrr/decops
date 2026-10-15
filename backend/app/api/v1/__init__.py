"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import auth, collaboration, departments, health, notifications, rbac, tasks, users, workflow

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(departments.router)
api_router.include_router(rbac.router)
api_router.include_router(tasks.router)
api_router.include_router(workflow.router)
api_router.include_router(workflow.templates_router)
api_router.include_router(collaboration.router)
api_router.include_router(notifications.router)
