#!/usr/bin/env python3
"""Export per-agency time series data from stats.jsonl for D3.js charts."""
import json, os, glob, sys

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
output_dir = os.path.join(os.path.dirname(__file__), '..', 'website', 'data', 'series')
os.makedirs(output_dir, exist_ok=True)

count = 0
for stats_path in sorted(glob.glob(os.path.join(data_dir, '*', 'stats.jsonl'))):
    slug = os.path.basename(os.path.dirname(stats_path))
    
    # Collect all non-empty entries with numeric fields
    entries = []
    total_cameras = None
    portal_status = None
    
    for line in open(stats_path):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        ts = obj.get('ts')
        if not ts:
            continue
            
        record = {"ts": ts}
        
        if 'total_cameras' in obj:
            record['cameras'] = obj['total_cameras']
            total_cameras = obj['total_cameras']
        if 'vehicles_30d' in obj and obj['vehicles_30d']:
            record['vehicles'] = obj['vehicles_30d']
        if 'searches_30d' in obj and obj['searches_30d']:
            record['searches'] = obj['searches_30d']
        if 'hotlist_hits_30d' in obj and obj['hotlist_hits_30d']:
            record['hotlist_hits'] = obj['hotlist_hits_30d']
        if 'portal_status' in obj:
            portal_status = obj['portal_status']
            record['status'] = portal_status
        if 'page_name' in obj:
            record['name'] = obj['page_name']
        
        # Only include records that have actual data values
        has_data = any(k in record for k in ['cameras','vehicles','searches','hotlist_hits','status'])
        if has_data:
            entries.append(record)
    
    # Write aggregated series only if we have data points
    if entries:
        output_file = os.path.join(output_dir, f"{slug}.json")
        with open(output_file, 'w') as f:
            json.dump({
                "slug": slug,
                "name": portal_status and entries[-1].get('name', slug.replace('-', ' ').title()) or slug,
                "last_updated": entries[-1]['ts'] if entries else None,
                "entries": entries[:200]  # Cap at 200 points for performance
            }, f, indent=2)
        count += 1

print(f"Exported time series for {count} agencies → website/data/series/")
