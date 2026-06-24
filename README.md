# Flock Safety Transparency Portal Scraper

Git-scraping project that monitors Flock Safety subscriber transparency portals for Washington state agencies. Runs daily via GitHub Actions.

## What it does

- Fetches the agency list from haveibeenflocked.com (curl-based)
- Refreshes the list of Washington state agency slugs
- Scrapes each WA agency's transparency portal via Playwright + Xvfb (bypasses Cloudflare)
- Captures structured stats: cameras, vehicles detected, hotlist hits, searches, retention, agencies with access, policies
- Saves raw HTML, extracted text, and parsed JSON per agency per day
- Commits changes to git so you can track changes over time

## Data format

```
data/YYYY-MM-DD/
  _summary.json              # Run summary (OK/failed counts)
  <agency-slug>/
    page.html                # Raw page HTML
    page.txt                 # Extracted plain text
    stats.json               # Parsed stats
```

## Current Washington agencies tracked (~38)

Arlington, Bonney Lake, Centralia, College Place, Des Moines, Eatonville, Edmonds, Ellensburg, Everett, Kent, Lake Stevens, Lakewood, Lynnwood, Marysville, Medina, Mill Creek, Monroe, Moses Lake, Mount Vernon, Newcastle, Olympia, Prosser, Puyallup, Renton, Richland, SeaTac, Selah, Shelton, Skamania County SO, Snohomish County SO, Spokane County SO, Stanwood, Sumner, Toppenish, Tukwila, Walla Walla, Yakima, Yelm

## Local dev

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
python3 -m playwright install chromium
xvfb-run -a python3 scrape-flock.py
```