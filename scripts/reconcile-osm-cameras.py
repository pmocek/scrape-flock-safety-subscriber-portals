#!/usr/bin/env python3
"""
Reconcile physical ALPR camera deployments from OpenStreetMap (DeFlock crowdsourced data)
against vendor transparency portal disclosures in data/*/stats.jsonl.

Identifies:
1. Agencies with physical cameras mapped in OSM but NO public transparency portal.
2. Discrepancies between community-mapped cameras and official disclosed counts.
3. Commercial / private camera networks feeding regional surveillance.

Usage:
    python3 scripts/reconcile-osm-cameras.py
    python3 scripts/reconcile-osm-cameras.py --commit-body
    python3 scripts/reconcile-osm-cameras.py --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
OSM_CACHE_FILE = DATA_DIR / "osm-alpr-wa.json"
OSM_CANDIDATES_FILE = DATA_DIR / "wa-osm-candidates.json"


def load_latest_portal_stats():
    """Load latest stats.jsonl record for each agency directory in data/."""
    stats_by_slug = {}
    if not DATA_DIR.exists():
        return stats_by_slug

    for slug_dir in DATA_DIR.iterdir():
        if not slug_dir.is_dir():
            continue
        stats_file = slug_dir / "stats.jsonl"
        if not stats_file.exists():
            continue

        try:
            with open(stats_file) as f:
                lines = f.readlines()
                if not lines:
                    continue
                last_line = json.loads(lines[-1])
                stats_by_slug[slug_dir.name] = last_line
        except Exception:
            pass

    return stats_by_slug


def normalize_string(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_core_tokens(s):
    stop = {
        "police", "dept", "department", "sheriff", "sheriffs", "sherrif", "office",
        "city", "town", "village", "of", "wa", "so", "pd", "co", "county"
    }
    return [w for w in normalize_string(s).split() if w not in stop and len(w) >= 3]


def match_osm_operator_to_portal(op_name, portals):
    """Fuzzy match an OSM operator string to a scraped portal in Washington State."""
    tokens = extract_core_tokens(op_name)
    if not tokens:
        return None, None

    is_so = any(t in op_name.lower() for t in ["sheriff", "sherrif", "so", "county"])
    is_pd = any(t in op_name.lower() for t in ["police", "pd", "dept", "city"])

    found_slug = None
    for slug in portals:
        # Prioritize Washington State portals
        if not ("-wa" in slug or "wa-" in slug or slug.endswith("-wa")):
            continue

        slug_tokens = extract_core_tokens(slug)
        if all(t in slug_tokens for t in tokens):
            slug_is_so = "so" in slug
            if is_so and slug_is_so:
                return slug, portals[slug]
            elif is_pd and not slug_is_so:
                return slug, portals[slug]
            elif not found_slug:
                found_slug = slug

    if found_slug:
        return found_slug, portals[found_slug]

    return None, None


def main():
    parser = argparse.ArgumentParser(description="Reconcile OpenStreetMap cameras against portal stats")
    parser.add_argument("--commit-body", action="store_true", help="Emit COMMIT_BODY lines for CI")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    if not OSM_CACHE_FILE.exists():
        print(f"Error: {OSM_CACHE_FILE} not found. Run scripts/seed-from-aggregators.py first.", file=sys.stderr)
        sys.exit(1)

    with open(OSM_CACHE_FILE) as f:
        osm_elements = json.load(f)

    portals = load_latest_portal_stats()

    # Aggregate OSM counts by operator
    operator_counts = {}
    commercial_counts = {}
    commercial_terms = [
        "home depot", "lowe", "safeway", "kroger", "fred meyer", "costco",
        "walmart", "target", "dick's", "dicks", "great wolf lodge", "winco",
        "wsdot", "department of transportation", "usps", "fedex", "gated community"
    ]

    for el in osm_elements:
        op = el.get("tags", {}).get("operator", "Unknown / Unspecified").strip()
        is_comm = any(term in op.lower() for term in commercial_terms)
        if is_comm:
            commercial_counts[op] = commercial_counts.get(op, 0) + 1
        else:
            operator_counts[op] = operator_counts.get(op, 0) + 1

    reconciled = []
    unmatched_leas = []

    for op, osm_count in sorted(operator_counts.items(), key=lambda x: x[1], reverse=True):
        if op in ("Unknown / Unspecified", "Flock Safety"):
            continue

        matched_slug, portal_data = match_osm_operator_to_portal(op, portals)

        if matched_slug and portal_data:
            disclosed = portal_data.get("total_cameras")
            status = portal_data.get("portal_status", "active")
            reconciled.append({
                "operator": op,
                "slug": matched_slug,
                "portal_status": status,
                "osm_cameras": osm_count,
                "disclosed_cameras": disclosed,
                "page_name": portal_data.get("page_name"),
            })
        else:
            unmatched_leas.append({
                "operator": op,
                "osm_cameras": osm_count,
            })

    if args.json:
        report = {
            "total_osm_cameras": len(osm_elements),
            "unspecified_operator_cameras": operator_counts.get("Unknown / Unspecified", 0),
            "commercial_network_cameras": sum(commercial_counts.values()),
            "commercial_networks": commercial_counts,
            "reconciled_portals": reconciled,
            "operators_without_portal": unmatched_leas,
        }
        print(json.dumps(report, indent=2))
        return

    # Text report
    print(f"==================================================================")
    print(f" WASHINGTON STATE ALPR RECONCILIATION: OSM (DeFlock) vs. PORTALS")
    print(f"==================================================================")
    print(f"Total Mapped OSM Cameras: {len(osm_elements)}")
    print(f"Unspecified Operator Cameras: {operator_counts.get('Unknown / Unspecified', 0)}")
    print(f"Commercial Storefront Cameras: {sum(commercial_counts.values())}")
    print()

    print(f"{'OPERATOR (OSM)':<32} {'SLUG':<26} {'OSM':<6} {'PORTAL':<8} {'DIFF':<6}")
    print("-" * 80)

    discrepancies = []
    for item in reconciled:
        disclosed = item["disclosed_cameras"]
        disclosed_str = str(disclosed) if disclosed is not None else "N/A"
        diff_str = "N/A"
        if isinstance(disclosed, int):
            diff = item["osm_cameras"] - disclosed
            diff_str = f"{diff:+d}" if diff != 0 else "0"
            if abs(diff) >= 3:
                discrepancies.append((item["operator"], item["osm_cameras"], disclosed))

        print(f"{item['operator'][:31]:<32} {item['slug'][:25]:<26} {item['osm_cameras']:<6} {disclosed_str:<8} {diff_str:<6}")

    print()
    print("=" * 80)
    print(" LAW ENFORCEMENT OPERATORS WITH PHYSICAL CAMERAS BUT NO CONFIRMED PORTAL")
    print("=" * 80)
    for u in unmatched_leas:
        print(f"  * {u['operator']}: {u['osm_cameras']} cameras in OSM (no verified portal)")

    print()
    print("=" * 80)
    print(" COMMERCIAL RETAIL / BUSINESS FLOCK NETWORKS IN OSM")
    print("=" * 80)
    for c_op, c_cnt in sorted(commercial_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  * {c_op}: {c_cnt} cameras")

    if args.commit_body:
        print("\n--- COMMIT_BODY ---")
        if unmatched_leas:
            top_unmatched = [f"{u['operator']} ({u['osm_cameras']} cams)" for u in unmatched_leas[:5]]
            print(f"COMMIT_BODY: OSM unindexed operators: {', '.join(top_unmatched)}")
        if discrepancies:
            top_disc = [f"{op} (OSM: {osm} vs Portal: {disc})" for op, osm, disc in discrepancies[:4]]
            print(f"COMMIT_BODY: OSM vs Portal discrepancies: {', '.join(top_disc)}")


if __name__ == "__main__":
    main()
