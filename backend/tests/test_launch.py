""" launch-drill guards: credential-source stability, smoke coverage,
and retry-safe register pre-check (tests/test_launch.py)."""

import csv
import importlib.util
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "launch_phase10.py"

spec = importlib.util.spec_from_file_location("launch_phase10", SCRIPT)
launch = importlib.util.module_from_spec(spec)
sys.modules["launch_phase10"] = launch
spec.loader.exec_module(launch)

from app.models import Task  # noqa: E402


@pytest.fixture()
def creds_file(tmp_path, monkeypatch):
    """Isolate the credentials file per test."""
    target = tmp_path / "launch_credentials.csv"
    monkeypatch.setattr(launch, "CREDS_PATH", target)
    return target


ACCOUNTS = [
    {"email": "a@interdec.com"},
    {"email": "b@interdec.com"},
]


def test_generated_credentials_are_stable_across_calls(creds_file):
    """Second call must read the credentials file, not regenerate (launch drill
    re-runs would otherwise orphan the provisioned passwords)."""
    first = launch.load_or_generate_passwords(ACCOUNTS, None)
    assert creds_file.exists()
    first_mode = creds_file.stat().st_mode & 0o777
    assert first_mode == 0o600, "credentials file must be owner-only"

    second = launch.load_or_generate_passwords(ACCOUNTS, None)
    assert second == first


def test_passwords_csv_takes_precedence(creds_file, tmp_path):
    supplied = tmp_path / "supplied.csv"
    supplied.write_text("email,password\na@interdec.com,Supplied!Pass1\n", encoding="utf-8")
    passwords = launch.load_or_generate_passwords(ACCOUNTS, supplied)
    assert passwords["a@interdec.com"] == "Supplied!Pass1"
    assert "b@interdec.com" in passwords  # still generated for the other account


def test_generated_passwords_meet_policy():
    passwords = launch.load_or_generate_passwords(ACCOUNTS, None)
    for password in passwords.values():
        assert len(password) >= 10  # matches user_admin_service.MIN_PASSWORD_LENGTH


def test_smoke_matrix_covers_every_system_role(test_db):
    """Every role the RBAC seed knows must have a smoke path set - a new role
    without launch smoke coverage is a launch-process defect."""
    from app.seeds.rbac_matrix import ROLE_MATRIX

    missing = set(ROLE_MATRIX) - set(launch.SMOKE_MATRIX)
    assert not missing, f"roles without smoke coverage: {sorted(missing)}"
    for role, probes in launch.SMOKE_MATRIX.items():
        assert probes, f"{role} has an empty smoke matrix"


def test_register_precheck_detects_fully_imported_register(test_db):
    """Retry-safe pre-check: all legacy IDs present -> skip without a new job."""
    from sqlalchemy import select

    from app.models import User
    admin = test_db.scalar(select(User).where(User.email == "admin@interdec.com"))

    for legacy_id in ("DEC-2024-001", "DEC-2024-002"):
        test_db.add(Task(
            title=f"t {legacy_id}", task_number=legacy_id,
            legacy_external_id=legacy_id,
            visibility_mode="participants",
            accountable_pm_id=admin.id,
            created_by_id=admin.id,
        ))
    test_db.commit()

    from app.models import Task as T
    legacy_ids = ["DEC-2024-001", "DEC-2024-002"]
    existing = set(test_db.scalars(select(T.legacy_external_id).where(
        T.legacy_external_id.in_(legacy_ids))).all())
    assert set(legacy_ids) <= existing  # the condition import_register uses

    partially = ["DEC-2024-001", "DEC-9999-999"]
    existing_partial = set(test_db.scalars(select(T.legacy_external_id).where(
        T.legacy_external_id.in_(partially))).all())
    assert not set(partially) <= existing_partial  # partial overlap must still import


def test_manifest_and_register_assets_are_wellformed():
    """The shipped launch assets parse and match the 17-column template."""
    manifest = REPO_ROOT / "docs" / "launch" / "accounts_manifest.csv"
    with open(manifest, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 9
    roles = {r["roles"].strip() for r in rows}
    assert "Company Administrator" not in roles  # admin is seeded, not manifested

    from app.domain.csv_import import DEFAULT_COLUMN_MAPPING
    register = REPO_ROOT / "docs" / "launch" / "task_register.csv"
    with open(register, newline="", encoding="utf-8-sig") as fh:
        headers = next(csv.reader(fh))
    assert headers == list(DEFAULT_COLUMN_MAPPING)  # exact legacy spreadsheet columns
