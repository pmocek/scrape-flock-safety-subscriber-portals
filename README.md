# Flock Safety Transparency Portal scraper

Tracks Flock Safety subscriber data using the [git-scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) pattern.

## What it does

- Fetches the agency list from [haveibeenflocked.com](https://haveibeenflocked.com/news/transparency-portals/)
- Scrapes individual agency transparency portals (`transparency.flocksafety.com/*`)
- Extracts structured stats: cameras, vehicles, retention, searches, hotlist hits, external agencies with access
- Commits any changes to git for change tracking over time

## How it runs

**Primary:** GitHub Actions — scheduled daily at 6:23 AM UTC via `.github/workflows/scrape.yml`.
The Playwright-based scraper (`scrape-flock.py`) bypasses Cloudflare using a real (virtual) browser with stealth plugins.

**Local development:** `./scrape.sh` also works locally with `.venv` (Playwright + Xvfb required).

## Files

| File | Purpose |
|------|---------|
| `scrape.sh` | Entry point — runs both the curl-based download and Playwright scrape |
| `scrape-flock.py` | Playwright-based scraper for Cloudflare-protected agency pages |
| `download.sh` | Simon Willison-style curl-based downloader |
| `wa-agencies.json` | Refreshed list of WA agency slugs from haveibeenflocked.com |
| `data/YYYY-MM-DD/` | Daily scrape output, one subdir per agency |
| `.github/workflows/scrape.yml` | GitHub Actions workflow |

## Output format

Each agency scrape saves:
- `page.html` — Full rendered HTML
- `page.txt` — Extracted visible text
- `stats.json` — Structured stats (cameras, vehicles, searches, retention, etc.)

And `_summary.json` per run tracks success/failure per agency.
