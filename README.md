# Flock Safety Transparency Portal scraper

Tracks Flock Safety subscriber data using the [git-scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) pattern.

## What it does

- Fetches the agency list from [eyesonflock.com](https://eyesonflock.com/)
- Scrapes individual agency transparency portals (`transparency.flocksafety.com/*`) via Playwright
- Extracts structured stats: cameras, vehicles, retention, searches, hotlist hits, directional sharing network data
- Directional sharing data is preserved separately: `shares_data_with` (agencies this agency sends data to) and `receives_data_from` (agencies this agency receives data from). Raw `page.txt` is the canonical source; directional data is derived in `stats.jsonl`.
- Aggregated sharing relationships across all agencies are saved to `data/sharing-relationships.json` — each row records a source agency, partner name, direction, and a placeholder for resolved slug.
- Extracts Public Search Audit CSV data where available; scans search reasons for immigration-related terms and potential Driver Privacy Act (SB 6002) violations
- Analyzes all audit CSV reasons across agencies — categorizes them, flags federal agency references, vague entries, case-number-only reasons, and on-behalf-of (OSA) patterns
- Detects Cloudflare blocks via HTTP status code (429) and body text ("Error 1015") — blocks are logged separately, not conflated with data
- Commits meaningful changes to git for change tracking over time; skips commits when nothing changed (e.g. all agencies blocked)

## How it runs

**Primary:** GitHub Actions — two scheduled workflows:

- **Scraper** (`.github/workflows/scrape.yml`): runs 6x daily (every 4 hours), staggered batches to avoid burst detection. Each scheduled run scrapes ~6 agencies. Push/`workflow_dispatch` scrapes the full list. After scraping, runs audit CSV analysis and appends outlier findings to the commit message body.
- **Health check** (`.github/workflows/health-check.yml`): runs hourly via Playwright to detect prolonged outages. Lists errored/blocked agencies in the commit message body. Fails loudly (exit 1) when >50% of agencies are unreachable.

**Local development:** `./scrape.sh` runs the full pipeline locally, wrapping `scrape-flock.py` (requires Playwright + Xvfb for browser-based scraping).

## Files

| File | Purpose |
|------|---------|
| `scrape.sh` | Entry point — refreshes agency list, runs Playwright scraper |
| `scrape-flock.py` | Playwright-based scraper for Cloudflare-protected agency pages |
| `scripts/describe-diff.py` | Generates semantic commit messages from staged `stats.jsonl` diffs |
| `scripts/health-check.py` | Playwright-based health check; lists errored/blocked agencies in commit body |
| `scripts/analyze-audit.py` | Categorizes audit CSV search reasons, flags DPA violations and outliers |
| `download.sh` | Refreshes `wa-agencies.json` from eyesonflock.com |
| `wa-agencies.json` | Cached list of WA agency slugs |
| `requirements.txt` | Python dependencies (playwright, playwright-stealth) |
| `AGENTS.md` | Development notes and fix history for AI agents |

## Output format

Each agency saves into `data/{slug}/`:

| File | How it updates |
|------|---------------|
| `stats.jsonl` | Append-only — one JSON line per successful scrape with `ts` key, extracted stats, directional sharing data (`shares_data_with`, `receives_data_from`), and `audit_immigration_entries`/`audit_immigration_reasons` if the audit CSV had immigration-related search reasons |
| `page.html` | Overwritten — full rendered HTML of the portal page |
| `page.txt` | Overwritten — visible text extracted from the page (canonical source for directional sharing data) |
| `audit.csv` | Overwritten — Public Search Audit CSV, if the agency publishes one |
| `blocked.jsonl` | Append-only — records Cloudflare block events (never pollutes `stats.jsonl`) |
| `health.jsonl` | Append-only — written by the health-check workflow |
| `sharing-relationships.json` | Generated — aggregated directional relationships across all agencies (`data/`) |

Git commits only when `describe-diff.py` detects meaningful changes. Runs where every agency is blocked produce no commit.

## Batching (avoiding bursts)

GitHub Actions runs the scraper 6 times per day (every 4 hours). Each
scheduled run scrapes one batch of ~6 agencies so traffic is spread
across 24 hours naturally without idle sleep in CI.

On `push` or `workflow_dispatch`, the full agency list is scraped.

To run a specific batch locally:

    python3 scrape-flock.py --batch 3 --total-batches 6

## Cloudflare handling

The scraper bypasses Cloudflare's JS challenge using Playwright with
stealth plugins. If rate-limited (HTTP 429 / Error 1015), it retries 3
times with backoff. After exhaustion, the block is logged to
`blocked.jsonl` — the previous successful data snapshot in `stats.jsonl`
is left untouched.
