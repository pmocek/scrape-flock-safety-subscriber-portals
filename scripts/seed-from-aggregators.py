#!/usr/bin/env python3
"""
Seed and cross-reference agency transparency portals from external aggregators:
1. EyesOnFlock API data (eyesonflock.com-api-v1-data.json)
2. OpenStreetMap ALPR cameras (DeFlock crowdsourced dataset via Overpass QL)

Outputs:
- data/portal-registry.json: Unified metadata index for known transparency portals
- data/osm-alpr-wa.json: Cached OpenStreetMap ALPR nodes for Washington State
- data/wa-osm-candidates.json: Candidate slugs generated from OSM camera operators
- Updates wa-agencies.json with newly discovered portal slugs and candidate slugs.

Usage:
    python3 scripts/seed-from-aggregators.py
    python3 scripts/seed-from-aggregators.py --fetch-osm   # Force fresh Overpass API query
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AGENCIES_FILE = PROJECT_DIR / "wa-agencies.json"
EYESONFLOCK_FILE = PROJECT_DIR / "eyesonflock.com-api-v1-data.json"
PORTAL_REGISTRY_FILE = DATA_DIR / "portal-registry.json"
OSM_CACHE_FILE = DATA_DIR / "osm-alpr-wa.json"
OSM_CANDIDATES_FILE = DATA_DIR / "wa-osm-candidates.json"

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
OVERPASS_WA_QUERY = """
[out:json][timeout:60];
area["ISO3166-2"="US-WA"]->.wa;
(
  node["surveillance:type"="ALPR"](area.wa);
  node["operator"~"Flock",i](area.wa);
);
out body;
"""


def load_eyesonflock_data():
    """Load local eyesonflock JSON dataset."""
    if not EYESONFLOCK_FILE.exists():
        print(f"Warning: {EYESONFLOCK_FILE} not found. Skipping EyesOnFlock seeding.")
        return []
    with open(EYESONFLOCK_FILE) as f:
        data = json.load(f)
    return data.get("portals", [])


def fetch_osm_wa_cameras(force_refresh=False):
    """Fetch all ALPR / Flock camera nodes in Washington State from OpenStreetMap Overpass API."""
    if OSM_CACHE_FILE.exists() and not force_refresh:
        print(f"Loading cached Washington State OSM cameras from {OSM_CACHE_FILE}")
        with open(OSM_CACHE_FILE) as f:
            return json.load(f)

    print("Fetching Washington State ALPR/Flock cameras from OpenStreetMap Overpass API...")
    req = urllib.request.Request(
        OVERPASS_ENDPOINT,
        data=OVERPASS_WA_QUERY.encode("utf-8"),
        headers={"User-Agent": "FlockTransparencyResearch/1.0 (https://github.com/pmocek/scrape-flock-safety-subscriber-portals)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
        elements = data.get("elements", [])
        print(f"Successfully fetched {len(elements)} camera nodes from OpenStreetMap.")
        OSM_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OSM_CACHE_FILE, "w") as f:
            json.dump(elements, f, indent=2)
        return elements
    except Exception as e:
        print(f"Error fetching from Overpass API: {e}")
        if OSM_CACHE_FILE.exists():
            print("Falling back to existing cache.")
            with open(OSM_CACHE_FILE) as f:
                return json.load(f)
        return []


def normalize_osm_operator(op_name):
    """Clean and normalize an OSM operator name into candidate portal slugs."""
    if not op_name:
        return []

    # Filter out known commercial retail chains and utility transit
    commercial_terms = [
        "home depot", "lowe", "safeway", "kroger", "fred meyer", "costco",
        "walmart", "target", "dick's", "dicks", "great wolf lodge", "winco",
        "wsdot", "department of transportation", "usps", "fedex", "gated community"
    ]
    op_lower = op_name.lower().strip()
    for comm in commercial_terms:
        if comm in op_lower:
            return []

    candidates = set()

    # Base clean
    cleaned = re.sub(r"[\[\]\(\)\'\"]", "", op_lower)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Detect Agency Type
    is_so = any(t in cleaned for t in ["sheriff", "so"])
    is_pd = any(t in cleaned for t in ["police", "pd", "dept", "department"])

    # Extract primary jurisdiction name
    jurisdiction = cleaned
    for drop in [
        "police department", "police dept.", "police dept", "police", "pd",
        "sheriffs office", "sheriff office", "sheriffs department",
        "sheriff dept", "sheriff", "so", "city of", "town of", "village of"
    ]:
        jurisdiction = re.sub(rf"\b{re.escape(drop)}\b", "", jurisdiction).strip()

    jurisdiction_slug = re.sub(r"[^\w\s-]", "", jurisdiction)
    jurisdiction_slug = re.sub(r"\s+", "-", jurisdiction_slug).strip("-")

    if not jurisdiction_slug or len(jurisdiction_slug) < 3:
        return []

    # Generate standard Flock naming patterns in Washington State
    if is_so:
        candidates.add(f"{jurisdiction_slug}-wa-so")
        candidates.add(f"{jurisdiction_slug}-so-wa")
        candidates.add(f"-{jurisdiction_slug}-wa-so")
        if not jurisdiction_slug.endswith("-county"):
            candidates.add(f"{jurisdiction_slug}-county-wa-so")
            candidates.add(f"{jurisdiction_slug}-county-so-wa")
    elif is_pd:
        candidates.add(f"{jurisdiction_slug}-wa-pd")
        candidates.add(f"{jurisdiction_slug}-pd-wa")
        candidates.add(f"city-of-{jurisdiction_slug}-wa-pd")
        candidates.add(f"{jurisdiction_slug}-wa-pd-")
    else:
        # Fallback combinations
        candidates.add(f"{jurisdiction_slug}-wa-pd")
        candidates.add(f"{jurisdiction_slug}-wa-so")

    return sorted(list(candidates))


def main():
    parser = argparse.ArgumentParser(description="Seed agency slugs and metadata from aggregators")
    parser.add_argument("--fetch-osm", action="store_true", help="Force fresh download from OpenStreetMap Overpass API")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load current agency list
    known_agencies = set()
    if AGENCIES_FILE.exists():
        with open(AGENCIES_FILE) as f:
            known_agencies = set(json.load(f))
    initial_count = len(known_agencies)
    print(f"Current agency count in {AGENCIES_FILE.name}: {initial_count}")

    # 2. Ingest EyesOnFlock data
    eof_portals = load_eyesonflock_data()
    registry = {}
    if PORTAL_REGISTRY_FILE.exists():
        try:
            with open(PORTAL_REGISTRY_FILE) as f:
                registry = json.load(f)
        except Exception:
            registry = {}

    eof_new_slugs = set()
    for p in eof_portals:
        portal_url = p.get("portal_url", "").strip()
        if not portal_url:
            continue
        slug = portal_url.split("/")[-1].strip()
        if not slug:
            continue

        if slug not in known_agencies:
            eof_new_slugs.add(slug)
            known_agencies.add(slug)

        # Store metadata
        registry[slug] = {
            "source": "eyesonflock",
            "portal_url": portal_url,
            "city": p.get("city"),
            "county": p.get("county"),
            "state": p.get("state"),
            "population": p.get("population"),
            "type": p.get("type"),
            "total_cameras": p.get("total_cameras"),
            "total_searches": p.get("total_searches"),
            "data_retention_days": p.get("data_retention"),
            "vehicles_captured": p.get("vehicles_captured"),
            "hotlist_hits": p.get("hotlist_hits"),
            "hotlist_hit_rate": p.get("hotlist_hit_rate"),
            "organizations_shared_with_count": len(p.get("organizations_shared_with") or []),
            "last_updated_aggregator": p.get("data_last_updated"),
        }

    print(f"EyesOnFlock: Ingested {len(eof_portals)} portals. Added {len(eof_new_slugs)} new verified slugs to agency pool.")

    # 3. Ingest OpenStreetMap / DeFlock data
    osm_elements = fetch_osm_wa_cameras(force_refresh=args.fetch_osm)
    osm_operator_counts = {}
    osm_candidates_map = {}
    osm_new_slugs = set()

    for el in osm_elements:
        op = el.get("tags", {}).get("operator")
        if not op:
            continue
        osm_operator_counts[op] = osm_operator_counts.get(op, 0) + 1

    print(f"OpenStreetMap: Found {len(osm_operator_counts)} distinct operators across {len(osm_elements)} WA cameras.")

    for op, count in sorted(osm_operator_counts.items(), key=lambda x: x[1], reverse=True):
        candidate_slugs = normalize_osm_operator(op)
        if not candidate_slugs:
            continue

        osm_candidates_map[op] = {
            "camera_count": count,
            "candidate_slugs": candidate_slugs,
        }

        for c_slug in candidate_slugs:
            if c_slug not in known_agencies:
                osm_new_slugs.add(c_slug)
                known_agencies.add(c_slug)

    print(f"OpenStreetMap: Generated candidate slugs for {len(osm_candidates_map)} LEA operators. Added {len(osm_new_slugs)} new candidates.")

    # Save OSM candidates metadata
    with open(OSM_CANDIDATES_FILE, "w") as f:
        json.dump(osm_candidates_map, f, indent=2)
    print(f"Saved OSM candidate mappings to {OSM_CANDIDATES_FILE}")

    # Save updated Portal Registry
    with open(PORTAL_REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"Saved unified portal registry ({len(registry)} entries) to {PORTAL_REGISTRY_FILE}")

    # Save updated wa-agencies.json
    updated_agencies = sorted(list(known_agencies))
    with open(AGENCIES_FILE, "w") as f:
        json.dump(updated_agencies, f, indent=2)

    # Export confirmed live WA portals from data/
    confirmed_wa = []
    for d in DATA_DIR.iterdir():
        if not d.is_dir():
            continue
        sf = d / "stats.jsonl"
        pf = d / "page.txt"
        if sf.exists() and pf.exists():
            try:
                with open(sf) as f:
                    lines = f.readlines()
                    if lines:
                        last = json.loads(lines[-1])
                        slug = d.name
                        if "-wa" in slug or "wa-" in slug or slug.endswith("-wa"):
                            confirmed_wa.append({
                                "slug": slug,
                                "page_name": last.get("page_name"),
                                "total_cameras": last.get("total_cameras"),
                                "portal_status": last.get("portal_status", "active"),
                            })
            except Exception:
                pass

    confirmed_wa.sort(key=lambda x: x["slug"])
    with open(DATA_DIR / "wa-confirmed-portals.json", "w") as f:
        json.dump(confirmed_wa, f, indent=2)
    print(f"Exported {len(confirmed_wa)} confirmed live WA portals to {DATA_DIR / 'wa-confirmed-portals.json'}")

    added_total = len(updated_agencies) - initial_count
    print(f"\nCompleted Seeding:")
    print(f"  Initial agencies: {initial_count}")
    print(f"  New from EyesOnFlock: {len(eof_new_slugs)}")
    print(f"  New from OSM/DeFlock: {len(osm_new_slugs)}")
    print(f"  Total agencies in {AGENCIES_FILE.name}: {len(updated_agencies)} (+{added_total})")


if __name__ == "__main__":
    main()
