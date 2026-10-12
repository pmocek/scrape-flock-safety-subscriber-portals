#!/usr/bin/env python3
"""Aggregate all stats.jsonl into site-wide dashboard data."""
import json, os, glob
from collections import defaultdict

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
output_path = os.path.join(os.path.dirname(__file__), '..', 'website', 'data', 'site-stats.json')

agencies = []  # list of {slug, name, status, cameras, vehicles, searches, sharing_partners}
total_cameras = 0
total_searches = 0
status_counts = defaultdict(int)

COMMON_ABBREVS = {
    'wa': 'WA', 'pd': 'PD', 'so': 'SO', 'ca': 'CA', 'tx': 'TX', 'fl': 'FL', 'ga': 'GA',
    'oh': 'OH', 'il': 'IL', 'nc': 'NC', 'va': 'VA', 'sc': 'SC', 'tn': 'TN', 'in': 'IN',
    'co': 'CO', 'az': 'AZ', 'ny': 'NY', 'or': 'OR', 'nv': 'NV', 'id': 'ID', 'ks': 'KS',
    'mo': 'MO', 'mi': 'MI', 'al': 'AL', 'pa': 'PA', 'ky': 'KY', 'mn': 'MN', 'wi': 'WI',
    'ia': 'IA', 'ar': 'AR', 'la': 'LA', 'ms': 'MS', 'ct': 'CT', 'ne': 'NE', 'nm': 'NM',
    'wv': 'WV', 'nj': 'NJ', 'ma': 'MA', 'ut': 'UT', 'ok': 'OK', 'hi': 'HI', 'ak': 'AK',
    'md': 'MD', 'de': 'DE', 'vt': 'VT', 'nh': 'NH', 'me': 'ME', 'ri': 'RI', 'nd': 'ND',
    'sd': 'SD', 'mt': 'MT', 'wy': 'WY', 'dot': 'DOT', 'dps': 'DPS', 'csu': 'CSU',
    'uc': 'UC', 'unlv': 'UNLV', 'fbi': 'FBI', 'ice': 'ICE', 'cbp': 'CBP'
}

def clean_agency_name(slug, raw_name):
    if raw_name:
        lower = raw_name.strip().lower()
        if not any(bad in lower for bad in ["doesn't exist", "does not exist", "<error>", "access denied", "just a moment", "404", "error 1015", "cloudflare"]):
            return raw_name.strip()
    parts = slug.split('-')
    cleaned_parts = [COMMON_ABBREVS.get(p.lower(), p.capitalize()) for p in parts if p]
    return ' '.join(cleaned_parts)

for stats_path in sorted(glob.glob(os.path.join(data_dir, '*', 'stats.jsonl'))):
    slug = os.path.basename(os.path.dirname(stats_path))
    latest = None
    for line in open(stats_path):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Prefer entries with portal_status; take the last valid one
        if 'portal_status' in obj or 'page_name' in obj:
            latest = obj
    
    if not latest:
        continue
    
    status = latest.get('portal_status', 'unknown')
    status_counts[status] += 1
    
    name = clean_agency_name(slug, latest.get('page_name'))
    cameras = latest.get('total_cameras', 0) or 0
    vehicles = latest.get('vehicles_30d', 0) or 0
    searches = latest.get('searches_30d', 0) or 0
    sharing = latest.get('external_agencies_count', 0) or 0
    
    if status != 'not_found':
        total_cameras += cameras
        total_searches += searches
    
    agencies.append({
        'slug': slug,
        'name': name,
        'status': status,
        'cameras': cameras,
        'vehicles_30d': vehicles,
        'searches_30d': searches,
        'sharing_partners': sharing,
    })

# Sort: active agencies first (by camera count descending), then inactive, then not_found
def agency_sort_key(a):
    status_order = {'active': 0, 'inactive': 1, 'not_found': 2, 'unknown': 3}
    return (status_order.get(a['status'], 9), -a['cameras'], a['name'])

agencies.sort(key=agency_sort_key)

result = {
    'total_portals': len(agencies),
    'active': status_counts.get('active', 0),
    'inactive': status_counts.get('inactive', 0),
    'not_found': status_counts.get('not_found', 0),
    'total_cameras': total_cameras,
    'total_searches': total_searches,
    'agencies': agencies,
}

stats_output_path = os.path.join(os.path.dirname(__file__), '..', 'website', 'data', 'stats.json')
for p in [output_path, stats_output_path]:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        json.dump(result, f, indent=2)

print(f"Aggregated {len(agencies)} agencies → {stats_output_path}")
print(f"  Active: {status_counts.get('active',0)}, Inactive: {status_counts.get('inactive',0)}, Not found: {status_counts.get('not_found',0)}")
print(f"  Total cameras: {total_cameras}, Total searches: {total_searches}")
