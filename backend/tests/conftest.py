"""Test fixtures: isolated in-memory database + FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models import User, UserRole
from app.seeds.seed import seed_admin, seed_permissions_and_roles


@pytest.fixture()
def test_db():
    """Fresh in-memory SQLite per test with FK enforcement."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    conn = engine.connect()
    conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(bind=conn)
    db = TestingSession(bind=conn)

    seed_permissions_and_roles(db)
    seed_admin(db)
    db.commit()
    yield db
    db.close()
    conn.close()
    engine.dispose()


@pytest.fixture()
def client(test_db):
    """TestClient wired to the isolated database and hardened test settings."""
    settings = Settings(
        environment="testing",
        debug=False,
        database_url="sqlite://",
        session_lifetime_minutes=60,
        max_failed_logins=5,
    )
    app = create_app(override_settings=settings)

    from app.api.deps import get_db

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


def make_user(
    db,
    *,
    email: str,
    password: str = "Secret!1234",
    employee_code: str | None = None,
    role_names: list[str] | None = None,
    status: str = "active",
):
    # Derive a unique code from the full local part (5-char prefixes collided
    # for emails like email1@ / emails1@).
    resolved_code = employee_code or f"INT-{email.split('@')[0].upper()[:26]}"
    user = User(
        employee_code=resolved_code,
        full_name=email.split("@")[0].title(),
        email=email,
        authentication_reference=hash_password(password),
        account_status=status,
    )
    db.add(user)
    db.flush()
    from app.models import Role

    for role_name in role_names or ["Department Member"]:
        role = db.query(Role).filter_by(name=role_name).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global"))
    db.commit()
    return user


def login(client: TestClient, email: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
