"""Health and system checks."""

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["System"])

APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
def health(db: DbSession) -> HealthResponse:
    db_state = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_state = "unavailable"
    return HealthResponse(
        status="ok" if db_state == "ok" else "degraded",
        environment=settings.environment,
        version=APP_VERSION,
        database=db_state,
    )
