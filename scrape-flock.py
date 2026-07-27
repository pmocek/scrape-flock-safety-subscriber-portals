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
import csv
import io
import json
import os
import re
import sys
import time
import argparse
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

PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"
EYESONFLOCK_URL = "https://eyesonflock.com/api/v1/data"
EYESONFLOCK_JSON_FILE = PROJECT_DIR / "eyesonflock.com-api-v1-data.json"

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


def parse_stats(text):
    """Extract structured stats from the transparency portal page."""
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

    agencies = []
    for direction in ("Sharing Network Data With", "Receiving Network Data From"):
        for m in re.finditer(
            rf'(?:{re.escape(direction)})\s*\n+\s*\n'
            r'(?:Organizations[^\n]*\.\s*\n+\s*\n)?'
            r'([\s\S]*?)(?=\n\n[A-Z]|\Z)',
            text
        ):
            lst = [a.strip() for a in m.group(1).split("\n") if a.strip() and len(a.strip()) > 3]
            agencies.extend(lst)
    if agencies:
        seen = set()
        agencies = [a for a in agencies if not (a in seen or seen.add(a))]
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


def _build_name_map(save_dir):
    """Build name→slug mapping from eyesonflock data and scraped page.txt files."""
    name_to_slug = {}
    if EYESONFLOCK_JSON_FILE.exists():
        try:
            with open(EYESONFLOCK_JSON_FILE) as f:
                data = json.load(f)
            for p in data.get("portals", []):
                url = p.get("portal_url", "")
                slug = url.split("/")[-1].strip() if url else ""
                if not slug:
                    continue
                city = (p.get("city") or "").strip().lower()
                state = (p.get("state") or "").strip().lower()
                name = (p.get("name") or "").strip().lower()
                if city:
                    name_to_slug[city] = slug
                    if state:
                        name_to_slug[f"{city} {state}"] = slug
                        name_to_slug[f"{city} ({state})"] = slug
                        name_to_slug[f"{city}, {state}"] = slug
                if name:
                    name_to_slug[name] = slug
        except Exception:
            pass

    for slug_dir in sorted(save_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        slug = slug_dir.name
        txt_path = slug_dir / "page.txt"
        if txt_path.exists():
            text = txt_path.read_text()
            lines = text.strip().split("\n")
            if len(lines) >= 3:
                name = lines[2].strip()
                name_to_slug[name] = slug
                name_to_slug[name.lower()] = slug
    return name_to_slug


def _name_to_slug(name):
    """Heuristic conversion of agency display name to likely slug."""
    name = re.sub(r'\s*\[Inactive\]', '', name).strip()
    name = name.lower()
    name = re.sub(r'\(wa\)', 'wa', name)
    name = re.sub(r'\bpolice department\b', 'pd', name)
    name = re.sub(r'\bpolice dept\.?\b', 'pd', name)
    name = re.sub(r'[()]', '', name)
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')


IMMIGRATION_RE = re.compile(
    r'(?i)\b(?:ice|usbp|hsi|customs|cbp)\b|border\s+patrol|\bimmigra'
)


def _scan_immigration_reasons(rows):
    """Scan audit CSV rows for immigration-related search reasons."""
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
                    wait = (attempt + 1) * 15
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

                slug_dir = save_dir / slug
                slug_dir.mkdir(parents=True, exist_ok=True)

                # Extract Public Search Audit CSV, if available
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
                wait = (attempt + 1) * 15
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
            await asyncio.sleep((attempt + 1) * 15)

    if not result["success"]:
        slug_dir = save_dir / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        line = json.dumps({"ts": ts, "error": result.get("error")}, default=str)
        with open(slug_dir / "blocked.jsonl", "a") as f:
            f.write(line + "\n")

    return result


def scrape_slug(slug, save_dir):
    """Sync wrapper with defensive crash protection."""
    try:
        return asyncio.run(scrape_one_slug(slug, save_dir))
    except Exception as e:
        print(f"  {slug}: UNHANDLED ERROR - {e}")
        return {"slug": slug, "url": f"https://transparency.flocksafety.com/{slug}", "success": False, "error": str(e)}


def refresh_agencies():
    """Fetch agency list from eyesonflock.com and save WA agencies."""
    if EYESONFLOCK_JSON_FILE.exists():
        print(f"Loading local eyesonflock data from {EYESONFLOCK_JSON_FILE}")
        with open(EYESONFLOCK_JSON_FILE) as f:
            data = json.load(f)
    else:
        print(f"Fetching eyesonflock data from {EYESONFLOCK_URL}")
        import urllib.request
        req = urllib.request.Request(EYESONFLOCK_URL, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

    agencies = []
    for portal in data.get("portals", []):
        if portal.get("state") == "WA":
            url = portal.get("portal_url", "")
            slug = url.split("/")[-1].strip()
            if slug:
                agencies.append(slug)

    agencies = sorted(list(set(agencies)))

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
    elif AGENCIES_FILE.exists():
        with open(AGENCIES_FILE) as f:
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

    # Cross-agency discovery: find external agencies not yet scraped
    discovered = set()
    name_map = _build_name_map(save_dir)
    known_slugs = set(WA_SLUGS)
    try:
        with open(AGENCIES_FILE) as f:
            known_slugs.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    for r in results:
        if not r.get("success"):
            continue
        agencies = r.get("stats", {}).get("external_agencies", [])
        for name in agencies:
            clean_name = re.sub(r'\s*\[.*?\]', '', name).strip()
            slug = (
                name_map.get(name)
                or name_map.get(name.lower())
                or name_map.get(clean_name.lower())
                or _name_to_slug(name)
            )
            if slug and len(slug) > 3 and slug not in ("additional-info",):
                if (save_dir / slug / "page.txt").exists():
                    known_slugs.add(slug)
                elif slug not in known_slugs and slug not in discovered:
                    discovered.add(slug)

    if discovered:
        disc_list = sorted(discovered)
        print(f"\nDiscovered {len(disc_list)} new agencies via sharing network:")
        for s in disc_list:
            print(f"  {s}")

        # Update wa-agencies.json with discovered slugs so they enter batched rotation
        all_agencies = sorted(list(known_slugs.union(discovered)))
        with open(AGENCIES_FILE, "w") as f:
            json.dump(all_agencies, f, indent=2)
        print(f"Updated {AGENCIES_FILE} with {len(all_agencies)} total agencies for batched scraping.")

        # Scrape a small sample (max 5) inline; remaining will be scraped via batch schedule
        max_inline = 5
        to_scrape = disc_list[:max_inline]
        print(f"Scraping initial sample of {len(to_scrape)} discovered agencies inline...")
        for slug in to_scrape:
            print(f"[Discovery] {slug}")
            result = scrape_slug(slug, save_dir)
            results.append(result)
        ok2 = sum(1 for r in results if r.get("success"))
        print(f"\nInline discovery sample done: {ok2 - ok}/{len(to_scrape)} OK")


if __name__ == "__main__":
    main()
