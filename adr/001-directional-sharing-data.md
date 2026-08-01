# ADR 001: Directional Flock Safety data-sharing relationships

**Date:** 2026-07-31

## Context

The Flock Safety transparency portal page for each agency contains two
separate sharing-network sections:

1. **Sharing Network Data With** — agencies this agency *sends* data to
   (page heading "Organizations granted access to <agency> data")
2. **Receiving Network Data From** — agencies this agency *receives* data
   from (page heading "Organizations sharing their data with <agency>")

These are bilateral data-sharing relationships, but the Flock portal only
reveals one direction at a time — we must scrape both endpoints to
confirm two-way sharing.

The original `parse_stats()` implementation merged both sections into a
single deduplicated `external_agencies` list. This was adequate for graph
traversal (finding new agency slugs to scrape) but lost the direction
information needed for:

- **NCIC contradiction analysis (Maass)** — an agency that prohibits
  immigration enforcement but *receives* data from a non-prohibiting
  partner may have a different severity than one that *sends* data to one.

- **Data flow mapping** — identifying data brokers and hubs (Yelm WA PD
  receives from 278 non-WA agencies but shares data only within WA).

- **Future policy analysis** — directional asymmetry can indicate which
  agencies are net data consumers vs. net data providers.

## Decision

- `stats.jsonl` will grow two new fields: `shares_data_with` and
  `receives_data_from`, each containing the ordered list of agency display
  names from the corresponding page section.

- The existing `external_agencies` field will be retained as the
  **union** of both lists, deduplicated, preserving backward compatibility
  with cross-agency spidering and existing analysis scripts.

- Raw `page.txt` and `page.html` are already saved on every scrape and
  are the canonical source of truth. `stats.jsonl` is a derived
  convenience format.

- Historical data will be backfilled: `page.txt` files for every agency
  dir will be re-parsed and new directional entries appended to their
  `stats.jsonl`.

## Consequences

### Positive

- Direction preserved for all future scrapes and backfilled for history.
- Existing `external_agencies` consumers (spidering, analyze-audit,
  ncic-contradiction) continue to work unchanged.
- Raw data never lost — `page.txt`/`page.html` remain canonical.

### Negative

- Slightly larger `stats.jsonl` entries (two lists instead of one).
- Backfill is a one-time cost: re-parsing ~240 historical page.txt files.

### Risks

- Some early `page.txt` files may use the old Flock page format
  ("External Agencies who have access") which had no directional
  separation. Those entries will have empty `shares_data_with` and
  `receives_data_from` fields and only the merged `external_agencies`.
  This is acceptable — the two-section format appeared when Flock
  redesigned their portal (before our scraping began).

## Alternatives Considered

### Store only raw page.txt, derive on demand

Rejected: all downstream scripts (spidering, ncic, analyze) would need to
re-parse the page text every time, adding complexity and slowing analysis
passes that don't need raw data.

### Add a separate relationships file

Rejected: keeping all per-agency data in `stats.jsonl` is simpler and
matches the existing pattern of one JSONL file per slug. A separate
global relationships file would need its own sync/merge logic.

### Skip backfill

Rejected: without backfill, a gap exists between "before this ADR" and
"after this ADR". Since all raw data is available, there's no cost to
backfilling, and it makes the dataset self-consistent.
