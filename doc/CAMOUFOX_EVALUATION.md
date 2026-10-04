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
    python3 -m camoufox fetch
```
No `xvfb-run` wrapper is required when running under Camoufox.
