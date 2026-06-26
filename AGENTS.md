# Scraper notes for AI agents

## TODO — Next session

- **Playwright stealth / "tread lightly"**: Investigate Playwright/stealth settings to reduce Cloudflare detection. The scraper currently works but health check (requests-only) gets blocked. Scraper itself may benefit from more careful browser fingerprint management.

## Committed fixes

- `describe-diff.py`: Changed/new were slug-only lists but unpacked as `(slug, desc)` tuples → ValueError. Fixed 2e9c37d.
- `describe-diff.py`: Subject included "X unchanged" which reads confusingly ("update 8 agencies (8 unchanged)" means nothing changed but reads as contradiction). No longer emits "unchanged" in subject. Skip commit entirely when no meaningful change (all stats identical, no page/other file changes). Workflow guards against empty commit message. Fixed 85d66a7.
- `scrape-flock.py`: Cloudflare Error 1015 rate-limit pages had title "Access denied | ... Cloudflare" which didn't match the "Just a moment" check. Pages were saved as if they were real data (empty stats, error HTML). Fixed by checking the HTTP response status code from `page.goto()`: 429 = rate limited. Also checks body text for "Error 1015" per Cloudflare docs (1XXX errors appear in HTML body, not status header). Fixed ae67732, 794d5ff.
