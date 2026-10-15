"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import auth, departments, health, rbac, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(departments.router)
api_router.include_router(rbac.router)
