# Scraper notes for AI agents

## Commit conventions

- **Atomic commits**: one logical change per commit
- **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, etc.
- **Commit body** includes audit outlier findings and health check error details when present
- Update README for user-facing changes; update AGENTS.md for things not obvious from repo structure

## Committed features

- `describe-diff.py`: Changed/new were slug-only lists but unpacked as `(slug, desc)` tuples → ValueError. Fixed 2e9c37d.
- `describe-diff.py`: Subject included "X unchanged" which reads confusingly ("update 8 agencies (8 unchanged)" means nothing changed but reads as contradiction). No longer emits "unchanged" in subject. Skip commit entirely when no meaningful change (all stats identical, no page/other file changes). Workflow guards against empty commit message. Fixed 85d66a7.
- `scrape-flock.py`: Cloudflare Error 1015 rate-limit pages had title "Access denied | ... Cloudflare" which didn't match the "Just a moment" check. Pages were saved as if they were real data (empty stats, error HTML). Fixed by checking the HTTP response status code from `page.goto()`: 429 = rate limited. Also checks body text for "Error 1015" per Cloudflare docs (1XXX errors appear in HTML body, not status header). Fixed ae67732, 794d5ff.
- `health-check.py`: Used `urllib.request.urlopen()` which gets Cloudflare-blocked. Ported to Playwright with headless browser, same detection logic as the scraper. Workflow updated to install Playwright deps and wrap with `xvfb-run`. Fixed in current session.
- `health-check.py` / `.github/workflows/health-check.yml`: Commit message said "1 error" but didn't say which agency or what error. Fixed by emitting `COMMIT_BODY:` lines for each errored/blocked agency with slug and detail. Workflow captures them and passes as second `-m` to `git commit`. Commit now includes body like `edmonds-wa-pd: error (http_404)`.
- `scrape-flock.py`: Added `_scan_immigration_reasons()` that scans audit CSV `reason`/`offenseType` fields for immigration terms (ICE, USBP, HSI, CBP, customs, border patrol, immigration). Results stored in `stats.jsonl` as `audit_immigration_entries` and `audit_immigration_reasons`.
- `scripts/analyze-audit.py` (new): Categorizes all audit CSV search reasons into 26+ categories, flags DPA SB 6002 violation signals (immigration searches, on-behalf-of federal OSA patterns), vague/generic reasons, case-number-only reasons, and rare unique reasons. Supports `--commit-body` flag for CI workflow integration. Workflow runs it after each scrape and includes outlier findings in commit message body.
- `.github/workflows/scrape.yml`: Added "Analyze audit CSVs" step after scraping. Captures `COMMIT_BODY:` lines from `analyze-audit.py --commit-body` and appends them to commit message body as an "Audit findings:" section.
- `scripts/ncic-contradiction.py` (new): Detects NCIC hotlist / immigration enforcement contradictions (Maass contradiction) using 6 detection modes:
  - A) Prohibits immigration + National hotlists = NCIC Immigration Violator File access
  - B) No immigration prohibition at all
  - C) Policy conflicts — prohibits immigration but shares data with non-prohibiting agencies
  - D) Direct sharing backdoor to non-prohibiting partners
  - E) Indirect sharing chains (multi-hop BFS graph traversal up to 5 hops)
  Uses `eyesonflock.com-api-v1-data.json` for partner-name-to-slug matching and graph construction. Supports `--commit-body` flag.
- `.github/workflows/scrape.yml`: Added "Detect NCIC contradictions" step after audit analysis. Captures `COMMIT_BODY:` lines from `ncic-contradiction.py --commit-body` and appends them as an "NCIC findings:" section in commit body.
- `.github/workflows/health-check.yml`: GHA's default `bash -e` was swallowing script output when health-check.py exited with code 1 (>50% agencies unreachable). The `OUTPUT=$(...)` line triggered `-e` before `echo "$OUTPUT"` ran, losing all diagnostic output. Fixed by adding `|| true` and `continue-on-error: true` so output is always captured and commit step always runs.
- `scrape-flock.py` / AGENTS.md: `refresh_agencies()` overwrote `wa-agencies.json` with only eyesonflock.com's 41 WA slugs on every run, discarding slugs added by cross-agency spidering. eyesonflock is a third-party aggregator with ~16% miss rate (8+ real portals not indexed). Fixed by removing `refresh_agencies()` from the daily workflow; eyesonflock API data still downloaded for name-to-slug mapping (NCIC analysis), but no longer used as authoritative agency source.
- `adr/002-portal-data-expansion.md` / `scrape-flock.py` / `scripts/backfill-portal-data.py`: Evaluated Flock portal architecture in comparison to Axon Fusus (ADR 001 in `scrape-axon-communityconnect`). Flock serves pre-rendered SSR HTML behind Cloudflare (no unauthenticated JSON API), requiring Playwright scraping. Expanded data extraction to pull:
  - Exact vendor compilation timestamp (`portal_last_updated` from `<span title="...">`)
  - Agency overview / mission statements (`overview`)
  - Status classification (`portal_status`: active, inactive, not_found)
  - Un-truncated policy texts (removed 500-char cap)
  - Custom `#more-info` / `Additional Info` disclosures (camera street locations, funding sources, external policy links)
  - Interactive widgets (`top_offense_types` and `camera_alert_activity` counts and breakdown)
  - DOM-level `data-tp-full-value` attribute extraction for sharing networks
  - Local asset downloads for agency insignia (`logo.{ext}`) and direct policy PDFs (`policy.pdf`)
  - Cumulative `audit.csv` deduplication and merging across rolling 30-day windows
  - Backfilled all 629 historical HTML snapshots into `stats.jsonl` via `scripts/backfill-portal-data.py`.

## Agency list source

`wa-agencies.json` grows organically through sharing-network spidering.
- eyesonflock API data (`eyesonflock.com-api-v1-data.json`) still downloaded daily for name-to-slug mapping (used by NCIC contradiction detection)
- `refresh_agencies()` (reloading from eyesonflock) no longer runs in the daily scrape workflow
- Initial seed from eyesonflock happened once at project setup; periodic eyesonflock comparison for brand-new agencies would be a separate task

## Project Planning & Task Tracking

This project tracks active roadmap items, features, and research in [`doc/PLANNING.md`](doc/PLANNING.md).
- Prior Beads tasks were migrated and archived in [`doc/PLANNING.md`](doc/PLANNING.md).
- Camoufox anti-detect browser evaluation is documented in [`doc/CAMOUFOX_EVALUATION.md`](doc/CAMOUFOX_EVALUATION.md).
- DeFlock community reverse-engineering and OpenStreetMap ALPR mapping research is documented in [`doc/DEFLOCK_RESEARCH.md`](doc/DEFLOCK_RESEARCH.md).
