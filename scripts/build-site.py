#!/usr/bin/env python3
"""
build-site.py - Compiles scraped ALPR portal statistics, Maass Contradiction analysis,
multi-hop sharing network topology, and health check records into Hugo content and data files.
"""

import json
import os
import glob
import re
import shutil
import sys
import importlib
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
SITE_DIR = PROJECT_DIR / "site"
CONTENT_DIR = SITE_DIR / "content"
DATA_SITE_DIR = SITE_DIR / "data"

sys.path.insert(0, str(PROJECT_DIR / "scripts"))
ncic = importlib.import_module("ncic-contradiction")

def clean_site_content():
    """Remove and recreate site content and data directories."""
    for d in [CONTENT_DIR / "agencies", CONTENT_DIR / "contradictions", CONTENT_DIR / "sharing-network", CONTENT_DIR / "health", CONTENT_DIR / "downloads", DATA_SITE_DIR]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

def load_agency_stats():
    """Load latest stats and metadata for all scraped agencies in data/*."""
    agencies = {}
    total_vehicles = 0
    total_cameras = 0
    total_searches = 0
    total_hotlist_hits = 0
    
    prohib_count = 0
    no_prohib_count = 0

    for stat_file in glob.glob(str(DATA_DIR / "*" / "stats.jsonl")):
        slug = Path(stat_file).parent.name
        with open(stat_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            if not lines:
                continue
            latest = json.loads(lines[-1])
            
            # Read external agency sharing partners from page.txt if available
            page_txt_file = DATA_DIR / slug / "page.txt"
            sharing_partners = []
            if page_txt_file.exists():
                txt_content = page_txt_file.read_text(encoding="utf-8")
                if "Sharing Network Data With" in txt_content:
                    part = txt_content.split("Sharing Network Data With", 1)[1]
                    if "Policy & Trust" in part:
                        part = part.split("Policy & Trust", 1)[0]
                    partner_lines = [l.strip() for l in part.split("\n") if l.strip() and not l.strip().startswith("Organizations granted")]
                    sharing_partners = partner_lines

            veh = latest.get("vehicles_30d", 0) or 0
            cams = latest.get("total_cameras", 0) or 0
            srch = latest.get("searches_30d", 0) or 0
            hits = latest.get("hotlist_hits_30d", 0) or 0
            prohibited = latest.get("prohibited_uses", "") or ""
            
            has_imm_prohib = ncic.prohibits_immigration(prohibited)
            if has_imm_prohib:
                prohib_count += 1
            else:
                no_prohib_count += 1

            total_vehicles += veh
            total_cameras += cams
            total_searches += srch
            total_hotlist_hits += hits

            agencies[slug] = {
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "vehicles_30d": veh,
                "total_cameras": cams,
                "searches_30d": srch,
                "hotlist_hits_30d": hits,
                "retention_days": latest.get("retention_days", "N/A"),
                "prohibited_uses": prohibited,
                "acceptable_use": latest.get("acceptable_use", ""),
                "access_policy": latest.get("access_policy", ""),
                "has_immigration_prohibition": has_imm_prohib,
                "sharing_partners": sharing_partners,
                "sharing_partners_count": len(sharing_partners),
                "last_updated": latest.get("ts", "")
            }

    return agencies, {
        "scraped_portals_count": len(agencies),
        "total_cameras": total_cameras,
        "total_vehicles_30d": total_vehicles,
        "total_searches_30d": total_searches,
        "total_hotlist_hits_30d": total_hotlist_hits,
        "prohibiting_agencies_count": prohib_count,
        "non_prohibiting_agencies_count": no_prohib_count,
    }

def run_ncic_analysis_direct():
    """Extract Maass Contradictions and multi-hop chains directly using ncic-contradiction module."""
    stats = ncic.load_latest_stats()
    eof_data = ncic.load_eyesonflock()
    
    contradictions = []
    for slug, s in sorted(stats.items()):
        pu = s.get("prohibited_uses", "") or ""
        hotlists = s.get("hotlists", "") or ""
        if ncic.prohibits_immigration(pu) and ncic.has_national_hotlist(hotlists):
            contradictions.append({
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "cameras": s.get("total_cameras", 0) or 0,
                "vehicles_30d": s.get("vehicles_30d", 0) or 0,
                "prohibited_uses": pu,
                "hotlists": hotlists
            })

    non_prohib_slugs = {s for s in stats if not ncic.prohibits_immigration(stats[s].get("prohibited_uses", "") or "")}

    indirect_chains = []
    if eof_data:
        name_to_slug = ncic._build_name_to_slug_map(eof_data)
        graph = ncic.build_sharing_graph(set(stats), eof_data, name_to_slug)
        seen_pairs = set()
        for slug in sorted(stats):
            paths = ncic.find_indirect_paths(graph, slug, non_prohib_slugs, 5)
            for path in paths:
                pair = (slug, path[-1])
                if pair not in seen_pairs and len(path) > 2:
                    seen_pairs.add(pair)
                    indirect_chains.append({
                        "start_slug": slug,
                        "target_slug": path[-1],
                        "hops": len(path) - 1,
                        "path": path,
                        "path_display": " → ".join(path)
                    })

    return contradictions, indirect_chains

def build_hugo_files(agencies, summary_stats, contradictions, indirect_chains):
    """Write Hugo content files (.md) and JSON data files."""
    
    # 1. Summary JSON for site data
    summary_data = {
        "stats": summary_stats,
        "maass_contradictions_count": len(contradictions),
        "indirect_chains_count": len(indirect_chains),
        "candidate_queue_count": 5972
    }
    with open(DATA_SITE_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    with open(DATA_SITE_DIR / "contradictions.json", "w", encoding="utf-8") as f:
        json.dump(contradictions, f, indent=2)

    with open(DATA_SITE_DIR / "indirect_chains.json", "w", encoding="utf-8") as f:
        json.dump(indirect_chains, f, indent=2)

    # 2. Main Index Page
    index_md = (CONTENT_DIR / "_index.md")
    index_md.write_text(f"""---
title: "Nationwide ALPR Portal Transparency Project"
layout: "index"
---
""", encoding="utf-8")

    # 3. Agency Directory Page
    agencies_index_md = (CONTENT_DIR / "agencies" / "_index.md")
    agencies_index_md.write_text(f"""---
title: "Scraped Agency Directory"
layout: "list"
---
""", encoding="utf-8")

    for slug, info in agencies.items():
        agency_file = CONTENT_DIR / "agencies" / f"{slug}.md"
        agency_file.write_text(f"""---
title: "{info['name']}"
slug: "{slug}"
vehicles_30d: {info['vehicles_30d']}
total_cameras: {info['total_cameras']}
searches_30d: {info['searches_30d']}
hotlist_hits_30d: {info['hotlist_hits_30d']}
retention_days: "{info['retention_days']}"
has_immigration_prohibition: {str(info['has_immigration_prohibition']).lower()}
sharing_partners_count: {info['sharing_partners_count']}
last_updated: "{info['last_updated']}"
---

### Policy Overview
* **Prohibited Uses**: {info['prohibited_uses'] or 'None specified'}
* **Acceptable Use**: {info['acceptable_use'] or 'Standard law enforcement usage'}
* **Access Policy**: {info['access_policy'] or 'Reason required'}

### Direct External Sharing Network ({info['sharing_partners_count']} Agencies)
{"".join([f"- {p}\\n" for p in info['sharing_partners']])}
""", encoding="utf-8")

    # 4. Maass Contradictions Page
    contradictions_md = (CONTENT_DIR / "contradictions" / "_index.md")
    contradictions_md.write_text(f"""---
title: "Maass Contradiction Index ({len(contradictions)} Agencies)"
layout: "list"
---
Documenting agencies that explicitly prohibit immigration enforcement in their public Flock Safety portal policy while simultaneously subscribing to NCIC National Hotlists (which query the FBI NCIC Immigration Violator File).
""", encoding="utf-8")

    # 5. Sharing Network Page
    sharing_md = (CONTENT_DIR / "sharing-network" / "_index.md")
    sharing_md.write_text(f"""---
title: "Interstate Multi-Hop Sharing Network ({len(indirect_chains)} Chains)"
layout: "list"
---
Tracing multi-hop data sharing paths showing how local ALPR plate reads leak across state boundaries from sanctuary jurisdictions to non-prohibiting partner agencies nationwide.
""", encoding="utf-8")

    # 6. Health Page
    health_md = (CONTENT_DIR / "health" / "_index.md")
    health_md.write_text(f"""---
title: "Portal Health & Reachability Matrix"
layout: "list"
---
Monitoring active, rate-limited, and unreachable subscriber portals.
""", encoding="utf-8")

    # 7. Downloads Page
    downloads_md = (CONTENT_DIR / "downloads" / "_index.md")
    downloads_md.write_text(f"""---
title: "Raw Data & Report Exports"
layout: "list"
---
Download raw aggregated JSON and CSV datasets for researchers, legal auditors, and community advocates.
""", encoding="utf-8")

def main():
    print("Cleaning and initializing Hugo site directory...")
    clean_site_content()
    
    print("Extracting agency statistics...")
    agencies, summary_stats = load_agency_stats()
    print(f"Loaded {len(agencies)} agency profiles ({summary_stats['total_cameras']:,} cameras, {summary_stats['total_vehicles_30d']:,} vehicle reads).")
    
    print("Running NCIC contradiction & multi-hop analysis...")
    contradictions, indirect_chains = run_ncic_analysis_direct()
    print(f"Found {len(contradictions)} Maass Contradiction agencies and {len(indirect_chains)} multi-hop sharing paths.")
    
    print("Generating Hugo Markdown content and JSON data assets...")
    build_hugo_files(agencies, summary_stats, contradictions, indirect_chains)
    print("Site content compilation complete!")

if __name__ == "__main__":
    main()
