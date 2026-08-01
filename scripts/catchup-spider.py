#!/usr/bin/env python3
"""
Catch-up spider: scrape only never-tried slugs in wa-agencies.json.

Reads the current agency list and hits slugs that have never been scraped
(no page.txt, no blocked.jsonl). Skips slugs that already have data or
have been blocked before. Rate-limited to avoid Cloudflare: 5s between slugs,
same 3-retry pattern as scrape-flock.py.

Usage:
    python3 scripts/catchup-spider.py
"""

import asyncio
import csv
import io
import json
import re
import sys
import time
import urllib.parse
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

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"

IMMIGRATION_RE = re.compile(
    r'(?i)\b(?:ice|usbp|hsi|customs|cbp)\b|border\s+patrol|\bimmigra'
)

# --- helpers (copied from scrape-flock.py) ---

def parse_stats(text):
    stats = {}
    lines = text.strip().split("\n")
    if len(lines) >= 3:
        stats["page_name"] = lines[2].strip()

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

    shares_with = []
    receives_from = []
    for direction, field in (
        ("Sharing Network Data With", "shares_data_with"),
        ("Receiving Network Data From", "receives_data_from"),
    ):
        items = []
        for m in re.finditer(
            rf'(?:{re.escape(direction)})\s*\n+\s*\n'
            r'(?:Organizations[^\n]*\.\s*\n+\s*\n)?'
            r'([\s\S]*?)(?=\n\n[A-Z]|\Z)',
            text
        ):
            items = [a.strip() for a in m.group(1).split("\n") if a.strip() and len(a.strip()) > 3]
        if items:
            stats[field] = items
            if field == "shares_data_with":
                shares_with.extend(items)
            else:
                receives_from.extend(items)

    # Union for backward compatibility (cross-agency spidering)
    all_agencies = shares_with + receives_from
    if all_agencies:
        seen = set()
        all_agencies = [a for a in all_agencies if not (a in seen or seen.add(a))]
        stats["external_agencies_count"] = len(all_agencies)
        stats["external_agencies"] = all_agencies

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


def _scan_immigration_reasons(rows):
    found = []
    seen = set()
    for row in rows:
        for field in ("reason", "offenseType"):
            val = row.get(field, "")
            m = IMMIGRATION_RE.search(val)
            if m:
                key = val.strip().lower()
                if key not in seen:
                    seen.add(key)
                    found.append(val.strip()[:120])
    return found


def append_jsonl(slug_dir, data):
    slug_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(data, default=str)
    with open(slug_dir / "stats.jsonl", "a") as f:
        f.write(line + "\n")


# --- scraper ---

async def scrape_one_slug(slug, max_retries=3, delay_between_retries=15):
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
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(8000)

            status = response.status if response else None
            title = await page.title()
            text = await page.inner_text("body")
            blocked = (
                status == 429
                or "Just a moment" in title
                or "Error 1015" in text
            )
            if blocked:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * delay_between_retries
                    print(f"  {slug}: Cloudflare (attempt {attempt+1}), retrying in {wait}s...")
                else:
                    result["error"] = "Cloudflare"
                    print(f"  {slug}: BLOCKED (after {max_retries} attempts)")
            else:
                html = await page.content()
                stats = parse_stats(text)
                result["success"] = True
                result["stats"] = stats
                result["title"] = title

                slug_dir = DATA_DIR / slug
                slug_dir.mkdir(parents=True, exist_ok=True)

                csv_link = await page.query_selector('a[download="public_search_audit.csv"]')
                if csv_link:
                    href = await csv_link.get_attribute("href")
                    if href and href.startswith("data:text/csv;charset=utf-8,"):
                        csv_content = urllib.parse.unquote(href[len("data:text/csv;charset=utf-8,"):])
                        with open(slug_dir / "audit.csv", "w") as f:
                            f.write(csv_content)
                        reader = csv.DictReader(io.StringIO(csv_content))
                        rows = list(reader)
                        if rows:
                            stats["audit_count"] = len(rows)
                            dates = [r["searchDate"] for r in rows if r.get("searchDate")]
                            if dates:
                                stats["audit_date_min"] = min(dates)
                                stats["audit_date_max"] = max(dates)
                            imm_reasons = _scan_immigration_reasons(rows)
                            if imm_reasons:
                                stats["audit_immigration_entries"] = len(imm_reasons)
                                stats["audit_immigration_reasons"] = imm_reasons[:20]

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
                wait = (attempt + 1) * delay_between_retries
                print(f"  {slug}: Error (attempt {attempt+1}): {e}, retrying in {wait}s...")
            else:
                result["error"] = str(e)
                print(f"  {slug}: ERROR - {e}")
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await p.stop()
            except Exception:
                pass

        if attempt < max_retries - 1:
            await asyncio.sleep((attempt + 1) * delay_between_retries)

    if not result["success"]:
        slug_dir = DATA_DIR / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        line = json.dumps({"ts": ts, "error": result.get("error")}, default=str)
        with open(slug_dir / "blocked.jsonl", "a") as f:
            f.write(line + "\n")

    return result


def scrape_slug(slug):
    try:
        return asyncio.run(scrape_one_slug(slug))
    except Exception as e:
        print(f"  {slug}: UNHANDLED ERROR - {e}")
        return {"slug": slug, "url": f"https://transparency.flocksafety.com/{slug}", "success": False, "error": str(e)}


def main():
    if not PLAYWRIGHT_OK:
        print("ERROR: playwright not installed.")
        sys.exit(1)

    if not AGENCIES_FILE.exists():
        print(f"ERROR: {AGENCIES_FILE} not found")
        sys.exit(1)

    with open(AGENCIES_FILE) as f:
        all_slugs = json.load(f)

    # Filter to never-tried slugs only
    never_tried = []
    for slug in all_slugs:
        d = DATA_DIR / slug
        if not d.exists():
            never_tried.append(slug)
            continue
        has_page = (d / "page.txt").exists()
        has_blocked = (d / "blocked.jsonl").exists()
        if not has_page and not has_blocked:
            never_tried.append(slug)

    if not never_tried:
        print("No never-tried slugs found. All caught up!")
        return

    total = len(never_tried)
    print(f"Found {total} never-tried slugs in {AGENCIES_FILE.name}")
    print(f"Scraping with 5s delay between slugs, up to 3 retries each...")
    print()

    start_time = time.time()
    results = []

    for i, slug in enumerate(never_tried):
        if i > 0:
            print(f"  --- waiting 5s before next slug ---")
            time.sleep(5)

        print(f"[{i+1}/{total}] {slug}")
        result = scrape_slug(slug)
        results.append(result)

    ok = sum(1 for r in results if r["success"])
    elapsed = time.time() - start_time
    print(f"\nCatch-up done: {ok}/{total} OK ({elapsed:.0f}s)")

    if ok > 0:
        print(f"\nResults written to data/<slug>/ directories.")
        print("Next regular scrape run will pick up any new stats for these agencies.")


if __name__ == "__main__":
    main()
