#!/usr/bin/env python3
"""Generate a semantic commit message from staged data changes.

Reads `git diff --cached` and describes what changed in each agency's
stats.jsonl (comparing last two snapshots). Intended for git-scraping
workflows where data files are the primary commit content.
"""

import json
import subprocess
import sys


FIELD_LABELS = {
    "vehicles_30d": "vehicles",
    "total_cameras": "cameras",
    "hotlist_hits_30d": "hotlist_hits",
    "searches_30d": "searches",
    "retention_days": "retention",
    "external_agencies_count": "ext_agencies",
}


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def get_changed_files():
    """Return list of (status, path) from --cached diff."""
    out = git("diff", "--cached", "--name-status")
    if not out:
        return []
    files = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            files.append((parts[0], parts[1]))
    return files


def get_head_file(path):
    """Return the full committed version of a file, or None if new."""
    out = git("show", f"HEAD:{path}")
    if out is None:
        # Check if it was a directory in HEAD (old date hierarchy)
        return None
    return out


def last_jsonl_line(content):
    """Parse the last JSON line from a JSONL string. Returns dict or None."""
    lines = content.strip().split("\n")
    if not lines:
        return None
    for line in reversed(lines):
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def describe_change(prev, curr):
    """Compare two stats dicts, return a short human string."""
    parts = []
    for key, label in FIELD_LABELS.items():
        p = prev.get(key)
        c = curr.get(key)
        if p == c:
            continue
        if p is None:
            parts.append(f"{label}={c}")
        elif c is None:
            parts.append(f"{label} removed")
        else:
            diff = c - p
            arrow = "▲" if diff > 0 else "▼"
            parts.append(f"{label} {arrow}{abs(diff)}")
    if not parts:
        return None
    return ", ".join(parts)


def main():
    files = get_changed_files()
    if not files:
        print("data: no changes")
        return 0

    data_changes = []  # (slug, description)
    deleted_old = []
    has_non_data = False

    for status, path in files:
        # Track old date-based dirs being cleaned up
        if status == "D" and path.startswith("data/") and not path.startswith("data/20"):
            pass  # some other deletion
        if path.startswith("data/") and len(path.split("/")) == 2:
            # data/YYYY-MM-DD/ directory marker — skip
            continue

        # Only care about stats.jsonl changes
        if not (path.startswith("data/") and path.endswith("/stats.jsonl")):
            if not path.startswith("data/"):
                has_non_data = True
            continue

        parts = path.split("/")
        slug = parts[1]

        head_content = get_head_file(path)
        with open(path) as f:
            staged_content = f.read()

        prev = last_jsonl_line(head_content) if head_content else None
        curr = last_jsonl_line(staged_content)

        if prev is None and curr:
            if "error" in curr:
                data_changes.append((slug, f"blocked ({curr['error']})"))
            elif head_content is None:
                data_changes.append((slug, "new"))
            else:
                data_changes.append((slug, "first snapshot"))
        elif prev and curr:
            prev_err = "error" in prev
            curr_err = "error" in curr
            if prev_err and curr_err:
                data_changes.append((slug, "still blocked"))
            elif prev_err:
                data_changes.append((slug, "recovered"))
            elif curr_err:
                data_changes.append((slug, f"blocked ({curr['error']})"))
            else:
                desc = describe_change(prev, curr)
                if desc:
                    data_changes.append((slug, desc))
                else:
                    data_changes.append((slug, "no change"))

    # Detect old date directory deletions
    old_dirs = set()
    for status, path in files:
        if status == "D" and path.startswith("data/20"):
            old_dirs.add(path.split("/")[1])
    old_dir_count = len(old_dirs)

    # Build the commit message
    body_lines = []

    if data_changes:
        changed = [s for s, d in data_changes if d and d != "no change"]
        unchanged = [s for s, d in data_changes if d == "no change"]
        new = [s for s, d in data_changes if d == "new" or d == "first snapshot"]

        n_changed = len(changed)
        n_new = len(new)
        n_total = len(data_changes)

        parts = []
        if n_changed:
            parts.append(f"{n_changed} with changes")
        if n_new:
            parts.append(f"{n_new} new")
        n_unchanged = len(unchanged)
        if n_unchanged:
            parts.append(f"{n_unchanged} unchanged")

        subject = f"data: update {n_total} agencies ({', '.join(parts)})"
        print(subject)

        # Body: per-agency details for those with changes
        if changed:
            body_lines.append("")
            body_lines.append("Changes:")
            for slug, desc in changed:
                body_lines.append(f"  {slug}: {desc}")
        if new:
            if not body_lines:
                body_lines.append("")
            body_lines.append("")
            body_lines.append("New:")
            for slug, desc in new:
                body_lines.append(f"  {slug}")

    if old_dir_count:
        if body_lines:
            body_lines.append("")
        body_lines.append(f"Cleanup: removed {old_dir_count} old date-based directories")

    if has_non_data and not data_changes:
        print("chore: update source files")

    if body_lines:
        print()
        print("\n".join(body_lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
