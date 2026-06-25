#!/usr/bin/env python3
"""Quick HTTP health check for each agency portal.

Fast: uses urllib, no browser. Cloudflare is expected and recorded
as 'blocked'.  Catches site-down events, DNS failures, or changes
in the Cloudflare response that might signal a redesign.

Saves to data/{slug}/health.jsonl (append-only).
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"
HAVEIBEENFLOCKED_URL = "https://haveibeenflocked.com/news/transparency-portals/"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

WA_SLUGS = [
    "arlington-pd-wa", "bonney-lake-wa-pd", "centralia-pd-wa",
    "college-place-wa-pd", "des-moines-wa-pd", "eatonville-wa-pd",
    "edmonds-wa-pd", "ellensburg-wa-pd", "everett-wa-pd", "kent-wa-pd",
    "lake-stevens-wa-pd", "lakewood-wa-pd", "lynnwood-wa-pd",
    "marysville-wa-pd", "medina-wa-pd", "mill-creek-wa-pd",
    "monroe-wa-pd", "moses-lake-wa-pd", "mount-vernon-wa-pd",
    "newcastle-wa-pd", "olympia-wa-pd-", "prosser-wa-pd",
    "puyallup-wa-pd", "renton-wa-pd", "richland-pd-wa", "seatac-wa-pd",
    "selah-wa-pd", "shelton-pd-wa", "skamania-co-wa-so",
    "snohomish-county-wa-so-", "-spokane-county-wa-so",
    "stanwood-wa-pd", "sumner-wa-pd", "toppenish-wa-pd",
    "tukwila-wa-pd", "walla-walla-wa-pd", "yakima-wa-pd", "yelm-wa-pd",
]


def check_slug(slug):
    """Returns {'status': ..., 'detail': ...}."""
    url = f"https://transparency.flocksafety.com/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            if "Just a moment" in body or "Checking your browser" in body:
                return {"status": "blocked", "detail": "cloudflare"}
            if resp.status >= 400:
                return {"status": "error", "detail": f"http_{resp.status}"}
            return {"status": "ok", "detail": f"http_{resp.status}"}
    except urllib.error.HTTPError as e:
        return {"status": "error", "detail": f"http_{e.code}"}
    except urllib.error.URLError as e:
        return {"status": "error", "detail": str(e.reason)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def main():
    if AGENCIES_FILE.exists():
        with open(AGENCIES_FILE) as f:
            slugs = json.load(f)
    else:
        slugs = WA_SLUGS

    ts = datetime.now(timezone.utc).isoformat()
    counts = {"ok": 0, "blocked": 0, "error": 0}

    for i, slug in enumerate(slugs):
        print(f"[{i+1}/{len(slugs)}] {slug} ...", end=" ", flush=True)
        result = check_slug(slug)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(result["status"])

        slug_dir = DATA_DIR / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": ts, **result})
        with open(slug_dir / "health.jsonl", "a") as f:
            f.write(line + "\n")

    total = sum(counts.values())
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"\n  {total} checked ({summary})")

    # Emit a commit-message line the workflow can capture
    print(f"COMMIT_MSG: health: {total} checked ({summary})", flush=True)

    if counts.get("error", 0) > len(slugs) // 2:
        print("FATAL: >50% of agencies unreachable")
        sys.exit(1)


if __name__ == "__main__":
    main()
