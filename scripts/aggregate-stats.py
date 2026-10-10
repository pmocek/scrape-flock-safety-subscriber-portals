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
    
    name = latest.get('page_name', slug.replace('-', ' ').title())
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

result = {
    'total_portals': len(agencies),
    'active': status_counts.get('active', 0),
    'inactive': status_counts.get('inactive', 0),
    'not_found': status_counts.get('not_found', 0),
    'total_cameras': total_cameras,
    'total_searches': total_searches,
    'agencies': agencies,
}

os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w') as f:
    json.dump(result, f, indent=2)

print(f"Aggregated {len(agencies)} agencies → {output_path}")
print(f"  Active: {status_counts.get('active',0)}, Inactive: {status_counts.get('inactive',0)}, Not found: {status_counts.get('not_found',0)}")
print(f"  Total cameras: {total_cameras}, Total searches: {total_searches}")
