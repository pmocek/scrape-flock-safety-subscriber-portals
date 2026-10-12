#!/usr/bin/env python3
"""Export portal health-check results as JSON for the companion website.

Reads the per-agency append-only logs at data/{slug}/health.jsonl and writes
website/data/health.json.

Each record is {"ts": ISO8601, "status": "ok"|"blocked"|"error", "detail": str}.
Only the latest record per agency drives the current status; the full history is
summarized into per-agency daily counts so the dashboard can show trends without
shipping every timestamp.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = PROJECT_DIR / "website" / "data" / "health.json"


def load_health_history():
    """Return {slug: [record, ...]} for every agency with health data."""
    history = {}
    for slug_dir in sorted(DATA_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        health_file = slug_dir / "health.jsonl"
        if not health_file.exists():
            continue
        records = []
        for line in health_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "status" in rec and "ts" in rec:
                records.append(rec)
        if records:
            history[slug_dir.name] = records
    return history


def build_health_export(history):
    agencies = []
    status_totals = Counter()
    daily_totals = defaultdict(Counter)
    latest_ts = ""
    oldest_ts = ""

    for slug in sorted(history):
        records = sorted(history[slug], key=lambda r: r["ts"])
        latest = records[-1]
        status_totals[latest["status"]] += 1

        # Per-day status counts, for the trend chart.
        per_day = defaultdict(Counter)
        for rec in records:
            per_day[rec["ts"][:10]][rec["status"]] += 1

        series = []
        for day in sorted(per_day):
            counts = per_day[day]
            total = sum(counts.values())
            series.append({
                "date": day,
                "checks": total,
                "ok": counts.get("ok", 0),
                "error": counts.get("error", 0),
                "blocked": counts.get("blocked", 0),
            })
            for status, n in counts.items():
                daily_totals[day][status] += n

        agencies.append({
            "slug": slug,
            "status": latest["status"],
            "detail": latest.get("detail", ""),
            "last_checked": latest["ts"],
            "checks_recorded": len(records),
            "series": series,
        })

        if latest["ts"] > latest_ts:
            latest_ts = latest["ts"]
        if records[0]["ts"] < oldest_ts or not oldest_ts:
            oldest_ts = records[0]["ts"]

    daily = []
    for day in sorted(daily_totals):
        counts = daily_totals[day]
        daily.append({
            "date": day,
            "checks": sum(counts.values()),
            "ok": counts.get("ok", 0),
            "error": counts.get("error", 0),
            "blocked": counts.get("blocked", 0),
        })

    # Agencies in the scrape inventory that have never been health-checked.
    unchecked = sorted(
        d.name
        for d in DATA_DIR.iterdir()
        if d.is_dir() and (d / "stats.jsonl").exists() and d.name not in history
    )

    return {
        "agencies_monitored": len(agencies),
        "agencies_in_inventory": len(agencies) + len(unchecked),
        "agencies_unchecked": len(unchecked),
        "ok": status_totals.get("ok", 0),
        "blocked": status_totals.get("blocked", 0),
        "error": status_totals.get("error", 0),
        "first_check": oldest_ts,
        "last_check": latest_ts,
        "daily": daily,
        "agencies": agencies,
        "_note": (
            "Coverage is partial: the health check runs hourly but only against a "
            "fixed agency subset, so agencies_monitored is far below "
            "agencies_in_inventory. See agencies_unchecked."
        ),
    }


def main():
    history = load_health_history()
    if not history:
        print(f"No health.jsonl data found under {DATA_DIR}")
        return

    result = build_health_export(history)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Health data → {OUTPUT_FILE}")
    print(f"  Monitored: {result['agencies_monitored']} of {result['agencies_in_inventory']} agencies")
    print(f"  Status:    {result['ok']} ok, {result['error']} error, {result['blocked']} blocked")
    print(f"  Window:    {result['first_check']} → {result['last_check']}")
    print(f"  Days:      {len(result['daily'])}")


if __name__ == "__main__":
    main()
