"""Repair pass for the dark sweep: restore classes corrupted by overlapping
substring matches (bg-brand-500 was hit by the bg-brand-50 pattern), and
convert wrongly scoped dark: variants to the hover: equivalent."""

import pathlib

ROOT = pathlib.Path("/home/z/my-project/app")

ORDERED = [
    # bg-brand-500 corruptions (the bg-brand-50 pattern ate the trailing digit)
    ("bg-brand-50 dark:bg-brand-500/100/35", "bg-brand-500/35"),
    ("bg-brand-50 dark:bg-brand-500/100/40", "bg-brand-500/40"),
    ("bg-brand-50 dark:bg-brand-500/100/5", "bg-brand-500/5"),
    ("bg-brand-50 dark:bg-brand-500/100", "bg-brand-500"),
    ("dark:bg-brand-50 dark:bg-brand-500/100/10", "dark:bg-brand-500/10"),
    ("dark:bg-brand-500/100/10", "dark:bg-brand-500/10"),
    ("dark:bg-brand-500/100/15", "dark:bg-brand-500/15"),
    # wrongly scoped dark variants on hover: utilities
    ("hover:text-brand-700 dark:text-brand-300", "hover:text-brand-700 dark:hover:text-brand-300"),
    ("hover:text-brand-600 dark:text-brand-400", "hover:text-brand-600 dark:hover:text-brand-400"),
    ("hover:bg-brand-100 dark:bg-brand-500/15", "hover:bg-brand-100 dark:hover:bg-brand-500/15"),
    ("hover:bg-brand-50 dark:bg-brand-500/10", "hover:bg-brand-50 dark:hover:bg-brand-500/10"),
    # AppBadge green entry got doubled variants; restore a clean form
    (
        "bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 "
        "dark:bg-brand-50 dark:bg-brand-500/10 dark:text-brand-300",
        "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300",
    ),
]

changed = 0
for path in sorted(ROOT.rglob("*.vue")):
    text = path.read_text()
    original = text
    for old, new in ORDERED:
        text = text.replace(old, new)
    # collapse any duplicated identical dark: tokens produced by stacking
    while True:
        deduped = path  # placeholder to keep loop shape clear
        import re
        new_text = re.sub(r"\b(dark:[\w/.:-]+)(\s+\1)+\b", r"\1", text)
        if new_text == text:
            break
        text = new_text
    if text != original:
        path.write_text(text)
        changed += 1
        print("repaired", path.relative_to(ROOT))

print(f"repaired {changed} files")
