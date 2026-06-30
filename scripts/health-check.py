#!/usr/bin/env python3
"""Quick Playwright health check for each agency portal.

Reuses the same browser/context for all slugs in one run.
Cloudflare blocks are detected the same way as the scraper
(HTTP 429, "Just a moment" title, "Error 1015" body text).

Saves to data/{slug}/health.jsonl (append-only).
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"

WA_SLUGS = [
    "-spokane-county-wa-so", "arlington-pd-wa", "auburn-wa-pd",
    "bonney-lake-wa-pd", "centralia-pd-wa", "college-place-wa-pd",
    "des-moines-wa-pd", "eatonville-wa-pd", "edmonds-wa-pd",
    "ellensburg-wa-pd", "everett-wa-pd", "kent-wa-pd",
    "lake-stevens-wa-pd", "lakewood-wa-pd", "lynnwood-wa-pd",
    "marysville-wa-pd", "medina-wa-pd", "mill-creek-wa-pd",
    "monroe-wa-pd", "moses-lake-wa-pd", "mount-vernon-wa-pd",
    "mukilteo-wa-pd", "newcastle-wa-pd", "olympia-wa-pd-",
    "prosser-wa-pd", "puyallup-wa-pd", "renton-wa-pd", "richland-pd-wa",
    "seatac-wa-pd", "selah-wa-pd", "shelton-pd-wa", "skamania-co-wa-so",
    "snohomish-county-wa-so-", "stanwood-wa-pd", "sultan-wa-pd",
    "sumner-wa-pd", "toppenish-wa-pd", "tukwila-wa-pd",
    "walla-walla-wa-pd", "yakima-wa-pd", "yelm-wa-pd",
]


def log_health(slug, data):
    slug_dir = DATA_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str)
    with open(slug_dir / "health.jsonl", "a") as f:
        f.write(line + "\n")


async def check_slug(slug, page):
    url = f"https://transparency.flocksafety.com/{slug}"
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        status = response.status if response else None
        title = await page.title()
        text = await page.inner_text("body")
        if status == 429 or "Just a moment" in title or "Error 1015" in text:
            return {"status": "blocked", "detail": "cloudflare"}
        if status and status >= 400:
            return {"status": "error", "detail": f"http_{status}"}
        return {"status": "ok", "detail": f"http_{status}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def main():
    if AGENCIES_FILE.exists():
        with open(AGENCIES_FILE) as f:
            slugs = json.load(f)
    else:
        slugs = WA_SLUGS

    ts = datetime.now(timezone.utc).isoformat()
    counts = {"ok": 0, "blocked": 0, "error": 0}

    p = await async_playwright().__aenter__()
    browser = await p.chromium.launch(headless=False)
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()

    try:
        for i, slug in enumerate(slugs):
            print(f"[{i+1}/{len(slugs)}] {slug} ...", end=" ", flush=True)
            result = await check_slug(slug, page)
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            print(result["status"])
            log_health(slug, {"ts": ts, **result})
    finally:
        await page.close()
        await context.close()
        await browser.close()
        await p.stop()

    total = sum(counts.values())
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"\n  {total} checked ({summary})")
    print(f"COMMIT_MSG: health: {total} checked ({summary})", flush=True)

    if counts.get("error", 0) or counts.get("blocked", 0):
        for slug in slugs:
            slug_dir = DATA_DIR / slug
            hf = slug_dir / "health.jsonl"
            if not hf.exists():
                continue
            with open(hf) as f:
                last = json.loads(f.read().strip().split("\n")[-1])
            if last["status"] in ("error", "blocked"):
                print(f"COMMIT_BODY:  {slug}: {last['status']} ({last['detail']})")

    if counts.get("error", 0) > len(slugs) // 2:
        print("FATAL: >50% of agencies unreachable")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
