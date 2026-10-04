#!/usr/bin/env python3
"""
Backfill script for Flock Safety Transparency Portal data.
Re-parses existing data/*/page.html and data/*/page.txt files to populate
newly added fields (exact update timestamp, overview, camera locations,
funding sources, policy links, un-truncated policies, and widget metrics)
into data/*/stats.jsonl without making external network requests.

Usage:
    python3 scripts/backfill-portal-data.py
    python3 scripts/backfill-portal-data.py --download-assets
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# Add project root to sys.path so we can import parse_stats from scrape-flock.py
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import importlib
scrape_flock = importlib.import_module("scrape-flock")
parse_stats = scrape_flock.parse_stats

DATA_DIR = PROJECT_DIR / "data"


def backfill(download_assets=False):
    slug_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    print(f"Scanning {len(slug_dirs)} directories in {DATA_DIR}...")

    updated_count = 0
    skipped_count = 0
    camera_locations_count = 0
    policy_links_count = 0
    funding_count = 0
    top_offense_count = 0
    alert_activity_count = 0
    inactive_count = 0
    not_found_count = 0
    logos_downloaded = 0
    policies_downloaded = 0

    for d in slug_dirs:
        slug = d.name
        html_file = d / "page.html"
        txt_file = d / "page.txt"

        if not html_file.exists() and not txt_file.exists():
            skipped_count += 1
            continue

        html_text = html_file.read_text(errors="replace") if html_file.exists() else None
        txt_text = txt_file.read_text(errors="replace") if txt_file.exists() else ""

        parsed = parse_stats(txt_text, html_text=html_text)

        if parsed.get("portal_status") == "not_found":
            not_found_count += 1
        elif parsed.get("portal_status") == "inactive":
            inactive_count += 1

        if "camera_locations" in parsed:
            camera_locations_count += 1
        if "policy_links" in parsed:
            policy_links_count += 1
        if "funding_source" in parsed:
            funding_count += 1
        if "top_offense_types" in parsed:
            top_offense_count += 1
        if "camera_alert_activity" in parsed:
            alert_activity_count += 1

        # Read existing stats.jsonl
        jsonl_file = d / "stats.jsonl"
        lines = []
        if jsonl_file.exists():
            for line in jsonl_file.read_text(errors="replace").splitlines():
                if line.strip():
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        if lines:
            # Update the latest entry with new fields while preserving existing history and original timestamp
            last_entry = lines[-1]
            original_ts = last_entry.get("ts")
            # Merge new fields into last_entry
            last_entry.update(parsed)
            if original_ts:
                last_entry["ts"] = original_ts
            lines[-1] = last_entry
        else:
            ts = parsed.get("portal_last_updated") or "1970-01-01T00:00:00Z"
            lines = [{"ts": ts, **parsed}]

        with open(jsonl_file, "w") as f:
            for item in lines:
                f.write(json.dumps(item, default=str) + "\n")

        # Optional asset download
        if download_assets:
            logo_url = parsed.get("logo_url")
            if logo_url and logo_url.startswith("http"):
                ext = ".png"
                if ".svg" in logo_url:
                    ext = ".svg"
                elif ".jpg" in logo_url or ".jpeg" in logo_url:
                    ext = ".jpg"
                logo_file = d / f"logo{ext}"
                if not logo_file.exists():
                    try:
                        req = urllib.request.Request(logo_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            logo_file.write_bytes(resp.read())
                        logos_downloaded += 1
                    except Exception:
                        pass

            for plink in parsed.get("policy_links", []):
                if plink.lower().endswith(".pdf"):
                    pdf_file = d / "policy.pdf"
                    if not pdf_file.exists():
                        try:
                            req = urllib.request.Request(plink, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=15) as resp:
                                pdf_file.write_bytes(resp.read())
                            policies_downloaded += 1
                            break
                        except Exception:
                            pass

        updated_count += 1

    print("\n=== Backfill Summary ===")
    print(f"Total processed:            {updated_count}")
    print(f"Skipped (no html/txt):       {skipped_count}")
    print(f"Active portals:             {updated_count - inactive_count - not_found_count}")
    print(f"Inactive portals:           {inactive_count}")
    print(f"Not Found portals:          {not_found_count}")
    print(f"With camera locations:      {camera_locations_count}")
    print(f"With policy links:          {policy_links_count}")
    print(f"With funding sources:       {funding_count}")
    print(f"With top offense types:     {top_offense_count}")
    print(f"With camera alert activity: {alert_activity_count}")
    if download_assets:
        print(f"Logos downloaded:           {logos_downloaded}")
        print(f"Policy PDFs downloaded:     {policies_downloaded}")


def main():
    parser = argparse.ArgumentParser(description="Backfill newly added fields across existing portal files")
    parser.add_argument("--download-assets", action="store_true", help="Download logo images and policy PDFs")
    args = parser.parse_args()
    backfill(download_assets=args.download_assets)


if __name__ == "__main__":
    main()
