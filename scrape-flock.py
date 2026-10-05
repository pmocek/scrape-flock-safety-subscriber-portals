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
import html
import io
import json
import os
import re
import sys
import time
import argparse
import urllib.parse
from datetime import datetime, timezone, timedelta
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


def parse_stats(text, html_text=None):
    """Extract structured stats and disclosures from transparency portal text and HTML."""
    stats = {}

    lines = text.strip().split("\n")
    if len(lines) >= 3:
        stats["page_name"] = lines[2].strip()

    # If HTML is provided, extract higher-fidelity metadata
    if html_text:
        # Check portal status (active, inactive, not_found)
        if ("Page not found" in html_text and "The page you are looking for doesn" in html_text) or ("Page Not Found" in text and "doesn" in text):
            stats["portal_status"] = "not_found"
            return stats

        title_m = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.IGNORECASE | re.DOTALL)
        title_str = (title_m.group(1) if title_m else "") + " " + (h1_m.group(1) if h1_m else "")
        if "[Inactive]" in title_str or "[inactive]" in title_str.lower():
            stats["portal_status"] = "inactive"
        else:
            stats["portal_status"] = "active"

        # Refine page_name from h1 if available
        if h1_m:
            raw_h1 = re.sub(r"<br\s*/?>", " ", h1_m.group(1))
            raw_h1 = re.sub(r"<[^>]+>", "", raw_h1)
            raw_h1 = re.sub(r"\s*Transparency Portal\s*", "", raw_h1, flags=re.IGNORECASE)
            raw_h1 = re.sub(r"\s*\[Inactive\]\s*", "", raw_h1, flags=re.IGNORECASE).strip()
            if raw_h1:
                stats["page_name"] = raw_h1

        # Exact ISO timestamp of portal update
        ts_m = re.search(r"Last updated:\s*<span[^>]*title=[\"\x27]([^\s\"\x27>]+)[\"\x27]", html_text)
        if ts_m:
            stats["portal_last_updated"] = ts_m.group(1)

        # Overview / Mission Statement
        over_m = re.search(r"<div[^>]*class=[\"\x27][^\"\x27]*tpOverview[^\"\x27]*[\"\x27][^>]*>.*?<p[^>]*>(.*?)</p>", html_text, re.DOTALL)
        if over_m:
            stats["overview"] = html.unescape(re.sub(r"<[^>]+>", "", over_m.group(1))).strip()

        # Logo and Hero image assets
        logo_m = re.search(r"<img[^>]*class=[\"\x27][^\"\x27]*tpHeroLogoImage[^\"\x27]*[\"\x27][^>]*src=[\"\x27]([^\s\"\x27>]+)", html_text)
        if logo_m:
            stats["logo_url"] = logo_m.group(1)
        hero_m = re.search(r"<img[^>]*class=[\"\x27][^\"\x27]*tpHeroImage[^\"\x27]*[\"\x27][^>]*src=[\"\x27]([^\s\"\x27>]+)", html_text)
        if hero_m:
            stats["hero_image_url"] = hero_m.group(1)

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
            label = key.replace("_", " ").title()
            m = re.search(rf'{re.escape(label)}\s*\n+\s*Data Unavailable', text, re.IGNORECASE)
            if m:
                stats[key] = "Data Unavailable"

    shares_with = []
    receives_from = []

    # If HTML has data-tp-full-value access tables, use them for 100% fidelity
    if html_text and "data-tp-full-value" in html_text:
        s_block = re.search(r"Sharing Network Data With[\s\S]*?(?=Receiving Network Data From|Policy &amp; Trust|<section|\Z)", html_text)
        if s_block:
            vals = re.findall(r"data-tp-full-value=[\"\x27]([^\"]+)[\"\x27]", s_block.group(0))
            if vals:
                shares_with = [html.unescape(v.strip()) for v in vals if v.strip()]
                stats["shares_data_with"] = shares_with

        r_block = re.search(r"Receiving Network Data From[\s\S]*?(?=Policy &amp; Trust|<section|\Z)", html_text)
        if r_block:
            vals = re.findall(r"data-tp-full-value=[\"\x27]([^\"]+)[\"\x27]", r_block.group(0))
            if vals:
                receives_from = [html.unescape(v.strip()) for v in vals if v.strip()]
                stats["receives_data_from"] = receives_from

    # Text fallback if HTML table extraction yielded nothing
    if not shares_with and not receives_from:
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

    # Policies — un-truncated
    for key, label in [("detected", "What's Detected"), ("not_detected", "What's Not Detected"),
                        ("acceptable_use", "Acceptable Use Policy"),
                        ("prohibited_uses", "Prohibited Uses"),
                        ("access_policy", "Access Policy"),
                        ("hotlist_policy", "Hotlist Policy")]:
        pat = rf'{re.escape(label)}\s*\n+\s*\n([\s\S]*?)(?:\n\n\w|\Z)'
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            stats[key] = val

    # HTML widget and section parsing
    if html_text:
        # Top Offense Types widget
        top_offense_m = re.search(r"Top Offense Types</h3>[\s\S]*?<ol[^>]*>([\s\S]*?)</ol>", html_text)
        if top_offense_m:
            items = re.findall(r"<li[^>]*>[\s\S]*?<span[^>]*>(?:<span>)?(.*?)(?:</span>)?</span>[\s\S]*?</li>", top_offense_m.group(1))
            cleaned_items = [html.unescape(re.sub(r"<[^>]+>", "", it)).strip() for it in items if it.strip()]
            if cleaned_items:
                stats["top_offense_types"] = cleaned_items

        # Camera Alert Activity widget
        alert_act_m = re.search(r"Camera Alert Activity</h3>[\s\S]*?<div[^>]*class=[\"\x27][^\"\x27]*tpActivityValue[^\"\x27]*[\"\x27][^>]*>(.*?)</div>([\s\S]*?)(?=<div class=[\"\x27]tpSection|\Z)", html_text)
        if alert_act_m:
            tot_str = re.sub(r"<[^>]+>", "", alert_act_m.group(1)).strip()
            act_data = {"total": tot_str}
            rows = re.findall(r"<span class=[\"\x27]tpActivityRowLabel[\"\x27][^>]*>(.*?)</span>[\s\S]*?<strong class=[\"\x27]tpActivityRowValue[\"\x27][^>]*>(.*?)</strong>", alert_act_m.group(2))
            breakdown = {}
            for lbl, cnt in rows:
                clean_lbl = html.unescape(re.sub(r"<[^>]+>", "", lbl)).strip()
                clean_cnt = re.sub(r"<[^>]+>", "", cnt).strip()
                if clean_lbl:
                    breakdown[clean_lbl] = clean_cnt
            if breakdown:
                act_data["breakdown"] = breakdown
            stats["camera_alert_activity"] = act_data

        # Custom disclosures and More Info section
        standard_card_titles = {
            "data retention", "total cameras", "unique vehicles detected",
            "vehicles detected in the last 30 days", "vehicles detected",
            "number of searches", "hotlists alerted on", "number of hotlist hits",
            "hotlist hits in the last 21 days", "sharing network data with",
            "receiving network data from", "what's detected", "what's not detected",
            "acceptable use policy", "prohibited uses", "access policy",
            "hotlist policy", "public search audit"
        }
        entry_blocks = re.findall(
            r"<p[^>]*font-weight:\s*600[^>]*>(.*?)</p>[\s\S]*?<div[^>]*white-space:\s*pre-line[^>]*>([\s\S]*?)</div>\s*</div>",
            html_text
        )
        custom_cards = {}
        policy_links = []
        funding_sources = []
        for title_raw, content_raw in entry_blocks:
            title = html.unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()
            if not title or title.lower() in standard_card_titles:
                continue

            for link in re.findall(r"href=[\"\x27](https?://[^\s\"\x27>]+)[\"\x27]", content_raw):
                policy_links.append(link)

            text_content = html.unescape(re.sub(r"<br\s*/?>", "\n", content_raw))
            text_content = html.unescape(re.sub(r"<[^>]+>", "", text_content)).strip()
            custom_cards[title] = text_content

            if "camera location" in title.lower():
                lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                stats["camera_locations"] = lines
            elif "funding" in title.lower():
                funding_sources.append(text_content)

        if custom_cards:
            stats["more_info"] = custom_cards
        if funding_sources:
            stats["funding_source"] = "\n\n".join(funding_sources)
        if policy_links:
            stats["policy_links"] = sorted(list(set(policy_links)))

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


def get_block_info(slug, save_dir):
    """Return (consecutive_blocks, last_block_time, has_history).

    has_history is True if the slug has ever successfully produced page.txt.
    consecutive_blocks counts consecutive block events since the last successful scrape.
    """
    slug_dir = save_dir / slug
    bf = slug_dir / "blocked.jsonl"
    sf = slug_dir / "stats.jsonl"
    has_history = (slug_dir / "page.txt").exists()

    if not bf.exists():
        return 0, None, has_history

    blines = []
    with open(bf, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    blines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not blines:
        return 0, None, has_history

    last_block = blines[-1]
    last_block_ts = None
    if "ts" in last_block:
        try:
            last_block_ts = datetime.fromisoformat(last_block["ts"])
        except ValueError:
            pass

    # Check if there was a successful scrape after the last block
    if sf.exists() and has_history:
        slines = []
        with open(sf, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        slines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        for entry in reversed(slines):
            if "error" not in entry and entry.get("portal_status") != "not_found":
                try:
                    last_succ_ts = datetime.fromisoformat(entry["ts"])
                    if last_block_ts and last_succ_ts >= last_block_ts:
                        # Scrape succeeded after or at last block; reset counter
                        return 0, None, has_history
                except (ValueError, KeyError):
                    pass
                break

    # Determine consecutive block count
    if "consecutive_blocks" in last_block:
        consecutive = int(last_block["consecutive_blocks"])
    elif "retry_count" in last_block:
        consecutive = int(last_block["retry_count"])
    else:
        consecutive = len(blines)

    return consecutive, last_block_ts, has_history


def should_attempt_slug(slug, save_dir, now=None):
    """Determine whether a slug is eligible to be scraped or currently in backoff.

    Returns (should_scrape: bool, reason: str).
    - Slugs with no historical data (never succeeded) back off exponentially: 2^N hours (capped at 720h / 30d).
    - Slugs with historical data (has page.txt) back off for 1 hour.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    consecutive, last_block_ts, has_history = get_block_info(slug, save_dir)
    if consecutive == 0 or last_block_ts is None:
        return True, "ready"

    if has_history:
        backoff_hours = 1
    else:
        backoff_hours = min(2 ** consecutive, 720)

    retry_after = last_block_ts + timedelta(hours=backoff_hours)
    if now < retry_after:
        remaining_hours = (retry_after - now).total_seconds() / 3600.0
        return False, f"in backoff ({consecutive} blocks, wait {backoff_hours}h, {remaining_hours:.1f}h remaining)"

    return True, "backoff expired"


def record_blocked(slug, save_dir, error_msg, now=None):
    """Record a block event in blocked.jsonl with consecutive count and backoff metadata."""
    if now is None:
        now = datetime.now(timezone.utc)

    consecutive, _, has_history = get_block_info(slug, save_dir)
    new_consecutive = consecutive + 1

    if has_history:
        backoff_hours = 1
    else:
        backoff_hours = min(2 ** new_consecutive, 720)

    retry_after = (now + timedelta(hours=backoff_hours)).isoformat()

    entry = {
        "ts": now.isoformat(),
        "error": error_msg,
        "consecutive_blocks": new_consecutive,
        "backoff_hours": backoff_hours,
        "retry_after": retry_after,
    }

    slug_dir = save_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str)
    with open(slug_dir / "blocked.jsonl", "a") as f:
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

                stats = parse_stats(text, html_text=html)
                result["success"] = True
                result["stats"] = stats
                result["title"] = title

                slug_dir = save_dir / slug
                slug_dir.mkdir(parents=True, exist_ok=True)

                # 1. Download official agency logo if available and not yet present
                logo_url = stats.get("logo_url")
                if logo_url and logo_url.startswith("http"):
                    ext = ".png"
                    if ".svg" in logo_url:
                        ext = ".svg"
                    elif ".jpg" in logo_url or ".jpeg" in logo_url:
                        ext = ".jpg"
                    logo_file = slug_dir / f"logo{ext}"
                    if not logo_file.exists():
                        try:
                            logo_resp = await context.request.get(logo_url, timeout=15000)
                            if logo_resp.status == 200:
                                with open(logo_file, "wb") as f:
                                    f.write(await logo_resp.body())
                        except Exception as e:
                            print(f"    Failed to download logo for {slug}: {e}")

                # 2. Download direct policy PDF if linked and not yet present
                for plink in stats.get("policy_links", []):
                    if plink.lower().endswith(".pdf"):
                        pdf_file = slug_dir / "policy.pdf"
                        if not pdf_file.exists():
                            try:
                                pdf_resp = await context.request.get(plink, timeout=20000)
                                if pdf_resp.status == 200:
                                    with open(pdf_file, "wb") as f:
                                        f.write(await pdf_resp.body())
                                    break
                            except Exception as e:
                                print(f"    Failed to download policy PDF for {slug}: {e}")

                # 3. Extract and cumulatively merge Public Search Audit CSV
                csv_link = await page.query_selector('a[download="public_search_audit.csv"]')
                if csv_link:
                    href = await csv_link.get_attribute("href")
                    if href and href.startswith("data:text/csv;charset=utf-8,"):
                        csv_content = urllib.parse.unquote(href[len("data:text/csv;charset=utf-8,"):])
                        new_reader = csv.DictReader(io.StringIO(csv_content))
                        new_rows = list(new_reader)
                        fieldnames = list(new_reader.fieldnames) if new_reader.fieldnames else ["id", "userId", "searchDate", "networkCount", "offenseType", "reason"]

                        audit_file = slug_dir / "audit.csv"
                        existing_rows = []
                        if audit_file.exists():
                            try:
                                with open(audit_file, "r") as f:
                                    ex_reader = csv.DictReader(f)
                                    existing_rows = list(ex_reader)
                                    if ex_reader.fieldnames:
                                        for fn in ex_reader.fieldnames:
                                            if fn not in fieldnames:
                                                fieldnames.append(fn)
                            except Exception:
                                pass

                        # Deduplicate by unique key
                        seen_keys = set()
                        merged_rows = []
                        for r in existing_rows + new_rows:
                            key = (r.get("id"), r.get("searchDate"), r.get("userId"), r.get("reason"), r.get("offenseType"))
                            if key not in seen_keys:
                                seen_keys.add(key)
                                merged_rows.append(r)

                        merged_rows.sort(key=lambda r: r.get("searchDate", ""), reverse=True)

                        with open(audit_file, "w", newline="") as f:
                            writer = csv.DictWriter(f, fieldnames=fieldnames)
                            writer.writeheader()
                            writer.writerows(merged_rows)

                        if merged_rows:
                            stats["audit_count"] = len(merged_rows)
                            dates = [r["searchDate"] for r in merged_rows if r.get("searchDate")]
                            if dates:
                                stats["audit_date_min"] = min(dates)
                                stats["audit_date_max"] = max(dates)
                            imm_reasons = _scan_immigration_reasons(merged_rows)
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
        record_blocked(slug, save_dir, result.get("error"))

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
    parser.add_argument("--ignore-backoff", action="store_true",
                        help="Attempt scraping even if slug is currently in backoff window")
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

    save_dir = Path(args.save_dir) if args.save_dir else DATA_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    # Filter out slugs currently in backoff unless --ignore-backoff or single --slug specified
    if not args.ignore_backoff and not args.slug:
        active = []
        skipped_backoff = 0
        now = datetime.now(timezone.utc)
        for s in slugs:
            attempt_ok, reason = should_attempt_slug(s, save_dir, now=now)
            if not attempt_ok:
                skipped_backoff += 1
            else:
                active.append(s)
        if skipped_backoff:
            print(f"  Skipped {skipped_backoff} slugs currently in backoff window")
        slugs = active

    # Apply batching — cap per batch at ~10 to avoid Cloudflare burst detection
    if args.batch > 0:
        if args.batch > args.total_batches:
            print(f"ERROR: batch {args.batch} > total-batches {args.total_batches}")
            sys.exit(1)

        # Cap per batch: if total is too large, only scrape the first N of this batch
        max_per_batch = 8
        if len(slugs) > args.total_batches * max_per_batch:
            chunk = max(len(slugs) // args.total_batches, 1)
            start = (args.batch - 1) * chunk
            end = start + chunk if args.batch < args.total_batches else len(slugs)
            slugs = slugs[start:end]
            if len(slugs) > max_per_batch:
                slugs = slugs[:max_per_batch]
                print(f"  Batch capped at first {max_per_batch} of {chunk} available")
        else:
            chunk = max(len(slugs) // args.total_batches, 1)
            start = (args.batch - 1) * chunk
            end = start + chunk if args.batch < args.total_batches else len(slugs)
            slugs = slugs[start:end]

        print(f"Batch {args.batch}/{args.total_batches}: {len(slugs)} agencies to scrape")

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
