#!/usr/bin/env python3
"""Ad-hoc verification: directional sharing data parsing in scrape-flock.py."""
import tempfile, os, sys, json, re

repo = os.path.expanduser("~/sandbox/pmocek/scrape-flock-safety-subscriber-portals")

# 1. Verify parse_stats() produces directional fields
# Replicate the exact parse_stats logic from the updated file
exec(open(os.path.join(repo, "scrape-flock.py")).read().split("def main")[0])

err = []

# Test with a page that has both sections (like Yelm)
yelm_txt = open(os.path.join(repo, "data/yelm-wa-pd/page.txt")).read()
stats = parse_stats(yelm_txt)

c = lambda cond, msg: err.append(msg) if not cond else None
c('shares_data_with' in stats, "missing shares_data_with")
c('receives_data_from' in stats, "missing receives_data_from")
c('external_agencies' in stats, "missing external_agencies (backward compat)")
c('external_agencies_count' in stats, "missing external_agencies_count")
c(len(stats.get('shares_data_with', [])) >= 80, f"too few shares_with ({len(stats.get('shares_data_with', []))})")
c(len(stats.get('receives_data_from', [])) >= 300, f"too few receives_from ({len(stats.get('receives_data_from', []))})")

# Verify union = shares_with + receives_from deduped
sw = set(stats['shares_data_with'])
rf = set(stats['receives_data_from'])
union = sw | rf
c(len(stats['external_agencies']) == len(union), f"external_agencies size {len(stats['external_agencies'])} != union {len(union)}")

# Test with an agency that has only one section
auburn_txt = open(os.path.join(repo, "data/auburn-wa-pd/page.txt")).read()
stats2 = parse_stats(auburn_txt)
c('shares_data_with' in stats2, "auburn: missing shares_data_with")
# Auburn has only one section; the other field should simply be absent
c('receives_data_from' not in stats2, "auburn: receives_from should be absent (section missing)")
c('external_agencies' in stats2, "auburn: missing external_agencies")
c('external_agencies_count' in stats2, "auburn: missing external_agencies_count")

# 2. Verify sharing-relationships.json exists and has entries
rel_path = os.path.join(repo, "data/sharing-relationships.json")
c(os.path.exists(rel_path), "sharing-relationships.json missing")
if os.path.exists(rel_path):
    with open(rel_path) as f:
        rels = json.load(f)
    c(len(rels) > 1500, f"too few relationships ({len(rels)})")
    c(all('source_slug' in r and 'partner_name' in r and 'direction' in r for r in rels[:10]),
      "relationship schema wrong")

# 3. Verify ADR exists
adr_path = os.path.join(repo, "adr/001-directional-sharing-data.md")
c(os.path.exists(adr_path), "ADR missing")

if err:
    for e in err:
        print(f"FAIL: {e}")
    sys.exit(1)
print("PASS: directional parse_stats, backward compat, relationships file, ADR all OK")
