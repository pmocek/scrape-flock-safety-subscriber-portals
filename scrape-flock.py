#!/usr/bin/env python3
"""
Flock Safety Transparency Portal scraper using Playwright.

Usage:
    python3 scrape-flock.py                           # Scrape all WA agencies
    python3 scrape-flock.py --slug renton-wa-pd       # Single agency
    python3 scrape-flock.py --refresh-agencies        # Update agency list
    python3 scrape-flock.py --batch 2 --total-batches 6   # Batch 2 of 6
"""

import asyncio
import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

PLAYWRIGHT_OK = False
STEALTH_OK = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    pass

try:
    import playwright_stealth
    STEALTH_OK = True
except ImportError:
    pass

PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"
HAVEIBEENFLOCKED_URL = "https://haveibeenflocked.com/news/transparency-portals/"

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


def parse_stats(text):
    """Extract structured stats from the transparency portal page."""
    stats = {}

    def grab_int(pattern, key):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            v = m.group(1).replace(",", "")
            try:
                stats[key] = int(v)
            except ValueError:
                stats[key] = v

    grab_int(r'Data\s*[Rr]etention\s*\n.*?(\d+)\s*days', "retention_days")
    grab_int(r'Total Cameras\s*\n.*?\n\s*([\d,]+)', "total_cameras")
    grab_int(r'(?:Vehicles|Unique Vehicles).*?30\s*days\s*\n.*?\n\s*([\d,]+)', "vehicles_30d")
    grab_int(r'Number of Hotlist Hits\s*\n.*?\n\s*([\d,]+)', "hotlist_hits_30d")
    grab_int(r'Number of Searches\s*\n.*?\n\s*([\d,]+)', "searches_30d")

    for key in ("hotlist_hits_30d", "searches_30d", "vehicles_30d"):
        if key not in stats:
            m = re.search(rf'{re.escape(key.replace("_"," ")).title()}\s*\n+\s*Data Unavailable', text, re.IGNORECASE)
            if m:
                stats[key] = "Data Unavailable"

    m = re.search(r'(?:External )?[Aa]gencies\s*who\s*have\s*access\s*\n+\s*\n([\s\S]*?)(?:\n\n(?:\w|\d)\n|\Z)', text)
    if m:
        agencies = [a.strip() for a in m.group(1).split("\n") if a.strip() and len(a.strip()) > 3]
        stats["external_agencies_count"] = len(agencies)
        stats["external_agencies"] = agencies

    m = re.search(r'Hotlists?\s*Alerted\s*On\s*\n+\s*\n([\s\S]*?)(?:\n\n\w|\Z)', text)
    if m:
        stats["hotlists"] = m.group(1).strip()

    for key, label in [("detected", "What's Detected"), ("not_detected", "What's Not Detected"),
                        ("acceptable_use", "Acceptable Use Policy"),
                        ("prohibited_uses", "Prohibited Uses"),
                        ("access_policy", "Access Policy"),
                        ("hotlist_policy", "Hotlist Policy")]:
        pat = rf'{re.escape(label)}\s*\n+\s*\n([\s\S]*?)(?:\n\n\w|\Z)'
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            if len(val) > 500:
                val = val[:500]
            stats[key] = val

    return stats


def append_jsonl(slug_dir, data):
    """Append a JSON line to stats.jsonl."""
    slug_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str)
    with open(slug_dir / "stats.jsonl", "a") as f:
        f.write(line + "\n")


async def scrape_one_slug(slug, save_dir, max_retries=3):
    """Scrape one agency page and save results. Retries on failure."""
    url = f"https://transparency.flocksafety.com/{slug}"
    result = {"slug": slug, "url": url, "success": False}

    for attempt in range(max_retries):
        p = await async_playwright().__aenter__()
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        if STEALTH_OK:
            stealth = playwright_stealth.Stealth()
            await stealth.apply_stealth_async(page)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)

            title = await page.title()
            if "Just a moment" in title:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 15
                    print(f"  {slug}: Cloudflare (attempt {attempt+1}), retrying in {wait}s...")
                else:
                    result["error"] = "Cloudflare"
                    print(f"  {slug}: BLOCKED (after {max_retries} attempts)")
            else:
                text = await page.inner_text("body")
                html = await page.content()

                stats = parse_stats(text)
                result["success"] = True
                result["stats"] = stats
                result["title"] = title

                slug_dir = save_dir / slug
                slug_dir.mkdir(parents=True, exist_ok=True)

                ts = datetime.now(timezone.utc).isoformat()
                append_jsonl(slug_dir, {"ts": ts, **stats})

                with open(slug_dir / "page.html", "w") as f:
                    f.write(html)
                with open(slug_dir / "page.txt", "w") as f:
                    f.write(text)

                print(f"  {slug}: OK ({stats.get('vehicles_30d', '?')} vehicles, {stats.get('total_cameras', '?')} cameras)")
                return result

        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 15
                print(f"  {slug}: Error (attempt {attempt+1}): {e}, retrying in {wait}s...")
            else:
                result["error"] = str(e)
                print(f"  {slug}: ERROR - {e}")
        finally:
            await page.close()
            await context.close()
            await browser.close()
            await p.stop()

        if attempt < max_retries - 1:
            await asyncio.sleep((attempt + 1) * 15)

    if not result["success"]:
        slug_dir = save_dir / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        append_jsonl(slug_dir, {"ts": ts, "error": result.get("error")})

    return result


def scrape_slug(slug, save_dir):
    """Sync wrapper."""
    return asyncio.run(scrape_one_slug(slug, save_dir))


def refresh_agencies():
    """Fetch agency list from haveibeenflocked.com and save WA agencies."""
    import urllib.request
    req = urllib.request.Request(HAVEIBEENFLOCKED_URL, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    slugs = set(re.findall(r"transparency\.flocksafety\.com/([a-zA-Z0-9_-]+)", html))
    agencies = sorted(s for s in slugs if "-wa-" in s.lower())

    with open(AGENCIES_FILE, "w") as f:
        json.dump(agencies, f, indent=2)

    print(f"Found {len(agencies)} WA agencies. Saved to {AGENCIES_FILE}")
    return agencies


def main():
    parser = argparse.ArgumentParser(description="Scrape Flock Safety transparency portals via Playwright")
    parser.add_argument("--slug", help="Single slug to scrape")
    parser.add_argument("--slugs-file", help="JSON file with list of slugs to scrape")
    parser.add_argument("--refresh-agencies", action="store_true", help="Update WA agency list")
    parser.add_argument("--save-dir", default=None, help="Output directory (default: data/)")
    parser.add_argument("--batch", type=int, default=0,
                        help="Batch number to scrape (0 = all agencies)")
    parser.add_argument("--total-batches", type=int, default=1,
                        help="Total number of batches (used with --batch)")
    args = parser.parse_args()

    if args.refresh_agencies:
        refresh_agencies()
        return

    if not PLAYWRIGHT_OK:
        print("ERROR: playwright not installed. Run: uv pip install playwright && python3 -m playwright install chromium")
        sys.exit(1)

    if args.slug:
        slugs = [args.slug]
    elif args.slugs_file:
        with open(args.slugs_file) as f:
            slugs = json.load(f)
    else:
        slugs = WA_SLUGS

    # Apply batching
    if args.batch > 0:
        if args.batch > args.total_batches:
            print(f"ERROR: batch {args.batch} > total-batches {args.total_batches}")
            sys.exit(1)
        chunk = len(slugs) // args.total_batches
        start = (args.batch - 1) * chunk
        end = start + chunk if args.batch < args.total_batches else len(slugs)
        slugs = slugs[start:end]
        print(f"Batch {args.batch}/{args.total_batches}: {len(slugs)} agencies")

    save_dir = Path(args.save_dir) if args.save_dir else DATA_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    total = len(slugs)
    print(f"Scraping {total} agencies...")

    start_time = time.time()
    results = []

    for i, slug in enumerate(slugs):
        print(f"[{i+1}/{total}] {slug}")
        result = scrape_slug(slug, save_dir)
        results.append(result)

    ok = sum(1 for r in results if r["success"])
    elapsed = time.time() - start_time
    print(f"\nDone: {ok}/{total} OK ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
