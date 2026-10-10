#!/usr/bin/env python3
"""Generate Hugo content files for each active portal from aggregated stats."""
import json, os

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', 'website', 'data', 'stats.json')
CONTENT_DIR = os.path.join(os.path.dirname(__file__), '..', 'website', 'content', 'agencies')

with open(DATA_FILE) as f:
    data = json.load(f)

os.makedirs(CONTENT_DIR, exist_ok=True)

for agency in data['agencies']:
    if agency['status'] == 'not_found':
        continue
    
    slug = agency['slug']
    name = agency['name']
    
    # Escape backticks in description to avoid breaking Hugo frontmatter
    desc = (f"This {name} operates a Flock Safety ALPR portal. "
            f"{agency.get('cameras', 0)} cameras deployed, "
            f"sharing data with {agency.get('sharing_partners', 0)} partner agencies.")
    
    content = f'''---
title: "{name}"
date: {{ .Date }}
status: "{agency['status']}"
cameras: {agency['cameras']}
shares_data_with: {agency['sharing_partners']}
---

{desc}
'''
    
    filepath = os.path.join(CONTENT_DIR, f'{slug}.md')
    with open(filepath, 'w') as f:
        f.write(content)

print(f"Generated {len([a for a in data['agencies'] if a['status'] != 'not_found'])} agency content pages → website/content/agencies/")
