---
title: "NCIC Immigration Violator File Contradictions in WA Flock Safety Portals"
date: 2026-10-10
status: draft
---

# NCIC Immigration Violator File Analysis

This document tracks agencies operating Flock Safety ALPR portals in Washington State that exhibit policy contradictions related to immigration enforcement and NCIC (National Crime Information Center) access.

## Background

The **Maass contradiction** (named after EFF investigator Dave Maass, June 2026) refers to agencies that:

1. Have configured their Flock portal to **prohibit immigration enforcement**, AND
2. Subscribe to **"National and statewide hotlist sources"** — which includes the NCIC Immigration Violator File maintained solely by ICE (Immigration and Customs Enforcement)

By subscribing to national hotlists while prohibiting immigration enforcement, these agencies effectively grant themselves access to immigration enforcement data without having a contractual prohibition in place to prevent misuse.

### Legal Context

Washington's **Keep Washington Working Act** (ESSB 5256, 2019) restricts all state and local law enforcement from using resources for federal immigration enforcement. However, this statute operates at the state level — it does not bind non-WA partner agencies through whom data may flow via Flock's sharing network. The Flock-level prohibition matters contractually: without it, nothing in Flock's Terms of Service restricts how a non-WA partner uses the data received.

## Detection Modes

The analysis tool (`scripts/ncic-contradiction.py`) flags contradictions across 6 detection modes:

### Mode A: Direct NCIC Access + Immigration Prohibition (The Maass Contradiction)

Agencies that prohibit immigration enforcement in their Flock portal but subscribe to "National and statewide hotlist sources" (which includes the NCIC Immigration Violator File).

**Risk**: Access to immigration violation data undermines the stated prohibition.

### Mode B: No Immigration Prohibition at All

Agencies with no Flock-level immigration prohibition configured. While WA agencies are subject to the Keep Washington Working Act, the absence of an explicit portal-level prohibition means there is no contractual backstop on how their data is used or shared.

**Risk**: Data may be repurposed for immigration enforcement if accessed by federal partners.

### Mode C: Policy Conflicts — Sharing with Non-Prohibiting Agencies

Agencies that prohibit immigration but share data directly with agencies that have **no** immigration prohibition. The prohibited-use restriction applies only to the originating agency — downstream recipients face no such constraint.

**Risk**: An agency that prohibits immigration enforcement may nonetheless have its data shared with non-prohibiting partners who could use it for immigration purposes.

### Mode D: Direct Backdoor Sharing

Agencies that prohibit immigration but share data directly with specific named non-prohibiting partner agencies. This represents a direct pathway for data to reach entities where immigration enforcement restrictions don't apply.

**Risk**: Specific, traceable data flows from protecting-to-non-protecting agencies.

### Mode E: Indirect Sharing Chains (Multi-hop BFS)

Using breadth-first search traversal (up to 5 hops), this mode identifies indirect pathways where data travels from a prohibitor → intermediate agency → non-prohibiting agency. Even if the originator has a prohibition, multi-hop chains can route data to places where it has no protection.

**Risk**: Complex, less-visible data pathways that evade simple bilateral analysis.

## Compliance Matrix

For the live compliance matrix, see [NCIC Compliance Matrix](https://pmocek.github.io/scrape-flock-safety-subscriber-portals/ncic-compliance/) on the companion site.

## Methodology

- **Data source**: Flock Safety transparency portal scrape data (stats.jsonl files per agency)
- **Hotlist detection**: `re.search(r"(?i)\bnational.*hotlist", hotlists_text)` 
- **Immigration prohibition**: `re.search(r"(?i)\bimmigra", prohibited_uses_text)`
- **Sharing network**: Bidirectional edges from `shares_data_with` field in stats.jsonl
- **Chain analysis**: BFS graph traversal up to N hops for indirect sharing detection
- **Name-to-slug mapping**: Cross-referenced against `eyesonflock.com-api-v1-data.json`

## References

- [Dave Maass, "How ICE Uses ALPRs to Hunt Immigrants," Electronic Frontier Foundation, June 2026](https://www.eff.org/)
- [WA ESSB 5256 (Keep Washington Working Act)](https://apps.leg.wa.gov/BillLookup/2019)
- [NCIC Code of Conduct — Prohibition on Use for Immigration Enforcement](https://www.fbi.gov/services/cjis/ncic/code-of-conduct)
