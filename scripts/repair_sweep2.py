"""Second repair pass: the amber/sky/rose/emerald tint patterns had the same
overlapping-substring corruption as the brand pattern. Restore bg-*-500 and
clean doubled dark: variants."""

import pathlib
import re

ROOT = pathlib.Path("/home/z/my-project/app")

for color in ("amber", "sky", "rose", "emerald"):
    pairs = [
        (f"bg-{color}-50 dark:bg-{color}-500/100/35", f"bg-{color}-500/35"),
        (f"bg-{color}-50 dark:bg-{color}-500/100/40", f"bg-{color}-500/40"),
        (f"bg-{color}-50 dark:bg-{color}-500/100/5", f"bg-{color}-500/5"),
        (f"bg-{color}-50 dark:bg-{color}-500/100", f"bg-{color}-500"),
        (f"dark:bg-{color}-50 dark:bg-{color}-500/100/10", f"dark:bg-{color}-500/10"),
        (f"dark:bg-{color}-500/100/10", f"dark:bg-{color}-500/10"),
        (f"dark:bg-{color}-500/100/15", f"dark:bg-{color}-500/15"),
        (f"dark:bg-{color}-500/100/5", f"dark:bg-{color}-500/5"),
        (f"dark:bg-{color}-500/100/40", f"dark:bg-{color}-500/40"),
        (f"dark:bg-{color}-500/100/35", f"dark:bg-{color}-500/35"),
        (f"dark:bg-{color}-500/100", f"dark:bg-{color}-500"),
    ]
    for path in sorted(ROOT.rglob("*.vue")):
        text = path.read_text()
        original = text
        for old, new in pairs:
            text = text.replace(old, new)
        text = re.sub(r"\b(dark:[\w/.:-]+)(\s+\1)+\b", r"\1", text)
        if text != original:
            path.write_text(text)
            print("repaired", path.relative_to(ROOT), f"({color})")

print("done")
