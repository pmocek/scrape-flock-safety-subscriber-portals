#!/usr/bin/env python3
"""
Detect NCIC / immigration enforcement contradictions and sharing backdoors.

Flags agencies that:
  A) Prohibit immigration enforcement in their Flock portal policy BUT
     subscribe to "National and statewide hotlist sources" (NCIC Immigration
     Violator File maintained solely by ICE).  (Maass contradiction)
  B) Share data (directly or indirectly) with agencies that have NOT
     configured a Flock-level immigration prohibition — if data crosses
     state lines to partners not bound by WA's Keep Washington Working Act,
     there is no contractual backstop on Flock's platform.
  C) Have not configured a Flock-level immigration prohibition.  These
     agencies may still be bound by the Keep Washington Working Act.
  D) Have conflicting Flock portal policies — prohibit immigration
     themselves BUT share data directly with agencies that have no Flock-
     level prohibition.  Their partners' data therefore enjoys no
     contractual backstop if shared outside WA.

NOTE: "Prohibits immigration" here means the agency has checked that box
in Flock's portal configuration.  All WA agencies are subject to the Keep
Washington Working Act (SB 5256, 2019), which restricts immigration
enforcement regardless of their Flock portal setting.  The Flock-level
prohibition matters contractually — without it, nothing in Flock's ToS
restricts how a non-WA partner uses the data.

Based on the EFF investigation by Dave Maass (June 2026) and analysis
of Flock Safety transparency portal data in Washington State.
"""

import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
EYESONFLOCK_FILE = PROJECT_DIR / "eyesonflock.com-api-v1-data.json"

MAX_INDIRECT_HOPS = 5


# ── helpers ──────────────────────────────────────────────────────

def load_latest_stats() -> dict[str, dict[str, Any]]:
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


def load_eyesonflock() -> dict[str, dict[str, Any]] | None:
    if not EYESONFLOCK_FILE.exists():
        return None
    with open(EYESONFLOCK_FILE) as f:
        data = json.load(f)
    by_slug: dict[str, dict[str, Any]] = {}
    for portal in data.get("portals", []):
        slug = portal.get("slug") or portal.get("portal_url", "").split("/")[-1]
        if slug:
            by_slug[slug] = portal
    return by_slug


def prohibits_immigration(pu_text: str) -> bool:
    return bool(pu_text and re.search(r"(?i)\bimmigra", pu_text))


def has_national_hotlist(hotlists_text: str) -> bool:
    return bool(hotlists_text and re.search(r"(?i)\bnational\b", hotlists_text))


def has_ncic_ref(hotlists_text: str, page_text: str) -> bool:
    combined = f"{hotlists_text or ''} {page_text or ''}"
    return bool(re.search(r"(?i)\bncic\b", combined))


# ── slug ↔ partner-name matching ────────────────────────────────

_SLUG_CACHE: dict[str, str] | None = None   # slug → lower name


def _build_slug_name_map(eof_data: dict) -> dict[str, str]:
    """Return {slug: lowercased_name} from eyesonflock data."""
    global _SLUG_CACHE
    if _SLUG_CACHE is not None:
        return _SLUG_CACHE
    m = {}
    for slug, portal in eof_data.items():
        name = (portal.get("city") or slug).lower().strip()
        m[slug] = name
    return m


def _build_name_to_slug_map(eof_data: dict) -> dict[str, str]:
    """Build a name → slug lookup from eyesonflock data.

    For each portal entry, register multiple human-readable name variants
    so we can match partner-names like "Everett (WA) Police Department"
    or "Lynnwood WA PD  [Inactive]" to their slug.
    """
    mapping: dict[str, str] = {}

    for slug, portal in eof_data.items():
        city_raw = (portal.get("city") or "").lower().strip()
        state = (portal.get("state") or "").lower().strip()

        # Always register the slug itself
        mapping[slug.lower()] = slug
        mapping[re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")] = slug

        if not city_raw:
            continue

        # Register bare city name
        mapping[city_raw] = slug

        # Variants: "City PD", "City Police Department", etc.
        labels = ["police department", "pd", "so", "sheriff", "sheriff's office",
                  "public safety", "public safety department"]

        for label in labels:
            variant = f"{city_raw} {label}"
            mapping[variant] = slug
            mapping[f"{city_raw} ({state.upper()}) {label}"] = slug
            mapping[f"{city_raw} {state} {label}"] = slug
            mapping[f"{city_raw}, {state.upper()}"] = slug

        # "City Police Department (State)" style
        mapping[f"{city_raw} ({state.upper()}) police department"] = slug
        mapping[f"{city_raw} ({state.upper()}) pd"] = slug

        # "City WA PD" variants
        mapping[f"{city_raw} wa pd"] = slug
        mapping[f"{city_raw} wa police department"] = slug
        mapping[f"{city_raw} wa so"] = slug

        # "City WA PD [Inactive]" → strip [Inactive] first (handled at lookup)

        # County-level: "County County WA SO"
        if "county" in city_raw:
            no_county = city_raw.replace("county", "").strip()
            mapping[f"{no_county} county wa so"] = slug
            mapping[f"{no_county} county so"] = slug

    return mapping


def _resolve_partners(
    slug: str, eof_data: dict, name_to_slug: dict[str, str]
) -> list[str]:
    """Return list of known slugs this agency shares data with."""
    portal = eof_data.get(slug)
    if not portal:
        return []
    partners: list[str] = []
    for raw_name in portal.get("organizations_shared_with", []):
        # Normalise: lowercase, strip, remove common suffixes
        key = raw_name.lower().strip()
        key = re.sub(r"\s*\[.*?\]", "", key).strip()  # strip [Inactive] etc
        key = re.sub(r"\s+", " ", key).strip()

        mapped = name_to_slug.get(key)
        if mapped and mapped != slug:
            partners.append(mapped)
    return partners


# ── graph building ───────────────────────────────────────────────

def _resolve_partners(
    slug: str, eof_data: dict, name_to_slug: dict[str, str]
) -> list[str]:
    """Return list of known slugs this agency shares data with."""
    portal = eof_data.get(slug)
    if not portal:
        return []
    partners: list[str] = []
    for raw_name in portal.get("organizations_shared_with", []):
        key = raw_name.lower().strip()
        mapped = name_to_slug.get(key)
        if mapped and mapped != slug:
            partners.append(mapped)
    return partners


def build_sharing_graph(
    slugs: set[str], eof_data: dict, name_to_slug: dict[str, str]
) -> dict[str, set[str]]:
    """Return {slug: {partner_slug, ...}} adjacency list."""
    g: dict[str, set[str]] = {s: set() for s in slugs}
    for slug in slugs:
        for partner in _resolve_partners(slug, eof_data, name_to_slug):
            if partner in g:
                g[slug].add(partner)
            # Ensure reverse edge exists too
            if slug in g and partner in g:
                g[partner].add(slug)
    return g


def find_indirect_paths(
    graph: dict[str, set[str]], start: str, targets: set[str], max_hops: int
) -> list[list[str]]:
    """BFS from `start` to any `target` within `max_hops` hops.

    Returns up to 3 shortest paths found.
    """
    found: list[list[str]] = []
    visited: set[str] = set()
    q: deque[tuple[str, list[str]]] = deque([(start, [start])])
    while q and len(found) < 3:
        node, path = q.popleft()
        if len(path) > max_hops + 1:
            continue
        if node in visited and node != start:
            # still allow BFS but don't revisit in same path branch
            pass
        for neighbor in sorted(graph.get(node, set())):
            if neighbor in path:
                continue
            new_path = path + [neighbor]
            if neighbor in targets and neighbor != start:
                found.append(new_path)
                continue
            if len(new_path) <= max_hops:
                q.append((neighbor, new_path))
    return found


# ── main ────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect NCIC / immigration enforcement contradictions"
    )
    parser.add_argument(
        "--commit-body",
        action="store_true",
        help="Output COMMIT_BODY: lines for workflow integration",
    )
    parser.add_argument(
        "--indirect-hops",
        type=int,
        default=MAX_INDIRECT_HOPS,
        help=f"Max chain length for indirect sharing (default {MAX_INDIRECT_HOPS})",
    )
    args = parser.parse_args()

    stats = load_latest_stats()
    eof_data = load_eyesonflock()
    ts = datetime.now(timezone.utc).isoformat()

    # ── classify agencies ────────────────────────────────────────
    contradictions_a: list[tuple[str, str, bool]] = []  # prohibits imm + national hotlists
    no_prohibition: list[tuple[str, str, bool]] = []     # doesn't prohibit imm
    no_data: list[str] = []                              # no stats
    kent_like: list[tuple[str, str]] = []                # prohibits imm + specific hotlists only

    # Read page.txt for each agency
    for slug in sorted(stats):
        s = stats[slug]
        pu = s.get("prohibited_uses", "") or ""
        hotlists = s.get("hotlists", "") or ""
        page_txt = ""
        page_file = DATA_DIR / slug / "page.txt"
        if page_file.exists():
            page_txt = page_file.read_text()

        prohibits = prohibits_immigration(pu)
        national = has_national_hotlist(hotlists)
        ncic_ref = has_ncic_ref(hotlists, page_txt)

        if not prohibits and not hotlists and not page_txt:
            no_data.append(slug)
            continue
        if not prohibits:
            no_prohibition.append((slug, hotlists, ncic_ref))
            continue
        if national:
            contradictions_a.append((slug, hotlists, ncic_ref))
            continue
        if hotlists:
            kent_like.append((slug, hotlists))

    prohib_slugs = {s for s in stats if prohibits_immigration(stats[s].get("prohibited_uses", "") or "")}
    non_prohib_slugs = {s for s, _, _ in no_prohibition}
    all_slugs = set(stats)

    # ── sharing graph ────────────────────────────────────────────
    direct_sharing: list[tuple[str, str]] = []      # (sharer_slug, partner_slug)
    indirect_chains: list[tuple[str, str, list[str]]] = []  # (start, target, path)
    policy_conflicts: list[tuple[str, str]] = []    # prohibits imm but shares w/ non-prohib

    if eof_data:
        slug_name_map = _build_slug_name_map(eof_data)
        name_to_slug = _build_name_to_slug_map(eof_data)
        graph = build_sharing_graph(all_slugs, eof_data, name_to_slug)

        # Direct sharing to non-prohibiting agencies
        for slug in sorted(stats):
            for partner in graph.get(slug, set()):
                if partner in non_prohib_slugs:
                    direct_sharing.append((slug, partner))

        # Policy conflicts: prohib shares directly with non-prohib
        for slug in prohib_slugs:
            for partner in graph.get(slug, set()):
                if partner in non_prohib_slugs:
                    policy_conflicts.append((slug, partner))

        # Indirect chains: start at any slug, find paths to non-prohib
        seen_pairs: set[tuple[str, str]] = set()
        for slug in sorted(stats):
            paths = find_indirect_paths(graph, slug, non_prohib_slugs, args.indirect_hops)
            for path in paths:
                pair = (slug, path[-1])
                if pair not in seen_pairs and len(path) > 2:
                    seen_pairs.add(pair)
                    indirect_chains.append((slug, path[-1], path))

    # ── output ───────────────────────────────────────────────────
    if args.commit_body:
        any_findings = contradictions_a or direct_sharing or no_prohibition or indirect_chains
        if any_findings:
            print("COMMIT_BODY: NCIC contradiction findings:", flush=True)
            for slug, _, ncic_ref in contradictions_a:
                flag = " NCIC-ref" if ncic_ref else ""
                print(
                    f"COMMIT_BODY:  contradiction-a {slug}: prohibits"
                    f" immigration + national hotlists{flag}"
                )
            for slug, partner in sorted(set(direct_sharing)):
                print(
                    f"COMMIT_BODY:  sharing-backdoor {slug}:"
                    f" direct share with {partner}"
                )
            for start, target, path in sorted(indirect_chains, key=lambda x: (x[0], len(x[2]))):
                chain = " → ".join(path)
                print(
                    f"COMMIT_BODY:  indirect-chain {start} → {target}"
                    f" [{len(path) - 1} hops]: {chain}"
                )
            for slug, _, ncic_ref in sorted(no_prohibition):
                flag = " NCIC-ref" if ncic_ref else ""
                print(f"COMMIT_BODY:  no-immigration-prohibition {slug}: no prohib flag{flag}")
        return

    # ── full report ──────────────────────────────────────────────
    print(f"NCIC / Immigration Contradiction Report ({ts})")
    print("=" * 70)

    # Section A — Maass contradiction
    print(
        f"\nA) MAASS CONTRADICTION — Prohibits immigration (Flock-level)"
        f" + National hotlists ({len(contradictions_a)} agencies)"
    )
    print("-" * 70)
    print(
        "These agencies use Flock's portal to prohibit immigration enforcement\n"
        "BUT subscribe to 'National and statewide hotlist sources' via NCIC,\n"
        "which includes the Immigration Violator File maintained solely by ICE.\n"
        "(All are subject to WA's Keep Washington Working Act regardless.)\n")
    for slug, hotlists, ncic_ref in contradictions_a:
        ncic_mark = " [NCIC reference in page text]" if ncic_ref else ""
        ext = stats[slug].get("external_agencies_count", 0)
        print(f"  {slug:30s}  ext_agencies={ext}{ncic_mark}")

    if kent_like:
        print(f"\n   Exception — Specific hotlists (not national bundle):")
        for slug, hotlists in kent_like:
            print(f"  {slug:30s}  {hotlists[:80]}")

    # Section B — No immigration prohibition
    if no_prohibition:
        print(
            f"\nB) NO FLOCK-LEVEL IMMIGRATION PROHIBITION ({len(no_prohibition)} agencies)"
        )
        print("-" * 70)
        print(
            "These agencies have NOT configured a Flock-level immigration prohibition.\n"
            "They may still be bound by WA's Keep Washington Working Act — but without\n"
            "the Flock checkbox, nothing in Flock's ToS contractually restricts how\n"
            "their data is used when shared with non-WA partners.\n")
        for slug, hotlists, ncic_ref in no_prohibition:
            ncic_mark = " [NCIC reference in page text]" if ncic_ref else ""
            print(f"  {slug:30s}  {hotlists[:50]}{ncic_mark}")

    # Section C — No data
    if no_data:
        print(f"\nC) NO DATA ({len(no_data)} agencies)")
        print("-" * 70)
        for slug in no_data:
            print(f"  {slug:30s}  (portal unreachable or no policies published)")

    # Section D — Policy conflicts (prohib shares with non-prohib)
    if policy_conflicts:
        print(
            f"\nD) FLOCK POLICY CONFLICTS — Prohibits immigration BUT shares with"
            f" agencies lacking Flock-level prohibition ({len(set(p[0] for p in policy_conflicts))} agencies)"
        )
        print("-" * 70)
        print(
            "These agencies prohibit immigration enforcement in their Flock portal,\n"
            "yet share data directly with partners who have no Flock-level prohibition.\n"
            "Data flowing through those partners has no contractual backstop.\n")
        by_sharer = defaultdict(set)
        for sharer, partner in sorted(set(policy_conflicts)):
            by_sharer[sharer].add(partner)
        for sharer in sorted(by_sharer):
            partners = sorted(by_sharer[sharer])
            print(f"  {sharer:30s}  shares with {len(partners)} non-prohibiting partner(s):")
            for p in partners[:5]:
                print(f"    {'':30s}  {p}")
            if len(partners) > 5:
                print(f"    {'':30s}  ... and {len(partners) - 5} more")

    # Section E — Direct sharing backdoor
    if direct_sharing:
        unique_sharers = len(set(s for s, _ in direct_sharing))
        print(
            f"\nE) DIRECT SHARING BACKDOOR ({unique_sharers} agencies,"
            f" {len(set(direct_sharing))} relationships)"
        )
        print("-" * 70)
        print(
            "Agencies sharing data with partners that have no Flock-level\n"
            "immigration prohibition.  Those partners lack a contractual backstop\n"
            "if they share data outside WA.\n"
        )
        by_sharer = defaultdict(set)
        for sharer, partner in sorted(set(direct_sharing)):
            by_sharer[sharer].add(partner)
        for sharer in sorted(by_sharer):
            partners = sorted(by_sharer[sharer])
            print(f"  {sharer:30s}  shares with {len(partners)} partner(s):")
            for p in partners[:5]:
                print(f"    {'':30s}  {p}")
            if len(partners) > 5:
                print(f"    {'':30s}  ... and {len(partners) - 5} more")

    # Section F — Indirect sharing chains
    if indirect_chains:
        unique_starters = len(set(s for s, _, _ in indirect_chains))
        print(
            f"\nF) INDIRECT SHARING CHAINS — Multi-hop paths to"
            f" agencies lacking Flock-level prohibition ({unique_starters} start nodes,"
            f" {len(indirect_chains)} chains)"
        )
        print("-" * 70)
        print(
            "Multi-hop data-sharing paths from agencies with a Flock-level\n"
            "immigration prohibition to agencies without one.  At each hop the\n"
            "contractual backstop weakens.\n"
        )
        by_start = defaultdict(list)
        for start, target, path in indirect_chains:
            by_start[start].append((target, path))
        for start in sorted(by_start):
            entries = by_start[start]
            print(f"  {start:30s}  {len(entries)} indirect path(s):")
            for target_slug, path in entries[:3]:
                display = " → ".join(path)
                print(f"    {'':30s}  [{len(path) - 1} hops] {display}")

    print()
    print("=" * 70)
    total = len(stats)
    print(
        f"Summary: {total} agencies checked,"
        f" {len(contradictions_a)} with Maass contradiction (Flock-level),"
        f" {len(no_prohibition)} without Flock-level prohibition,"
        f" {len(no_data)} unreachable,"
        f" {len(set(s for s, _, _ in indirect_chains))} with indirect chains."
    )


if __name__ == "__main__":
    main()
