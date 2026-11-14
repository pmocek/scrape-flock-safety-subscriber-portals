# Task: Decouple Global Analysis Summaries from Batch Scraper Commits

## Summary

Batch scraper commits (running every 2 hours via `.github/workflows/scrape.yml`) contain repetitive, static commit message bodies listing the identical top-10 audit search reason outliers and identical nationwide NCIC contradiction counts on every run, regardless of which agencies actually changed.

This task decouples global audit and NCIC analysis from routine batch scrape commits, restoring clean, diff-scoped commit logs driven solely by `scripts/describe-diff.py`.

---

## Background & Applicable Architecture Decisions

* **ADR 002 (Public Transparency Portal Data Expansion and DOM Extraction — `adr/002-portal-data-expansion.md`):**
  * Decision #7 (*Cumulative Search Audit Log*): Deduplicates and merges `audit.csv` records across rolling 30-day windows into `data/{slug}/audit.csv`. Audit rows are preserved permanently.
  * *Impact:* Because audit records never expire from the local dataset, any search reason ever flagged as an outlier (vague phrases like `"investigation"`, raw case numbers, or DPA violations) persists indefinitely in `data/*/audit.csv`.
* **ADR 001 (Directional Flock Safety data-sharing relationships — `adr/001-directional-sharing-data.md`):**
  * Establishes directional bilateral relationship tracking for NCIC contradiction detection across the entire nationwide network graph.
* **AGENTS.md Commit Conventions:**
  * Requires atomic commits with meaningful commit bodies describing changes.

---

## Bug Description & Root Cause

### Observed Symptoms

Every 2-hour data commit (e.g. `db354e36`, `fee4b375`, `5694ca0f`, `8cd4c2e7`) appends an identical block of 25 lines to the commit body:

```text
Audit findings:
COMMIT_BODY: Audit outliers:
COMMIT_BODY:  vague brawley-ca-pd: investigation
COMMIT_BODY:  vague cranbury-nj-pd: INVESTIGATION
COMMIT_BODY:  vague eaton-co-pd: Investigation
COMMIT_BODY:  vague golden-co-pd: investigation
COMMIT_BODY:  vague isle-of-palms-sc-pd: investigation
COMMIT_BODY:  vague livingston-ca-pd: Investigation
COMMIT_BODY:  vague lucas-county-oh-so: investigation
COMMIT_BODY:  vague luray-va-pd: INVESTIGATION
COMMIT_BODY:  vague lynn-haven-fl-pd: Investigation
COMMIT_BODY:  vague mukilteo-wa-pd: AL SCSO
COMMIT_BODY:  vague ... and 6 more (of 16 total)
COMMIT_BODY:  case-number-only brawley-ca-pd: 10851
COMMIT_BODY:  case-number-only brawley-ca-pd: 211
COMMIT_BODY:  case-number-only brawley-ca-pd: 459
COMMIT_BODY:  case-number-only livingston-ca-pd: 10851
COMMIT_BODY:  case-number-only ottawa-county-mi-so: 2026-09090083
COMMIT_BODY:  case-number-only sumner-wa-pd: 2615701827
COMMIT_BODY:  case-number-only sumner-wa-pd: 2618800695
COMMIT_BODY:  case-number-only sumner-wa-pd: 2619002651
NCIC findings:
COMMIT_BODY: NCIC contradiction findings:
COMMIT_BODY:  contradiction-a: 151 agencies (prohibits immigration + national hotlists)
COMMIT_BODY:  sharing-backdoor: 133 relationships
COMMIT_BODY:  indirect-chain: 258 chains across 87 start nodes
COMMIT_BODY:  no-immigration-prohibition: 726 agencies
```

### Root Cause Analysis

1. **Global Scope in Batch Pipeline:**
   * In `.github/workflows/scrape.yml`, steps `audit` and `ncic` execute `scripts/analyze-audit.py --commit-body` and `scripts/ncic-contradiction.py --commit-body`.
   * Both scripts evaluate the entire repository (`DATA_DIR.glob("*/audit.csv")` and `DATA_DIR.iterdir()`), having no awareness of which batch or agencies were scraped in the current run.
2. **Deterministic Alphabetical Slicing:**
   * Commit `d893b066` capped printed audit outliers to 10 entries to fix previous 120+ KB commit bodies (e.g. `29b73516`).
   * Because `emit_commit_body()` sorts by `(slug, reason)` and slices `[:10]`, agencies alphabetically early (`brawley-ca-pd`, `cranbury-nj-pd`, `eaton-co-pd`, etc.) permanently occupy the 10 slots.
3. **Macro Metrics in Micro Commits:**
   * NCIC contradictions summarize global macro state (726 agencies without immigration prohibitions, 151 with contradictions). These totals rarely change between 2-hour batches and are already tracked in `docs/immigration-ncic/conflict-matrix.md` and `website/data/ncic-matrix.json`.
4. **Unstripped Protocol Marker:**
   * In `.github/workflows/scrape.yml`, `grep "^COMMIT_BODY:"` captures lines without stripping the prefix, leaving raw `COMMIT_BODY:` text in commit messages.

---

## Suggested Remedy (Decoupled Global Summaries)

### 1. Simplify `.github/workflows/scrape.yml`

* **Remove commit body capture from batch scrape:**
  * Delete the `Analyze audit CSVs` step (`steps.audit`) from `scrape.yml`, or remove the `--commit-body` output capture.
  * Delete the `Detect NCIC contradictions` step (`steps.ncic`) from `scrape.yml`, or remove the `--commit-body` output capture.
  * Keep `Refresh NCIC conflict matrix` (`scripts/ncic-contradiction.py --wa-matrix > docs/immigration-ncic/conflict-matrix.md`) and `Export health dashboard data` (`scripts/export-health-data.py`) as they produce file artifacts that only stage when contents genuinely change.
* **Streamline the commit step:**
  * Build the commit subject and body solely from `scripts/describe-diff.py`:
    ```bash
    MSG=$(python3 scripts/describe-diff.py)
    if [ -z "$MSG" ]; then
      echo "Nothing meaningful changed — skipping commit"
      exit 0
    fi
    git commit -m "$MSG"
    ```

### 2. Maintain Global Analysis in Dedicated Reporting Workflows

* Ensure global audit and NCIC analysis outputs continue to update site dashboards and reporting docs:
  * In `.github/workflows/pages.yml` (runs when publishing the GitHub Pages companion site), verify `scripts/analyze-audit.py` and `scripts/ncic-contradiction.py` run to refresh `website/data/*.json`.
  * If periodic summary reports in git log are desired, create a separate daily workflow (e.g. `reports.yml`) or run it on schedule once per day as a distinct commit (`report: daily audit outliers and contradiction summary`).

### 3. Update Documentation & Conventions

* **`AGENTS.md`:**
  * Update the commit conventions section: clarify that batch data commits are scoped to data deltas via `describe-diff.py`.
  * Note that global audit and NCIC scans run during site builds or reporting passes, not appended to every 2-hour batch commit.
* **`doc/PLANNING.md`:**
  * Record completion of this fix in the project roadmap.

---

## Verification Plan

1. **Simulate Commit Message Generation:**
   * Stage a sample data change: `git add data/<slug>/stats.jsonl`.
   * Run `python3 scripts/describe-diff.py`.
   * Verify output contains only `data: update 1 agencies (1 with changes)` and the specific agency change delta.
   * Verify no `COMMIT_BODY:`, audit outlier lists, or NCIC count blocks are present.
2. **Verify Workflow Syntax:**
   * Check YAML validity of `.github/workflows/scrape.yml`.
3. **Verify Site & Matrix Generators Remain Functional:**
   * Run `python3 scripts/ncic-contradiction.py --wa-matrix > /dev/null`.
   * Run `python3 scripts/export-health-data.py`.
   * Confirm exit code 0 and non-destructive outputs.
