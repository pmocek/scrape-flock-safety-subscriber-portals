# Technical Evaluation: Camoufox for Cloudflare Evasion

## 1. Overview

[Camoufox](https://camoufox.com/) is an open-source anti-detect browser built on a custom C++ patched build of Mozilla Firefox. It is specifically designed to bypass advanced bot mitigation systems (such as Cloudflare Turnstile, Cloudflare WAF / Error 1015, DataDome, and Kasada) by eliminating the browser leaks inherent to Chromium-based automation.

In Python, Camoufox exposes an API compatible with Playwright (`from camoufox.async_api import AsyncCamoufox`), making it a direct candidate to augment or replace our current Playwright Chromium + `playwright-stealth` pipeline.

---

## 2. Comparison: Current Setup vs. Camoufox

| Feature | Current: Playwright Chromium + Stealth | Proposed: Camoufox |
| :--- | :--- | :--- |
| **Browser Engine** | Chromium (Google Chrome engine) | Modified Mozilla Firefox (Gecko engine) |
| **Evasion Method** | JavaScript runtime injection (`playwright-stealth` overrides properties like `navigator.webdriver`, permissions, chrome runtime). | **C++ Native Injection**: Fingerprint properties (Canvas, WebGL, AudioContext, Navigator, Screen, Fonts, WebRTC) are modified directly in the browser's C++ source code before JavaScript ever executes. |
| **CDP / Automation Leaks** | Chrome DevTools Protocol (CDP) exposes automation artifacts detectable by Cloudflare's `precursor/main.js`. | No CDP; uses native Marionette/WebDriver protocol without automation flags. |
| **TLS & HTTP/2 Fingerprint** | Python/Node HTTP stack or standard Chromium TLS fingerprint (JA3/JA4) which Cloudflare flags when mismatched with HTTP headers. | Accurate, human-like Firefox TLS Client Hello and HTTP/2 settings matching the exact OS and user agent. |
| **Headless Execution** | Requires `headless=False` wrapped with `xvfb-run` (virtual X11 server) to avoid Cloudflare's basic headless checks. | Native headless mode (`headless=True`) engineered to appear identical to real headful desktop instances without `xvfb`. |
| **CI Dependencies** | Requires `sudo apt-get install xvfb` and `.venv/bin/python3 -m playwright install-deps chromium`. | Self-contained prebuilt Firefox binaries downloaded via `camoufox fetch`; no virtual display server required. |

---

## 3. Why This Matters for Flock Scraping

1. **Elimination of `xvfb-run`:**
   Currently, `.github/workflows/scrape.yml` and `health-check.yml` must install system X11 packages and wrap script invocations with `xvfb-run -a`. Camoufox's native headless mode eliminates this dependency entirely.
2. **Mitigation of Cloudflare Error 1015 (Rate Limiting):**
   Cloudflare Error 1015 ("You are being rate limited") is triggered not merely by request volume, but by anomaly scores calculated from TLS fingerprints, JavaScript execution speed, and canvas challenges. Camoufox generates diverse, realistic fingerprint seeds across runs, lowering Cloudflare's edge threat score.
3. **Turnstile / Bot Challenge Bypass:**
   When Cloudflare presents a "Just a moment..." verification page, Camoufox passes the client-side precursor verification without manual intervention.

---

## 4. Implementation & CI Architecture

### A. Python Integration
Camoufox integrates directly with async Python:

```python
from camoufox.async_api import AsyncCamoufox

async def scrape_portal(slug):
    async with AsyncCamoufox(
        headless=True,
        geoip=True,  # Match timezone, locale, and WebRTC to IP
        os=["windows", "linux", "macos"],  # Realistic OS fingerprint pool
    ) as browser:
        page = await browser.new_page()
        response = await page.goto(f"https://transparency.flocksafety.com/{slug}", wait_until="domcontentloaded")
        html = await page.content()
        return html
```

### B. Dual-Engine Support in `scrape-flock.py`
To ensure maximum reliability without breaking existing workflows, `scrape-flock.py` can support an `--engine` argument:
* `--engine=playwright` (default for backward compatibility)
* `--engine=camoufox` (opt-in or fallback when Cloudflare blocks are encountered)

### C. GitHub Actions Setup
In `.github/workflows/scrape.yml`:
```yaml
- name: Install Camoufox
  run: |
    uv pip install "camoufox[geoip]"
    .venv/bin/python3 -m camoufox fetch
```
No `xvfb-run` wrapper is required when running under Camoufox.

---

## 5. Implementation Status (verified 2026-10-12)

The `--engine` flag and CI wiring already existed but **had never successfully run**.
`launch_browser()` passed `os=["windows","macos","linux"]`, and current `fpgen` expects a
single OS string, so the path raised:

```
fpgen.exceptions.InvalidConstraints: The passed function (...) yielded no
possible values for "os"
```

This fires during fingerprint generation, i.e. before a browser ever launches. The
`scrape.sh` guard hides it: `if $PYTHON -c "import camoufox"` succeeds, so the script
prints "Camoufox available" and then gets no data — another instance of the silent-failure
pattern in `AGENTS.md`.

### Verification

| Check | Result |
|---|---|
| `camoufox fetch` | v156.0.1-beta.36 installed |
| Headless scrape, no `xvfb` | 8/8 slugs OK in 94s, 0 blocked |
| Data parity vs Playwright | identical (`auburn-wa-pd`: 6417 chars, 40 cameras from both) |
| GitHub Actions dispatch | `success`, "Camoufox available — no Xvfb", batch 9/12 |

### Findings

1. **`os` is a single value, not a list.** `CAMOUFOX_OS` env var pins it explicitly;
   unset, Camoufox selects for itself, which is preferable.
2. **Content renders around 4s**, not immediately. An early `inner_text` can return an
   empty string even when the page is healthy — the scraper's 8s settle covers this, but
   ad-hoc probes must not assume immediate content.
3. **HTTP 403 with fully-rendered content is normal** on this site and is *not* a
   Cloudflare block. Both engines see it. Detection must key on interstitial text
   ("Just a moment" / "Error 1015"), never on status code alone.
4. **Camoufox does not reduce parse quality.** Identical extracted stats to Playwright.

### Recommendation

Keep Playwright as the default for scheduled runs. Camoufox is a viable fallback when
Playwright's fingerprint starts getting blocked, and it drops the `xvfb-run` dependency.
Do not switch the default without first observing a sustained block rate under Playwright —
Camoufox's advantage here is unproven in production because it has never run long enough
to accumulate comparable data.
