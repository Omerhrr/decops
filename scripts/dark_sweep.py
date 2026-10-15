"""Dark mode sweep: replace hardcoded slate/white palette classes with the
semantic theme tokens (bg-surface, text-ink, ...) across all Vue files, and
add dark: variants for brand/rose/amber/sky tint fills. Idempotent: tint
patterns are skipped when already followed by their dark: counterpart."""

import pathlib
import re

ROOT = pathlib.Path("/home/z/my-project/app")

# Plain class-for-class swaps (safe to repeat).
SWAPS = [
    ("hover:bg-slate-50", "hover:bg-hover"),
    ("hover:bg-slate-100", "hover:bg-hover"),
    ("hover:text-slate-900", "hover:text-ink"),
    ("hover:text-slate-700", "hover:text-ink"),
    ("hover:text-slate-600", "hover:text-body"),
    ("hover:border-slate-400", "hover:border-faint"),
    ("hover:border-slate-300", "hover:border-line-strong"),
    ("focus:border-slate-300", "focus:border-line-strong"),
    ("bg-white/95", "bg-surface/90"),
    ("bg-white", "bg-surface"),
    ("bg-slate-900/50", "bg-overlay"),
    ("bg-slate-50", "bg-elevated"),
    ("bg-slate-200", "bg-hover"),
    ("bg-slate-100", "bg-hover"),
    ("text-slate-900", "text-ink"),
    ("text-slate-800", "text-ink"),
    ("text-slate-700", "text-body"),
    ("text-slate-600", "text-body"),
    ("text-slate-500", "text-muted"),
    ("text-slate-400", "text-faint"),
    ("text-slate-300", "text-faint"),
    ("text-slate-200", "text-faint"),
    ("border-slate-100", "border-line"),
    ("border-slate-200", "border-line"),
    ("border-slate-300", "border-line-strong"),
    ("divide-slate-100", "divide-line"),
    ("divide-slate-200", "divide-line"),
    ("ring-slate-200", "ring-line"),
]

# (pattern, replacement, follow-up dark variant). Skipped when the dark
# variant already immediately follows, so re-running stays idempotent.
TINTS = [
    (r"bg-brand-50/\d+", None, None),  # handled below via specific entries
    (r"bg-brand-50(?:/\d+)?", "bg-brand-50 dark:bg-brand-500/10", "bg-brand-50 dark:bg-brand-500/10"),
    (r"bg-brand-100(?:/\d+)?", "bg-brand-100 dark:bg-brand-500/15", "bg-brand-100 dark:bg-brand-500/15"),
    (r"text-brand-700", "text-brand-700 dark:text-brand-300", "text-brand-700 dark:text-brand-300"),
    (r"text-brand-600", "text-brand-600 dark:text-brand-400", "text-brand-600 dark:text-brand-400"),
    (r"bg-rose-50(?:/\d+)?", "bg-rose-50 dark:bg-rose-500/10", "bg-rose-50 dark:bg-rose-500/10"),
    (r"bg-rose-100(?:/\d+)?", "bg-rose-100 dark:bg-rose-500/15", "bg-rose-100 dark:bg-rose-500/15"),
    (r"text-rose-700", "text-rose-700 dark:text-rose-300", "text-rose-700 dark:text-rose-300"),
    (r"text-rose-600", "text-rose-600 dark:text-rose-400", "text-rose-600 dark:text-rose-400"),
    (r"border-rose-200", "border-rose-200 dark:border-rose-900/50", "border-rose-200 dark:border-rose-900/50"),
    (r"border-rose-100(?:/\d+)?", "border-rose-100 dark:border-rose-900/50", "border-rose-100 dark:border-rose-900/50"),
    (r"bg-amber-50(?:/\d+)?", "bg-amber-50 dark:bg-amber-500/10", "bg-amber-50 dark:bg-amber-500/10"),
    (r"text-amber-700", "text-amber-700 dark:text-amber-300", "text-amber-700 dark:text-amber-300"),
    (r"text-amber-600", "text-amber-600 dark:text-amber-400", "text-amber-600 dark:text-amber-400"),
    (r"border-amber-200", "border-amber-200 dark:border-amber-900/50", "border-amber-200 dark:border-amber-900/50"),
    (r"bg-sky-50(?:/\d+)?", "bg-sky-50 dark:bg-sky-500/10", "bg-sky-50 dark:bg-sky-500/10"),
    (r"text-sky-700", "text-sky-700 dark:text-sky-300", "text-sky-700 dark:text-sky-300"),
    (r"text-sky-600", "text-sky-600 dark:text-sky-400", "text-sky-600 dark:text-sky-400"),
    (r"border-sky-200", "border-sky-200 dark:border-sky-900/50", "border-sky-200 dark:border-sky-900/50"),
    (r"bg-emerald-50(?:/\d+)?", "bg-emerald-50 dark:bg-emerald-500/10", "bg-emerald-50 dark:bg-emerald-500/10"),
    (r"text-emerald-700", "text-emerald-700 dark:text-emerald-300", "text-emerald-700 dark:text-emerald-300"),
]

changed_files = 0
for path in sorted(ROOT.rglob("*.vue")):
    text = path.read_text()
    original = text
    for old, new in SWAPS:
        text = text.replace(old, new)

    for pattern, replacement, done_marker in TINTS:
        if done_marker and done_marker in text:
            continue

        def _sub(match: re.Match) -> str:
            return replacement

        text = re.sub(pattern, _sub, text)

    # Remove accidental duplicates of identical adjacent dark tokens.
    text = re.sub(
        r"\b(dark:[\w/.:-]+)(?:\s+\1)+\b",
        r"\1",
        text,
    )

    if text != original:
        path.write_text(text)
        changed_files += 1

print(f"updated {changed_files} files")
