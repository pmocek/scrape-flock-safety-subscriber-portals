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
| `scrape-flock-safety-subscriber-portals-s6m` | Automate NCIC contradiction detection | P2 | **Implemented / Open** | Created `scripts/ncic-contradiction.py` (6 detection modes, graph BFS for multi-hop sharing). Next: integrate into GitHub Pages dashboard. |
| `scrape-flock-safety-subscriber-portals-57f` | Copy immigration NCIC analysis into repo `docs/` | P3 | **Open** | Migrate blog post drafts and NCIC Immigration Violator File conflict analysis into version control under `docs/`. |
| `scrape-flock-safety-subscriber-portals-ee7` | Build GitHub Pages companion site | P3 | **Open** | Build public static site (Hugo-based): agency portal explorer, stats history charts, NCIC compliance matrix, sharing network graph. |
| `scrape-flock-safety-subscriber-portals-edf` | Track blocked state with retry backoff for consistently denied slugs | P2 | **Backlog** | Add exponential backoff logic to `blocked.jsonl` to reduce wasted scrape attempts on confirmed dead/blocked slugs. |

---

## 2. Active Roadmap & Milestones

### Milestone 1: Automated Reporting & Static Companion Site
* **Status:** In Progress
* **Goals:**
  1. **Deploy GitHub Pages site (former `ee7`):**
     * Build static companion dashboard (Hugo or static HTML/JS) hosted on GitHub Pages.
     * Summary overview of Washington State Flock deployments (total cameras, unique vehicles detected, search volumes).
     * Interactive directory for each agency with time-series charts from `stats.jsonl`.
     * Data sharing network graph visualizing bilateral data flows and multi-hop backdoor sharing chains.
     * Public search audit reason breakdown (categorized via `scripts/analyze-audit.py`).
  2. **Publish NCIC Contradiction Analysis (former `57f` & `s6m`):**
     * Migrate the NCIC Immigration Violator File contradiction analysis and explanatory blog post into `docs/immigration-ncic/`.
     * Maintain the live matrix of agencies exhibiting policy conflicts (prohibiting immigration enforcement locally while querying national hotlists or sharing data with non-prohibiting partners).

### Milestone 2: Anti-Detect Engine Upgrade (Camoufox Integration)
* **Status:** Planned (See [`CAMOUFOX_EVALUATION.md`](CAMOUFOX_EVALUATION.md))
* **Goals:**
  1. Add support for **Camoufox** (Firefox-based C++ patched anti-detect browser) alongside Playwright Chromium.
  2. Eliminate the need for `xvfb-run` virtual framebuffers in CI by leveraging Camoufox's native C++ headless fingerprint injection.
  3. Reduce Cloudflare Error 1015 rate limiting and Turnstile challenges through realistic TLS (JA3/JA4) and HTTP/2 fingerprinting.
  4. Implement an engine flag in `scrape-flock.py`: `--engine=playwright` (default) or `--engine=camoufox`.

### Milestone 3: Cross-Referencing with Community ALPR Data (DeFlock & OSM)
* **Status:** Planned (See [`DEFLOCK_RESEARCH.md`](DEFLOCK_RESEARCH.md))
* **Goals:**
  1. Query OpenStreetMap via the Overpass API for all ALPR cameras tagged in Washington State (`surveillance:type=ALPR`, `operator=Flock Safety`).
  2. Correlate portal camera counts (`total_cameras`) with mapped camera density from DeFlock (`deflock.me`).
  3. Geocode and map exact camera street intersections disclosed under `#more-info` (e.g. Lucas County OH SO).
  4. Identify discrepancies between agency transparency portal claims and physical ground-truth camera deployments.

### Milestone 4: Scraper Resilience & Rate-Limit Backoff
* **Status:** Backlog (former `edf`)
* **Goals:**
  1. Extend `blocked.jsonl` to track consecutive block counters and exponential backoff timestamps.
  2. Skip slugs with repeated consecutive blocks (`Error 1015` or HTTP 404) for escalating durations ($2^N$ hours) to conserve CI runtime.
  3. Never permanently drop a slug to preserve historical longitudinal tracking.
