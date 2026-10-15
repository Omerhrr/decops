"""Autogenerate the Phase 5 migration against an empty temp DB."""
import os, subprocess, sys

# Point settings at a fresh temp DB so autogenerate sees only the models.
os.environ["DECOPS_DATABASE_URL"] = "sqlite:///./migration_tmp.db"
for f in ("decops.db", "migration_tmp.db"):
    if os.path.exists(f):
        os.remove(f)
print("env prepared")
