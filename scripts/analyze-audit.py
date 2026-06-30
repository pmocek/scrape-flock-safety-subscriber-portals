#!/usr/bin/env python3
"""
Analyze Public Search Audit CSV files across agencies.

Categorizes search reasons, flags outliers (federal agency mentions,
generic entries, case-number-only reasons, rare patterns), and
produces a structured summary for case-by-case review.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_DIR / "data"

FED_RE = re.compile(
    r'(?i)\b(?:fbi|atf|dea|hsi|ice|usbp|cbp|dhs|hsinet?|us\s*marshals?'
    r'|border\s+patrol|customs|immigra|federal|jttf|ncic|wacic)\b'
)

CASE_NUM_RE = re.compile(r'^[\d-]+$')

# Driver Privacy Act (SB 6002) violation signals:
# - Immigration enforcement use (banned outright)
# - Federal agency searches on behalf of immigration enforcement
# - Case-number-only reasons (circumvents reason specificity requirement)
# - On-behalf-of (OSA) searches for federal agencies
DPA_IMMIGRATION_RE = re.compile(
    r'(?i)\b(?:ice|usbp|hsi|cbp|border\s+patrol|customs|immigra)\b'
)
DPA_FED_OSA_RE = re.compile(
    r'(?i)\b(?:osa\s+(?:to|for)\s+(?:atf|fbi|dea|hsi|ice|usbp|cbp|dhs|us\s+marshals?|border\s+patrol))\b'
)

CATEGORY_RULES = [
    ("homicide_death", re.compile(r'(?i)\b(?:homicide|death\s*investig|murder|manslaughter)')),
    ("weapons", re.compile(r'(?i)\b(?:weapons?\s*offen|gun|shooting|firearm)')),
    ("assault", re.compile(r'(?i)\b(?:assault|battery)')),
    ("domestic_violence", re.compile(r'(?i)\b(?:domestic\s+violence|dv\b)')),
    ("robbery", re.compile(r'(?i)\b(?:robbery|armed\s*rob|carjacking|rob\s+\d)')),
    ("kidnapping", re.compile(r'(?i)\b(?:kidnap|abduction)')),
    ("burglary_theft", re.compile(r'(?i)\b(?:burglary|theft|stolen|financial\s*crime|embezzlement|fraud|vandalism|arson)')),
    ("hit_and_run", re.compile(r'(?i)\b(?:hit\s*(?:and|&)?\s*run|car\s*accident|motor.?vehicle\s*accident)')),
    ("mva_crash", re.compile(r'(?i)\bmva\b')),
    ("dui", re.compile(r'(?i)\b(?:dui|dwi|owi|ovi|impaired|alcohol|driving\s*under\s*the\s*influence)')),
    ("eluding", re.compile(r'(?i)\b(?:elud|flee|obstruct.*(?:police|resisting)|pursuit|reckless)')),
    ("drugs", re.compile(r'(?i)\b(?:drugs?|narcotics?)')),
    ("sex_crime", re.compile(r'(?i)\b(?:rape|sexual|sex\s+offen|child\s+abuse|pornograph|prostitution)')),
    ("missing_person", re.compile(r'(?i)\bmissing\b')),
    ("warrant", re.compile(r'(?i)\b(?:warrant|ro\s+has)')),
    ("locate_suspect", re.compile(r'(?i)\b(?:locate|attempt\s+to\s+locate|\bAtl\b|suspect\s+vehicle|suspect\s+id|suspect\s+location|lookout)')),
    ("community_caretaking", re.compile(r'(?i)\b(?:community\s+caretaking|welfare\s+check)')),
    ("training", re.compile(r'(?i)\b(?:training|exempt|test\b)')),
    ("probable_cause", re.compile(r'(?i)\b(?:probable\s+cause|reasonable\s+suspicion)')),
    ("protective_order", re.compile(r'(?i)\b(?:protective|protection)\s*order')),
    ("stalking_threats", re.compile(r'(?i)\b(?:stalking|threats?|harassment)')),
    ("destruction_vandalism", re.compile(r'(?i)\b(?:destruction|damage|vandalism|malicious\s*misch|mal\s+misch)')),
    ("motor_vehicle_offense", re.compile(r'(?i)\b(?:criminal\s+motor\s+vehicle\s+offen|tmvwop|vehicle\s+prowl)')),
    ("investigation_generic", re.compile(r'(?i)^\s*investigation\s*$')),
    ("identification", re.compile(r'(?i)\b(?:identif|checking\s+for\s+vehicles|load\s+car)')),
    ("case_number_only", CASE_NUM_RE),
]


def classify_reason(reason):
    if not reason or not reason.strip():
        return ["empty"]
    matched = []
    for cat, pattern in CATEGORY_RULES:
        if pattern.search(reason):
            matched.append(cat)
    if not matched:
        matched = ["unclassified"]
    return matched


def has_federal_ref(reason):
    return bool(FED_RE.search(reason))


def has_dpa_immigration_signal(reason):
    return bool(DPA_IMMIGRATION_RE.search(reason))


def has_dpa_fed_osa(reason):
    return bool(DPA_FED_OSA_RE.search(reason))


VAGUE_PHRASES = {
    "investigation", "checking for vehicles", "load car", "pdr", "tf/vucsa",
    "al scso", "mvtr",
}


def is_vague(reason):
    r = reason.strip().lower()
    return r in VAGUE_PHRASES


def format_header(msg):
    return f"\n{'=' * 60}\n{msg}\n{'=' * 60}"


def emit_commit_body(items, prefix):
    for slug, reason in sorted(items, key=lambda x: x[1].lower()):
        print(f"COMMIT_BODY:  {prefix} {slug}: {reason[:120]}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze Public Search Audit CSV files")
    parser.add_argument("--commit-body", action="store_true",
                        help="Output COMMIT_BODY: lines for workflow integration")
    args = parser.parse_args()

    audit_dirs = sorted(DATA_DIR.glob("*/audit.csv"))
    if not audit_dirs:
        print("No audit CSV files found.")
        return

    all_reasons = []
    per_agency = {}
    category_counts = Counter()
    fed_references = []
    dpa_immigration = []
    dpa_fed_osa = []
    vague_entries = []
    case_number_entries = []

    for path in audit_dirs:
        slug = path.parent.name
        rows = []
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            print(f"  {slug}: error reading CSV — {e}")
            continue

        agency_reasons = []
        for row in rows:
            reason = (row.get("reason") or row.get("offenseType") or "").strip()
            if not reason:
                continue
            categories = classify_reason(reason)
            all_reasons.append((slug, reason, categories))

            has_dpa_imm = has_dpa_immigration_signal(reason)
            has_dpa_osa = has_dpa_fed_osa(reason)

            entry = {
                "reason": reason,
                "categories": categories,
                "has_federal_ref": has_federal_ref(reason),
                "is_vague": is_vague(reason),
                "is_case_number": bool(CASE_NUM_RE.match(reason)),
                "dpa_immigration": has_dpa_imm,
                "dpa_fed_osa": has_dpa_osa,
            }
            agency_reasons.append(entry)

            for cat in categories:
                category_counts[cat] += 1

            if entry["has_federal_ref"]:
                fed_references.append((slug, reason))
            if has_dpa_imm:
                dpa_immigration.append((slug, reason))
            if has_dpa_osa:
                dpa_fed_osa.append((slug, reason))
            if entry["is_vague"] and not entry["is_case_number"]:
                vague_entries.append((slug, reason))
            if entry["is_case_number"]:
                case_number_entries.append((slug, reason))

        per_agency[slug] = agency_reasons

    # ── Summary ──────────────────────────────────────────────
    total_rows = sum(len(v) for v in per_agency.values())
    total_files = len(audit_dirs)
    agencies_with_rows = sum(1 for v in per_agency.values() if v)

    print(format_header("SUMMARY"))
    print(f"  Agencies with audit CSVs:  {total_files}")
    print(f"  Agencies with data rows:   {agencies_with_rows}")
    print(f"  Total search reason rows:  {total_rows}")
    print(f"  Unique reason strings:     {len(set(r for _, r, _ in all_reasons))}")

    print(format_header("CATEGORY BREAKDOWN"))
    for cat, count in category_counts.most_common():
        pct = count / total_rows * 100
        print(f"  {cat:30s} {count:5d} ({pct:4.1f}%)")

    unclassified = [r for r in all_reasons if "unclassified" in r[2]]
    if unclassified:
        print(format_header(f"UNCLASSIFIED REASONS ({len(unclassified)})"))
        for slug, reason, _ in sorted(unclassified, key=lambda x: x[1].lower()):
            print(f"  {slug:30s} {reason[:100]}")

    # ── Outliers ─────────────────────────────────────────────
    print(format_header("OUTLIERS — FEDERAL AGENCY REFERENCES"))
    if fed_references:
        for slug, reason in sorted(fed_references, key=lambda x: x[1].lower()):
            print(f"  {slug:30s} {reason[:120]}")
    else:
        print("  (none found)")

    if dpa_immigration or dpa_fed_osa:
        print(format_header("POTENTIAL DPA (SB 6002) VIOLATIONS"))
        if dpa_immigration:
            print(f"  Immigration enforcement signals ({len(dpa_immigration)}):")
            for slug, reason in sorted(dpa_immigration, key=lambda x: x[1].lower()):
                print(f"    {slug:30s} {reason[:120]}")
        if dpa_fed_osa:
            print(f"  On-behalf-of federal searches ({len(dpa_fed_osa)}):")
            for slug, reason in sorted(dpa_fed_osa, key=lambda x: x[1].lower()):
                print(f"    {slug:30s} {reason[:120]}")

    print(format_header("OUTLIERS — VAGUE / GENERIC"))
    if vague_entries:
        for slug, reason in sorted(vague_entries, key=lambda x: x[1].lower()):
            print(f"  {slug:30s} {reason[:120]}")
    else:
        print("  (none found)")

    print(format_header("OUTLIERS — CASE NUMBER ONLY"))
    if case_number_entries:
        agency_case_counts = Counter(slug for slug, _ in case_number_entries)
        for slug, count in agency_case_counts.most_common():
            print(f"  {slug:30s} {count} entries")
        for slug, reason in sorted(case_number_entries, key=lambda x: x[1])[:20]:
            print(f"  {slug:30s} {reason[:120]}")
        if len(case_number_entries) > 20:
            print(f"  ... and {len(case_number_entries) - 20} more")
    else:
        print("  (none found)")

    # ── Per-Agency Breakdown ─────────────────────────────────
    print(format_header("PER-AGENCY BREAKDOWN"))
    for slug in sorted(per_agency):
        rows = per_agency[slug]
        if not rows:
            print(f"  {slug:30s} 0 rows")
            continue
        cats = Counter()
        for r in rows:
            for c in r["categories"]:
                cats[c] += 1
        cat_str = ", ".join(f"{c}={v}" for c, v in cats.most_common(5))
        flags = []
        if any(r["has_federal_ref"] for r in rows):
            flags.append("FED")
        if any(r["is_vague"] for r in rows):
            flags.append("VAGUE")
        if any(r["is_case_number"] for r in rows):
            flags.append("CASENUM")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {slug:30s} {len(rows):4d} rows  {cat_str}  {flag_str}")

    # ── Rare reasons (appear only once across all agencies) ──
    print(format_header("RARE REASONS (appear once across all data)"))
    reason_counter = Counter(r[1].lower().strip() for r in all_reasons)
    rare = [(slug, r) for slug, r, _ in all_reasons if reason_counter[r.lower().strip()] == 1]
    if rare:
        for slug, reason in sorted(rare, key=lambda x: x[1].lower())[:30]:
            print(f"  {slug:30s} {reason[:120]}")
        if len(rare) > 30:
            print(f"  ... and {len(rare) - 30} more")
    else:
        print("  (none found)")


    # ── Commit body output (for CI integration) ─────────────────
    if args.commit_body:
        any_dpa = dpa_immigration or dpa_fed_osa
        any_outliers = any_dpa or vague_entries or case_number_entries
        if any_outliers:
            print("COMMIT_BODY: Audit outliers:", flush=True)
            if dpa_immigration:
                emit_commit_body(dpa_immigration, "DPA-immigration")
            if dpa_fed_osa:
                emit_commit_body(dpa_fed_osa, "DPA-federal-OSA")
            if vague_entries:
                emit_commit_body(vague_entries, "vague")
            if case_number_entries:
                emit_commit_body(case_number_entries, "case-number-only")


if __name__ == "__main__":
    main()
