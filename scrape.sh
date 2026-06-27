#!/usr/bin/env bash
# Flock Safety Transparency Portal scraper
# Downloads agency list + scrapes individual agency pages
# Works both locally (with .venv) and in GitHub Actions CI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== $(date -u -Iseconds): Scraping Flock Safety agencies ==="

# 1. Agency list from eyesonflock.com (curl-based, no Cloudflare)
./download.sh 'https://eyesonflock.com/api/v1/data'

# 2. Determine Python and Playwright setup
if [ -d ".venv" ]; then
  # Local development — use virtualenv
  PYTHON=".venv/bin/python3"
else
  # GitHub Actions — use system Python
  PYTHON="python3"
fi

# 3. Check for xvfb (needed for Playwright stealth to bypass Cloudflare)
XVFB_RUN=""
if command -v xvfb-run &>/dev/null; then
  XVFB_RUN="xvfb-run -a"
fi

# 4. Run Playwright-based scraper for individual agency portals
if $PYTHON -c "import playwright" 2>/dev/null; then
  echo "Playwright available — scraping individual agency portals..."
  $XVFB_RUN $PYTHON scrape-flock.py --refresh-agencies 2>&1 || echo "  (refresh-agencies step non-fatal)"

  if [ -n "$XVFB_RUN" ]; then
    $XVFB_RUN $PYTHON scrape-flock.py "$@" 2>&1 || echo "  (agency scrape step non-fatal)"
  else
    echo "  No Xvfb available — skipping browser-based agency scraping."
    echo "  Only eyesonflock.com list will be updated."
  fi
else
  echo "Playwright not installed — scraping eyesonflock.com agency list only."
fi

echo "=== Done: $(date -u -Iseconds) ==="