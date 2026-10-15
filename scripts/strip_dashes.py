#!/usr/bin/env python3
"""Remove every em dash and en dash from the DecOps codebase.

Rules, applied in order:
 1. quoted em-dash placeholders (single/double quoted) become a hyphen
 2. spaced em dash becomes " - "
 3. bare em dash becomes "-"
 4. spaced and bare en dash likewise
 5. interior double spaces are collapsed, but ONLY on lines that contained
    a dash, so Python indentation and aligned code elsewhere stay untouched
"""

import re
from pathlib import Path

ROOT = Path("/home/z/my-project")

TARGETS = [
    "app",
    "backend/app",
    "backend/tests",
    "backend/alembic",
    "backend/pyproject.toml",
    "backend/alembic.ini",
    "docs",
    "scripts",
    "README.md",
    "worklog.md",
    "spec_full.json",
]

EXCLUDE_PARTS = {"node_modules", ".nuxt", ".output", ".venv", "__pycache__", "var"}
EXCLUDE_NAMES = {"bun.lock", "package-lock.json", "dev.log", "dev-front.log"}
EXCLUDE_SUFFIXES = {".png", ".jpg", ".db", ".log", ".pyc"}

PLACEHOLDER = re.compile("(['\"])\\u2014\\1")
EM = "\u2014"
EN = "\u2013"


def clean_line(line: str) -> str:
    line = PLACEHOLDER.sub(r"\1-\1", line)
    line = re.sub(r"[ \t]*\u2014[ \t]*", " - ", line)
    line = re.sub(r"[ \t]*\u2013[ \t]*", " - ", line)
    line = line.replace(EM, "-").replace(EN, "-")
    if " - " in line or line.startswith("- "):
        line = re.sub(r"(?<=\S) {2,}(?=\S)", " ", line)
    line = re.sub(r"[ \t]+$", "", line)
    return line


def clean_text(text: str) -> str:
    return "\n".join(clean_line(ln) for ln in text.split("\n"))


def iter_files():
    for entry in TARGETS:
        path = ROOT / entry
        if path.is_file():
            yield path
        else:
            for p in path.rglob("*"):
                if not p.is_file():
                    continue
                if any(part in EXCLUDE_PARTS for part in p.parts):
                    continue
                if p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIXES:
                    continue
                yield p


total_files = 0
total_hits = 0
for path in sorted(set(iter_files())):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        continue
    if EM not in text and EN not in text:
        continue
    hits = text.count(EM) + text.count(EN)
    path.write_text(clean_text(text), encoding="utf-8")
    total_files += 1
    total_hits += hits
    print(f"{hits:4d}  {path.relative_to(ROOT)}")

print(f"cleaned {total_hits} dashes across {total_files} files")

left = 0
for path in sorted(set(iter_files())):
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        continue
    n = text.count(EM) + text.count(EN)
    if n:
        print(f"REMAINING {n}: {path.relative_to(ROOT)}")
        left += n
print("remaining:", left)
