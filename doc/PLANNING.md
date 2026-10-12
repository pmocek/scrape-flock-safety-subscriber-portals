# Project Planning & Roadmap

This document serves as the persistent project task tracker and roadmap, replacing the former Beads (`bd`) issue database. All prior Beads issues, accepted milestones, active work, and backlog items have been preserved here.

---

## 1. Prior Beads Issue Archive

The following is the complete dump of all tasks migrated from the Beads local Dolt repository:

| Former Bead ID | Title | Priority | Status | Resolution / Notes |
|:---|:---|:---:|:---:|:---|
| `scrape-flock-safety-subscriber-portals-ft7` | Expand portal scraping: extract more-info disclosures, exact timestamps, and un-truncate policies | P2 | **Closed** | Implemented in ADR 002. Enhanced `scrape-flock.py` to extract `#more-info`, exact update timestamps, un-truncated policies, logos, and widgets; backfilled all 629 portals via `scripts/backfill-portal-data.py`. |
| `scrape-flock-safety-subscriber-portals-chr` | Add audit CSV search-reason analysis for immigration signals | P2 | **Closed** | Implemented `scripts/analyze-audit.py` with 26+ categorization rules, DPA SB 6002 violation signals, `--commit-body` workflow integration, and `describe-diff.py` updates. |
| `scrape-flock-safety-subscriber-portals-12n` | Bug fix: stop `refresh_agencies()` from overwriting discovered slugs | P1 | **Closed** | Removed `--refresh-agencies` from daily scrape workflow; agency list grows organically through bilateral sharing spidering. |
| `scrape-flock-safety-subscriber-portals-phb` | Deprecate eyesonflock.com as authoritative agency source | P2 | **Closed** | eyesonflock data kept for name-to-slug mapping only; real portals discovered via sharing-network spidering. |
| `scrape-flock-safety-subscriber-portals-9x3` | Investigate Playwright stealth / tread lightly settings | P2 | **Closed** | Ported health check from `urllib` to Playwright (`headless=False` + `xvfb`), matching scraper's Cloudflare detection logic. |
| `scrape-flock-safety-subscriber-portals-bng` | One-off spidering catch-up run for never-tried slugs | P2 | **Closed** | Executed catch-up scrape: verified 6 new WA agencies, purged heuristic noise, stabilized `wa-agencies.json`. |
| `scrape-flock-safety-subscriber-portals-s6m` | Automate NCIC contradiction detection | P2 | **Closed** | Created `scripts/ncic-contradiction.py` (6 detection modes, graph BFS for multi-hop sharing); results surfaced on the GitHub Pages dashboard via `website/data/ncic-matrix.json`. |
| `scrape-flock-safety-subscriber-portals-57f` | Copy immigration NCIC analysis into repo `docs/` | P3 | **Closed** | Published analysis to `docs/immigration-ncic/README.md` with a generated `conflict-matrix.md` refreshed each scrape. The original Antigravity brain files no longer existed locally, so the analysis was authored from live scraper data plus sourced statutory and investigative reporting. |
| `scrape-flock-safety-subscriber-portals-ee7` | Build GitHub Pages companion site | P3 | **Closed** | Site deployed with landing page, per-agency charts, NCIC matrix, network graph, and health dashboard. Was briefly reopened when the health criterion was found unmet; health collection was itself dead since 2026-06-29 (`44145d3a`) and the dashboard shipped once fixed. Also fixed a data-serving bug that had left `ncic-matrix.json` unreachable in production. |
| `scrape-flock-safety-subscriber-portals-edf` | Track blocked state with retry backoff for consistently denied slugs | P2 | **Closed** | Implemented exponential backoff ($2^N$ hours capped at 30 days for new slugs, 1 hour for historical slugs) and consecutive block metadata in `blocked.jsonl`. |

---

## 2. Active Roadmap & Milestones

### Milestone 1: Automated Reporting & Static Companion Site
* **Status:** Deployed & Live (https://pmocek.github.io/scrape-flock-safety-subscriber-portals/) — complete (former `ee7`)
* **Goals:**
  1. **Deploy GitHub Pages site (former `ee7`):** [Completed]
     * Build static companion dashboard (Hugo or static HTML/JS) hosted on GitHub Pages. [Completed]
     * Summary overview of Washington State Flock deployments (total cameras, unique vehicles detected, search volumes). [Completed]
     * Interactive directory for each agency with time-series charts from `stats.jsonl`. [Completed]
     * Data sharing network graph visualizing bilateral data flows and multi-hop backdoor sharing chains. [Completed]
     * Public search audit reason breakdown (categorized via `scripts/analyze-audit.py`). [Completed]
     * Health dashboard from `health.jsonl`. [Completed — `scripts/export-health-data.py` → `website/layouts/health/list.html` with D3 daily trend chart and per-agency table. Data now refreshes via `scrape.yml`.]

     * **Also fixed:** `website/data/*.json` was readable by templates via `site.Data` but 404'd when fetched over HTTP by client-side charts. `hugo.toml` now mounts `data/` into `static/data/`. `ncic-matrix.json` had been silently unavailable in production as a result; two hand-duplicated files in `static/data/` were removed.
  2. **Publish NCIC Contradiction Analysis (former `57f` & `s6m`):** [Completed]
     * Published the NCIC Immigration Violator File contradiction analysis to [`docs/immigration-ncic/README.md`](../docs/immigration-ncic/README.md), covering the NCIC operator manual's single-authority ICE provisions, the KWW and Driver Privacy Act (SB 6002, signed 2026-03-30) legal overlay, and the explicit limits of what the public portal data can and cannot prove.
     * Maintained the live WA matrix of agencies exhibiting policy conflicts in [`docs/immigration-ncic/conflict-matrix.md`](../docs/immigration-ncic/conflict-matrix.md), auto-regenerated each scrape via `scripts/ncic-contradiction.py --wa-matrix`.

### Milestone 2: Anti-Detect Engine Upgrade (Camoufox Integration)
* **Status:** Planned (See [`CAMOUFOX_EVALUATION.md`](CAMOUFOX_EVALUATION.md))
* **Goals:**
  1. Add support for **Camoufox** (Firefox-based C++ patched anti-detect browser) alongside Playwright Chromium.
  2. Eliminate the need for `xvfb-run` virtual framebuffers in CI by leveraging Camoufox's native C++ headless fingerprint injection.
  3. Reduce Cloudflare Error 1015 rate limiting and Turnstile challenges through realistic TLS (JA3/JA4) and HTTP/2 fingerprinting.
  4. Implement an engine flag in `scrape-flock.py`: `--engine=playwright` (default) or `--engine=camoufox`.

### Milestone 3: Cross-Referencing with Community ALPR Data (DeFlock & OSM)
* **Status:** Implemented (See [`DEFLOCK_RESEARCH.md`](DEFLOCK_RESEARCH.md))
* **Delivered:**
  1. Implemented `scripts/seed-from-aggregators.py` to ingest 174 missing verified portals from EyesOnFlock (`data/portal-registry.json`) and query OpenStreetMap Overpass QL for 2,346 physical ALPR cameras in Washington State.
  2. Generated candidate slugs for 63 distinct Washington State LEA operators (`data/wa-osm-candidates.json`) and exported 77 confirmed live WA portals (`data/wa-confirmed-portals.json`).
  3. Implemented `scripts/reconcile-osm-cameras.py` comparing physical camera density mapped in OSM against portal disclosures. Identified unindexed operators with physical cameras (Clark County SO 15, Wapato 8, Redmond 6) and significant discrepancies (Lynnwood +15 unlisted cameras, Lakewood -17).
  4. Cataloged 229 commercial/retail Flock cameras in Washington State (Lowe's, The Home Depot, Safeway, Kroger).
* **Next in Milestone:**
  1. Geocode and map exact camera street intersections disclosed under `#more-info` (e.g. Lucas County OH SO).

### Milestone 4: Scraper Resilience & Rate-Limit Backoff
* **Status:** Completed (former `edf`)
* **Delivered:**
  1. Extended `blocked.jsonl` schema with `consecutive_blocks`, `backoff_hours`, and `retry_after` timestamps.
  2. Implemented `should_attempt_slug()` and `record_blocked()` in `scrape-flock.py`:
     * Slugs with no historical data (never succeeded) back off exponentially: $2^N$ hours (capped at 720h / 30d).
     * Slugs with historical data (`page.txt` exists) back off for a short 1-hour window.
     * Reset counter to 0 upon successful scrape.
     * Never permanently drop slugs to ensure long-term longitudinal tracking.
  3. Integrated backoff filtering into `scrape-flock.py` batching and added `--ignore-backoff` flag.
