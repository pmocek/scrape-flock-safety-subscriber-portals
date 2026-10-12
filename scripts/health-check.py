#!/usr/bin/env python3
"""Quick Playwright health check for each agency portal.

Reuses the same browser/context for all slugs in one run.
Cloudflare blocks are detected the same way as the scraper
(HTTP 429, "Just a moment" title, "Error 1015" body text).

Saves to data/{slug}/health.jsonl (append-only).
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

try:
    import playwright_stealth
    STEALTH_OK = True
except ImportError:
    STEALTH_OK = False

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


def is_wa_slug(slug):
    return slug.endswith("-wa-pd") or slug.endswith("-wa-so") or "-wa-" in slug


def log_health(slug, data):
    slug_dir = DATA_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str)
    with open(slug_dir / "health.jsonl", "a") as f:
        f.write(line + "\n")


async def check_slug(slug, page, max_retries=2):
    """Check one portal, retrying Cloudflare interstitials.

    Mirrors scrape_one_slug(): a single fast attempt gets 403'd by Cloudflare
    on GitHub runner IPs even though the portal is fine, so retry once with
    backoff and settle longer before judging. Without this every portal
    reports "blocked" and the dashboard is worthless.

    2 attempts, not the scraper's 3: the health check runs hourly and a burst
    of 221 checks is what triggers Cloudflare rate limiting in the first place.
    """
    url = f"https://transparency.flocksafety.com/{slug}"
    for attempt in range(max_retries):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(8000)
            status = response.status if response else None
            title = await page.title()
            text = await page.inner_text("body")
            if status == 429 or "Just a moment" in title or "Error 1015" in text:
                if attempt < max_retries - 1:
                    await page.wait_for_timeout((attempt + 1) * 15000)
                    continue
                return {"status": "blocked", "detail": "cloudflare"}
            if status and status >= 400:
                return {"status": "error", "detail": f"http_{status}"}
            return {"status": "ok", "detail": f"http_{status}"}
        except Exception as e:
            if attempt < max_retries - 1:
                await page.wait_for_timeout((attempt + 1) * 5000)
                continue
            return {"status": "error", "detail": str(e)}
    return {"status": "error", "detail": "exhausted_retries"}


async def main():
    # Hard wall-clock budget. GitHub Actions kills a job at 6h, and because
    # this step is continue-on-error, a timeout is indistinguishable from a
    # pass with no data. Abort early and still emit COMMIT_MSG so the run
    # produces a (partial) record rather than vanishing.
    budget_s = int(os.environ.get("HEALTH_CHECK_BUDGET_SECONDS", "2400"))
    started = time.monotonic()

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        with open(sys.argv[1]) as f:
            slugs = json.load(f)
    elif AGENCIES_FILE.exists():
        with open(AGENCIES_FILE) as f:
            all_slugs = json.load(f)
        # wa-agencies.json is the *scraper worklist* and grows via cross-agency
        # spidering (6703 slugs nationally). Health-checking all of them takes
        # ~6h, which hits the GitHub Actions job limit and silently kills the
        # job before COMMIT_MSG is ever printed. This check is WA-scoped --
        # hence the hardcoded WA_SLUGS list -- so filter the worklist to WA.
        slugs = [s for s in all_slugs if is_wa_slug(s)]
    else:
        slugs = WA_SLUGS

    # Offset by absolute hour, not day-of-year: a day-based offset is constant
    # for 24h, so every scheduled run in a day re-checked the same slice and
    # the rest of the list was never reached. Hour-based advances the window by
    # one slice per run, giving full coverage roughly every 7.4 runs.
    slice_size = int(os.environ.get("HEALTH_CHECK_SLICE", "0")) or None
    if slice_size and slice_size < len(slugs):
        now = time.gmtime()
        slot = now.tm_yday * 24 + now.tm_hour
        offset = (slot * slice_size) % len(slugs)
        slugs = slugs[offset:] + slugs[:offset]
        slugs = slugs[:slice_size]
        print(f"rotating slice: {len(slugs)} of the WA list (offset {offset})")

    ts = datetime.now(timezone.utc).isoformat()
    counts = {"ok": 0, "blocked": 0, "error": 0}

    p = await async_playwright().__aenter__()
    browser = await p.chromium.launch(headless=False)
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()
    # Match scrape-flock.py: without stealth, Cloudflare serves an interstitial
    # and every portal reports "blocked" -- indistinguishable from a real block.
    # The first live run after the scope fix reported 220/221 blocked while the
    # scraper was still seeing 267 active portals from the same kind of IP.
    if STEALTH_OK:
        stealth = playwright_stealth.Stealth()
        await stealth.apply_stealth_async(page)
    else:
        print("WARNING: playwright-stealth unavailable -- Cloudflare will block every check")

    try:
        for i, slug in enumerate(slugs):
            if time.monotonic() - started > budget_s:
                print(
                    f"\n  time budget ({budget_s}s) exhausted after {i} checks"
                    f" -- stopping early",
                    flush=True,
                )
                break
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
