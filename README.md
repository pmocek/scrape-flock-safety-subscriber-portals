# Flock Safety Transparency Portal scraper

Tracks Flock Safety subscriber data using the [git-scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) pattern.

## What it does

- Fetches the agency list from [haveibeenflocked.com](https://haveibeenflocked.com/news/transparency-portals/)
- Scrapes individual agency transparency portals (`transparency.flocksafety.com/*`)
- Extracts structured stats: cameras, vehicles, retention, searches, hotlist hits, external agencies with access
- Commits any changes to git for change tracking over time

## How it runs

**Primary:** GitHub Actions — runs 6x daily (every 4 hours) via `.github/workflows/scrape.yml`.
Each scheduled run scrapes a different batch of agencies so traffic is spread across the full day,
avoiding burst detection. The Playwright-based scraper (`scrape-flock.py`) bypasses Cloudflare using
a real (virtual) browser with stealth plugins.

**Local development:** `./scrape.sh` also works locally with `.venv` (Playwright + Xvfb required).

## Files

| File | Purpose |
|------|---------|
| `scrape.sh` | Entry point — runs both the curl-based download and Playwright scrape |
| `scrape-flock.py` | Playwright-based scraper for Cloudflare-protected agency pages |
| `download.sh` | Simon Willison-style curl-based downloader |
| `wa-agencies.json` | Refreshed list of WA agency slugs from haveibeenflocked.com |
| `data/{slug}/` | Per-agency output, one subdir per agency (overwritten each run) |
| `.github/workflows/scrape.yml` | GitHub Actions workflow |

## Output format

Each agency scrape saves into `data/{slug}/`:
- `stats.jsonl` — Appended each run (one JSON line per snapshot, with `ts` key)
- `page.html` — Full rendered HTML (overwritten)
- `page.txt` — Extracted visible text (overwritten)

Files overwritten in place each run; `stats.jsonl` grows as an append-only log.
Git commits only when data actually changes (`git add -A` + empty-diff check).

## Batching (avoiding bursts)

GitHub Actions runs the workflow 6 times per day (every 4 hours). Each
scheduled run scrapes one batch of ~6 agencies so traffic is spread
across 24 hours naturally without idle sleep in CI.

On `push` or `workflow_dispatch`, the full agency list is scraped.

To run a specific batch locally:

    python3 scrape-flock.py --batch 3 --total-batches 6
