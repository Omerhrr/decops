"""Phase 9 performance benchmark: latency + SQL query counts on hot paths.

Seeds a realistic sandbox dataset (24 users, 4 departments, 300 tasks with
mixed visibility) into a temp SQLite DB, then measures wall time and SQL
statement counts for the endpoints the UI hits most, plus CSV import
validation at 1000 rows.

Run: cd backend && uv run python ../scripts/bench_phase9.py
Output: scripts/phase9_bench.json + stdout table.
"""

import json
import statistics
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/z/my-project/backend")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.domain.task_lifecycle import TaskStatus  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    Department,
    DepartmentMembership,
    Role,
    Task,
    TaskAssignment,
    TaskDepartment,
    User,
    UserRole,
)
from app.seeds.seed import seed_admin, seed_permissions_and_roles  # noqa: E402

N_USERS = 24
N_TASKS = 300
ITERATIONS = 12


def build_db(tmp: Path):
    engine = create_engine(
        f"sqlite:///{tmp}/bench.db",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # Bind create_all to the ENGINE (it manages its own transaction). Sharing
    # one Connection across create_all + seed data leaves the seed in an open
    # transaction that is rolled back when the connection closes.
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    seed_permissions_and_roles(db)
    seed_admin(db)
    db.commit()

    admin = db.scalar(select(User).where(User.email == "admin@interdec.com"))
    roles = {r.name: r for r in db.scalars(select(Role)).all()}

    users = []
    for i in range(N_USERS):
        user = User(
            employee_code=f"INT-B{i:03d}",
            full_name=f"Bench User {i}",
            email=f"bench{i}@interdec.com",
            authentication_reference=hash_password("Secret!1234"),
            account_status="active",
        )
        db.add(user)
        db.flush()
        role = roles["Accountable PM"] if i % 2 else roles["Department Member"]
        db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global"))
        users.append(user)

    # Benchmark actor: Management role (dashboards.view + reports.view per the
    # spec matrix; the System Administrator deliberately lacks reports.view).
    manager = User(
        employee_code="INT-BMGR",
        full_name="Bench Manager",
        email="manager@interdec.com",
        authentication_reference=hash_password("Secret!1234"),
        account_status="active",
    )
    db.add(manager)
    db.flush()
    db.add(UserRole(user_id=manager.id, role_id=roles["Management"].id, scope_type="global"))
    # Also Company Administration so the import pipeline can be benchmarked.
    db.add(UserRole(user_id=manager.id, role_id=roles["Company Administrator"].id,
                    scope_type="global"))
    users.append(manager)

    departments = []
    for d in range(4):
        dep = Department(name=f"Bench Dept {d}", description="perf", status="active")
        db.add(dep)
        db.flush()
        departments.append(dep)
        for u in users[d * 6:(d + 1) * 6]:
            db.add(DepartmentMembership(department_id=dep.id, user_id=u.id,
                                        membership_role="member"))

    statuses = [TaskStatus.open, TaskStatus.in_progress, TaskStatus.completed,
                TaskStatus.blocked, TaskStatus.under_review]
    today = date.today()
    for i in range(N_TASKS):
        pm = users[i % N_USERS]
        task = Task(
            task_number=f"TSK-2026-{i + 100:04d}",
            title=f"Bench task {i} - inspect subsystem {i % 17}",
            description="benchmark payload",
            priority=["low", "medium", "high", "critical"][i % 4],
            status=statuses[i % len(statuses)],
            accountable_pm_id=pm.id,
            created_by_id=admin.id,
            start_date=today - timedelta(days=i % 40),
            due_date=today + timedelta(days=(i % 30) - 10),
            visibility_mode=["participants", "department_scoped", "private"][i % 3],
            percent_complete=i % 101,
        )
        db.add(task)
        db.flush()
        db.add(TaskAssignment(task_id=task.id, user_id=pm.id,
                              assignment_role="accountable_pm", assigned_by_id=admin.id))
    db.commit()

    # Link department_scoped tasks to departments so those are visible
    tasks = db.scalars(select(Task)).all()
    for i, task in enumerate(tasks):
        if task.visibility_mode == "department_scoped":
            db.add(TaskDepartment(task_id=task.id, department_id=departments[i % 4].id))
    db.commit()
    db.close()
    engine.dispose()
    return engine


def main() -> None:
    tmp = Path("/tmp/phase9_bench")
    tmp.mkdir(exist_ok=True)
    (tmp / "bench.db").unlink(missing_ok=True)  # fresh dataset per run
    engine = build_db(tmp)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    settings = Settings(environment="testing", database_url="sqlite://",
                        import_storage_dir=tmp / "imports")
    app = create_app(override_settings=settings)

    query_counts: dict[str, int] = {}

    @event.listens_for(engine, "before_cursor_execute")
    def count_queries(conn, cursor, statement, parameters, context, executemany):
        query_counts["_count"] = query_counts.get("_count", 0) + 1

    def override_get_db():
        db = TestingSession()
        yield db
        db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # login as the Management actor (reports + dashboards per spec matrix)
        r = client.post("/api/v1/auth/login", json={
            "email": "manager@interdec.com", "password": "Secret!1234"})
        assert r.status_code == 200, r.text

        endpoints = [
            ("GET", "/api/v1/tasks?page=1&page_size=25", "task register (25/page)"),
            ("GET", "/api/v1/tasks?page=1&page_size=100", "task register (100/page)"),
            ("GET", "/api/v1/dashboard/summary", "personal dashboard"),
            ("GET", "/api/v1/dashboard/my-tasks", "my tasks"),
            ("GET", "/api/v1/reports/task-completion", "completion report"),
            ("GET", "/api/v1/reports/department-workload", "workload report"),
        ]

        results = []
        for method, path, label in endpoints:
            r = client.request(method, path)  # warmup
            assert r.status_code == 200, (path, r.status_code, r.text[:200])
            times = []
            for _ in range(ITERATIONS):
                query_counts["_count"] = 0
                t0 = time.perf_counter()
                r = client.request(method, path)
                elapsed = (time.perf_counter() - t0) * 1000
                assert r.status_code == 200, path
                times.append(elapsed)
            queries = query_counts["_count"]
            results.append({
                "endpoint": path,
                "label": label,
                "p50_ms": round(statistics.median(times), 1),
                "p95_ms": round(sorted(times)[int(0.95 * len(times)) - 1], 1),
                "mean_ms": round(statistics.mean(times), 1),
                "sql_queries": queries,
            })

        # CSV import validation at 1000 rows
        header = ("Task ID,Date Created,Task Title,Task Description,Priority,"
                  "Accountable PM,Supporting PM(s),Assigned By,Start Date,Due Date,"
                  "Status,% Complete,Last Updated,Next Follow-up Date,"
                  "Dependency / Blocker,Attachment / Folder Link,Completion Date")
        rows = []
        for i in range(1000):
            rows.append(
                f"LEG-B{i:05d},01/02/2025,Bench import task {i},payload,High,"
                f"manager@interdec.com,,,05/02/2025,15/03/2025,In Progress,"
                f"{i % 101},,,,Waiting on part,,"
            )
        csv_bytes = (header + "\n" + "\n".join(rows) + "\n").encode()
        r = client.post("/api/v1/imports/csv",
                        files={"file": ("bench-1000.csv", csv_bytes, "text/csv")})
        assert r.status_code == 201, r.text[:300]
        times = []
        for _ in range(3):
            query_counts["_count"] = 0
            t0 = time.perf_counter()
            client.post("/api/v1/imports/csv",
                        files={"file": ("bench-1000.csv", csv_bytes, "text/csv")})
            times.append((time.perf_counter() - t0) * 1000)
        import_result = {
            "endpoint": "POST /api/v1/imports/csv",
            "label": "CSV validation (1000 rows)",
            "p50_ms": round(statistics.median(times), 1),
            "sql_queries": query_counts["_count"],
            "note": "re-upload duplicates every row (worst case: full report)",
        }

    out = {"dataset": {"users": N_USERS, "tasks": N_TASKS},
           "endpoints": results, "import_1000_rows": import_result,
           "generated_at": datetime.now(UTC).isoformat()}
    Path("/home/z/my-project/scripts/phase9_bench.json").write_text(json.dumps(out, indent=1))
    print(f"{'endpoint':<44}{'p50 ms':>9}{'p95 ms':>9}{'mean ms':>9}{'SQL':>6}")
    for row in results:
        print(f"{row['label']:<44}{row['p50_ms']:>9}{row['p95_ms']:>9}"
              f"{row['mean_ms']:>9}{row['sql_queries']:>6}")
    print(f"{import_result['label']:<44}{import_result['p50_ms']:>9}{'-':>9}"
          f"{'-':>9}{import_result['sql_queries']:>6}")


if __name__ == "__main__":
    main()
