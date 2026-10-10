#!/usr/bin/env python3
"""Export aggregated search reason data for audit breakdown chart."""
import json, os, glob, re
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'website', 'data', 'audit-data.json')

reason_counter = Counter()
total_searches = 0
total_audit_entries = 0

# Categories from analyze-audit.py patterns
CATEGORIES = {
    'Warrant': r'\bwarrant\b|\bwarrent\b',
    'Stolen Vehicle': r'\bstolen\b|theft|\bTP\b|\brecovery\b',
    'Traffic Incident': r'\bincident\b|accident|collision|\bfatal\b',
    'Person of Interest': r'\bperson of interest\b|POI|BOLO|\blookout\b',
    'DMV Lookup': r'\bdmv\b|registration|vehicle history',
    'Towing Recovery': r'\btow\b|impound|retrieval',
    'License Check': r'\blicense\s*check\b|\blinkage check\b|\bcamera check\b',
    'Immigration Search': r'\bimmigrat\b|ice\b|\bborder patrol\b|usbp\b|customs\b',
    'Other': r'.*',
}

for stats_path in sorted(glob.glob(os.path.join(DATA_DIR, '*', 'audit.csv'))):
    agency_slug = os.path.basename(os.path.dirname(stats_path))
    
    try:
        with open(stats_path) as f:
            lines = f.readlines()
        
        # Skip header line if present
        if lines and 'date' in lines[0].lower():
            lines = lines[1:]
            
        total_audit_entries += len(lines)
        
        for line in lines:
            line = line.strip().lower()
            if not line or line == '"search_date"':
                continue
            
            # Match against categories (first match wins)
            matched = False
            for category, pattern in CATEGORIES.items():
                if category == 'Other':
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    reason_counter[f"{agency_slug}:{category}"] += 1
                    matched = True
                    break
            
            if not matched:
                reason_counter[f"{agency_slug}:Other"] += 1
                
    except Exception:
        pass

# Aggregate across agencies by category
by_category = {}
for key, count in reason_counter.items():
    _, category = key.split(':', 1)
    by_category[category] = by_category.get(category, 0) + count

result = {
    'total_searches': total_searches,
    'total_audit_entries': total_audit_entries,
    'categories': dict(sorted(by_category.items(), key=lambda x: -x[1])[:20]),
}

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, 'w') as f:
    json.dump(result, f, indent=2)

print(f"Audit data → {OUTPUT_FILE}")
print(f"  Total audit entries: {total_audit_entries}")
print(f"  Top categories:")
for cat, count in list(by_category.items())[:5]:
    print(f"    {cat}: {count}")
