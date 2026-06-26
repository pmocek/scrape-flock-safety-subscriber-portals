# Scraper notes for AI agents

## TODO — Next session

- **Playwright stealth / "tread lightly"**: Investigate Playwright/stealth settings to reduce Cloudflare detection. The scraper currently works but health check (requests-only) gets blocked. Scraper itself may benefit from more careful browser fingerprint management.

## Committed fixes

- `describe-diff.py`: Changed/new were slug-only lists but unpacked as `(slug, desc)` tuples → ValueError. Fixed 2e9c37d.
- `describe-diff.py`: Subject included "X unchanged" which reads confusingly ("update 8 agencies (8 unchanged)" means nothing changed but reads as contradiction). No longer emits "unchanged" in subject. Skip commit entirely when no meaningful change (all stats identical, no page/other file changes). Workflow guards against empty commit message. Fixed 85d66a7.
