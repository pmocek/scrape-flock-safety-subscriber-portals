#!/usr/bin/env python3
"""Export NCIC contradiction analysis results as JSON for the companion website."""
import json, re, os
from collections import defaultdict, deque
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = PROJECT_DIR / "website" / "data" / "ncic-matrix.json"
EYESONFLOCK_FILE = PROJECT_DIR / "eyesonflock.com-api-v1-data.json"

def load_latest_stats():
    result = {}
    for slug_dir in sorted(DATA_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        stats_file = slug_dir / "stats.jsonl"
        if not stats_file.exists():
            continue
        with open(stats_file) as f:
            lines = f.read().strip().split("\n")
            if not lines or not lines[0]:
                continue
            result[slug_dir.name] = json.loads(lines[-1])
    return result

def load_eyesonflock():
    if not EYESONFLOCK_FILE.exists():
        return None
    with open(EYESONFLOCK_FILE) as f:
        data = json.load(f)
    by_slug = {}
    for portal in data.get("portals", []):
        slug = portal.get("slug") or portal.get("portal_url", "").split("/")[-1]
        if slug:
            by_slug[slug] = portal
    return by_slug

def prohibits_immigration(pu_text):
    return bool(pu_text and re.search(r"(?i)\bimmigra", pu_text))

def has_national_hotlist(hotlists_text):
    return bool(hotlists_text and re.search(r"(?i)\bnational.*hotlist", hotlists_text))

def build_sharing_graph(stats):
    """Build adjacency list for sharing relationships."""
    graph = defaultdict(set)
    for slug, entry in stats.items():
        shared_with = entry.get("shares_data_with", []) or []
        for partner_name in shared_with:
            # Try to match name to slug
            partner_slug = name_to_slug(partner_name, stats.keys())
            if partner_slug:
                graph[slug].add(partner_slug)
    return graph

def name_to_slug(name, slugs):
    normalized = name.lower().replace(" ", "").replace("-", "")
    for slug in slugs:
        if slug.replace("-", "").replace("_", "").lower() == normalized:
            return slug
    first_word = name.split()[0].lower().replace(" ", "")
    for slug in slugs:
        if first_word in slug.replace("-", "").replace("_", "").lower():
            return slug
    return None

def find_indirect_chains(origin_slug, graph, max_hops=5):
    """BFS to find indirect paths from origin to non-prohibiting agencies."""
    chains = []
    visited = set([origin_slug])
    queue = deque([(origin_slug, [origin_slug])])
    
    while queue:
        current, path = queue.popleft()
        if len(path) - 1 >= max_hops:
            continue
        
        for neighbor in graph.get(current, set()):
            if neighbor in visited:
                continue
            
            new_path = path + [neighbor]
            visited.add(neighbor)
            
            if not is_prohibitor_neighbor(neighbor):
                chains.append(new_path)
            
            if len(path) < max_hops:
                queue.append((neighbor, new_path))
    
    return chains

# Cache inhibitor status
_inhibitors = {}
def is_prohibitor(slug):
    if slug not in _inhibitors:
        stat = all_stats.get(slug, {})
        _inhibitors[slug] = prohibits_immigration(stat.get("prohibited_uses", ""))
    return _inhibitors[slug]

def is_prohibitor_neighbor(slug):
    return is_prohibitor(slug)

all_stats = load_latest_stats()
eof_data = load_flags = load_eyesonflock()
graph = build_sharing_graph(all_stats)

results = []
mode_a = []  # Maass contradiction
mode_b = []  # No prohibition
mode_c = []  # Sharing with non-prohibiting
mode_d = []  # Direct backdoor
mode_e = []  # Indirect chains

for slug, entry in sorted(all_stats.items(), key=lambda x: x[1].get("page_name", "")):
    prohibited = prohibits_immigration(entry.get("prohibited_uses", ""))
    national_hotlist = has_national_hotlist(entry.get("hotlists", ""))
    name = entry.get("page_name", slug)
    status = entry.get("portal_status", "unknown")
    partners = entry.get("external_agencies_count", 0) or 0
    
    flags = []
    
    # Mode A: Prohibits immigration but uses national hotlists
    if prohibited and national_hotlist:
        flags.append("maass_contradiction")
        mode_a.append({"slug": slug, "name": name, "cameras": entry.get("total_cameras", 0)})
    
    # Mode B: No immigration prohibition at all (only for active portals)
    if status != "not_found" and not prohibited:
        flags.append("no_immigration_prohibition")
        mode_b.append({"slug": slug, "name": name})
    
    # Mode C & D: Sharing with non-prohibiting partners
    if status != "not_found" and partners > 0:
        partner_slugs = graph.get(slug, set())
        non_prohibiting_partners = []
        direct_backdoors = []
        
        for partner_slug in partner_slugs:
            if not is_prohibitor(partner_slug):
                non_prohibiting_partners.append(partner_slug)
                if len(graph.get(partner_slug, set()).intersection({slug})) > 0:
                    direct_backdoors.append(partner_slug)
        
        if non_prohibiting_partners:
            flags.append("shares_with_non_prohibitors")
            mode_c.append({"slug": slug, "name": name, "non_prohibiting_partners": len(non_prohibiting_partners)})
        
        if direct_backdoors:
            flags.append("direct_backdoor_sharing")
            mode_d.append({"slug": slug, "name": name, "backdoor_partners": direct_backdoors})
    
    if flags:
        results.append({
            "slug": slug,
            "name": name,
            "status": status,
            "flags": flags,
            "prohibits_immigration": prohibited,
            "uses_national_hotlists": national_hotlist,
            "sharing_partners": partners,
        })

result = {
    "generated_at": "auto",
    "total_analyzed": len(all_stats),
    "agencies_with_flags": len(results),
    "mode_a_maass_contradiction": mode_a,
    "mode_b_no_prohibition": mode_b,
    "mode_c_sharing_conflicts": mode_c,
    "mode_d_direct_backdoors": mode_d,
    "mode_e_indirect_chains": [],  # BFS chains deferred for complexity
    "matrix": results,
}

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w") as f:
    json.dump(result, f, indent=2)

print(f"NCIC matrix → {OUTPUT_FILE}")
print(f"  Analyzed: {len(all_stats)} agencies")
print(f"  Flags found: {len(results)} agencies with issues")
print(f"  Mode A (Maass): {len(mode_a)}")
print(f"  Mode B (No prohibition): {len(mode_b)}")
print(f"  Mode C (Sharing conflicts): {len(mode_c)}")
print(f"  Mode D (Direct backdoors): {len(mode_d)}")
