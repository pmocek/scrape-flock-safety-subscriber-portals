# ADR 002: Public Transparency Portal Data Expansion and DOM Extraction

**Date:** 2026-10-04  
**Status:** Accepted  

## Context

Following the investigation into public surveillance disclosures documented in `../scrape-axon-communityconnect` (ADR 001: Public API Discovery and Nationwide Data Caching), we evaluated whether Flock Safety subscriber portals could similarly be queried directly via unauthenticated backend APIs rather than browser scraping, and whether our scraper was capturing all public data exposed by Flock's platform.

### Investigation Findings

1. **Architecture Comparison: Axon Fusus vs. Flock Safety**
   * **Axon Community Connect:** Operates as a Client-Side Rendered (CSR) Angular Single Page Application. The server serves an empty shell; Angular boots up in the client browser and queries unauthenticated public REST endpoints (`https://api.fususone.com/api/public/connectivity-check/`, `/organizations/{org}/stats/`, etc.) with no bot protection. Direct HTTP requests (`curl`, `urllib`) can retrieve JSON payloads directly in milliseconds.
   * **Flock Safety Transparency Portals:** Operates as Server-Side Rendered (SSR) static HTML. Flock's origin server queries its internal database and compiles all metrics, policy paragraphs, sharing partner lists, and even the 30-day search audit CSV (as an inline `data:text/csv` URI) directly into HTML markup before sending it over the wire.
   * **Client Bundles:** An analysis of the scripts embedded across Flock portals confirms that there is no frontend SPA framework bundle and no public client-facing API client. The only client scripts are Cloudflare anti-bot scripts, Segment analytics, Cloudflare Insights, and a 30-line vanilla helper (`initPortalEnhancements`) that binds scrollbar and anchor listeners to the pre-rendered HTML.
   * **Cloudflare Edge Protection:** Flock front-ends `transparency.flocksafety.com` with Cloudflare edge security (TLS fingerprint checks, Turnstile/precursor JS challenge, Error 1015 / 429 rate limiting). Direct non-browser HTTP queries (`curl`, Python `urllib`) are rejected with `HTTP 403 Forbidden` at the edge.

2. **Conclusion on Direct API Access**
   Because Flock provides no public JSON API for transparency data, compiles all portal data server-side into static HTML, and blocks raw HTTP clients with Cloudflare 403s, **browser-driven scraping via Playwright remains necessary**.

3. **Gaps in Current Data Extraction**
   While Playwright successfully captures the pre-rendered `page.html` and raw `page.txt`, our current text-regex parser (`parse_stats()`) omits or artificially truncates substantial public oversight data present in the rendered HTML:
   * **Exact Update Timestamps:** Portals include the exact ISO 8601 timestamp when Flock compiled the page (`<span title="<ISO_TIMESTAMP>">`), but `stats.jsonl` only records the scraper's execution time (`ts`).
   * **Custom `#more-info` / `Additional Info` Disclosures:** Completely ignored by the regex parser. These sections frequently contain:
     * Specific ALPR **camera street intersections** (e.g. Lucas County OH SO).
     * External **ALPR policy documents and PDF links**, such as Lexipol policy manuals (e.g. Yakima WA PD).
     * Program **funding sources**, such as state auto theft grant awards (e.g. Everett WA PD, Lynnwood WA PD).
     * Agency-authored glossaries and definition standards.
   * **Policy Text Truncation:** `scrape-flock.py` has an arbitrary cutoff (`if len(val) > 500: val = val[:500]`) that actively discards policy text for agencies with comprehensive rules.
   * **Widget Metrics:** Newer Flock portal layouts include widgets for `Top Offense Types` (ranked offense categories used for searches in the last 30 days) and `Camera Alert Activity` (total alert counts and source breakdown, e.g. NCIC Warrants). These are not extracted into `stats.jsonl`.
   * **Agency Badges and Insignia:** Official agency badge/logo assets (`tpHeroLogoImage`) and hero graphics (`tpHeroImage`) are hosted on public S3 buckets but not archived locally.
   * **Rolling Audit Loss:** `audit.csv` is overwritten on each scrape with the current rolling 30-day window, losing historical searches if not merged.

---

## Decision

We expand the Flock transparency scraper and data schema to extract all structured data exposed in the rendered HTML:

1. **Exact Portal Timestamps & Agency Overview (`stats.jsonl`):**
   * Extract `portal_last_updated` from `<span title="<ISO_TIMESTAMP>">`.
   * Extract `overview` paragraph containing agency mission statements and local authorizations.
   * Track `portal_status` (`"active"`, `"inactive"`, or `"not_found"`).

2. **Un-truncated Policy Texts:**
   * Remove the 500-character cap on `acceptable_use`, `prohibited_uses`, `access_policy`, and `hotlist_policy`.

3. **`#more-info` & `Additional Info` Disclosures:**
   * Parse all custom cards into a structured `more_info` mapping in `stats.jsonl`.
   * Extract dedicated convenience fields:
     * `camera_locations`: list of street intersections when published.
     * `funding_source`: text disclosing grant or municipal funding sources.
     * `policy_links`: list of URLs pointing to external department policy pages or PDFs.
   * Download external ALPR policy PDFs to `data/{slug}/policy.pdf` when direct PDF URLs are present.

4. **Widgets (`Top Offense Types` & `Camera Alert Activity`):**
   * Extract `top_offense_types`: ranked list of search offense categories over the last 30 days.
   * Extract `camera_alert_activity`: total alerts count and breakdown by alert category (e.g. NCIC Warrants, Amber Alerts).

5. **DOM-Level Attribute Extraction for Sharing Networks:**
   * Extract sharing networks using `data-tp-full-value` attributes rather than unstructured text lines, preventing display truncation or line-wrap errors.

6. **Local Insignia Archival (`data/{slug}/logo.{ext}`):**
   * Download official agency badges/logos locally to `data/{slug}/logo.{ext}` when an insignia asset URL (`tpHeroLogoImage`) is present.

7. **Cumulative Search Audit Log (`audit.csv`):**
   * When new `audit.csv` rows are retrieved, merge with existing local audit rows deduplicated by `(id, searchDate, userId, reason, offenseType)` so historical searches are preserved indefinitely beyond the 30-day rolling window.

8. **Historical Backfill (`scripts/backfill-portal-data.py`):**
   * Re-parse all 629 pre-existing `page.html` files in `data/` to backfill `stats.jsonl` entries with the new fields without making external network calls.

---

## Consequences

### Positive
* Complete historical fidelity of all public Flock Safety disclosures.
* Zero data loss from policy truncation.
* Transparency into specific camera deployments (intersections) and policy manuals (PDFs) wherever published.
* Permanent retention of audit search logs across time.
* Independent local preservation of official agency insignia.

### Negative / Trade-offs
* Slightly larger `stats.jsonl` entries per agency run.
* Binary storage of logos and policy PDFs (mitigated by only downloading once when assets do not change).
