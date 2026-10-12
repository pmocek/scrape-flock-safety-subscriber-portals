# Flock Safety, the NCIC Immigration Violator File, and the "Prohibited Use" That Isn't

*A data-driven conflict analysis of Washington State law enforcement agencies.*

---

## The short version

Most Flock Safety transparency portals have a **Prohibited Uses** section. Many of those
portals list **"immigration enforcement"** as prohibited. That reads like a guarantee.
It is not one.

The same portal, a few lines down, frequently lists **"National and statewide hotlist
sources"** among the agency's subscribed hotlists. That is Flock's bundle of FBI NCIC
topics — and one of the topics inside NCIC is the **Immigration Violator File**, a database
that, per the NCIC operator manual, is populated *exclusively* by ICE and maintained by
*no other agency*. Records in it are derived from administrative warrants issued by ICE
agents without any judicial review. The manual explicitly contemplates vehicle and
license-plate data being entered into those records.

So the agency has, in its own published configuration:

1. declared that it will not use its cameras for immigration enforcement, **and**
2. subscribed to the one data source that exists specifically to tell it when a vehicle
   ICE is looking for has been seen.

Flock Safety states that the local agency receives the alert, not ICE. But the alert is
the enforcement. An agency that is pinged that a specific car ICE wants has just been told
where to find it. Nothing in the hotlist subscription is passive.

This project scrapes those portal configurations continuously so the conflict can be
tracked over time rather than argued about. **30 of 74** Washington State agencies with
live portals currently exhibit it.

---

## Why the NCIC Immigration Violator File is different from every other hotlist

Most Flock hotlists are curated from many sources: stolen vehicles, missing persons,
felony warrants. Any agency can add to them. The Immigration Violator File is structurally
unlike all of them:

- **Single-authority.** ICE is the only agency permitted to enter or maintain records. The
  FBI curates and pushes the list, but the content is ICE's alone.
- **Not judicially reviewed.** The underlying documents are ICE administrative warrants,
  issued by ICE agents, not by a magistrate.
- **Designed for vehicle correlation.** The operator manual states that where ICE has
  reasonable grounds to believe a subject may be operating a particular vehicle or a
  vehicle bearing a particular plate, the vehicle or plate data *may be included in the
  record*.

That last point is what makes the Flock subscription doctrinally significant. An ALPR
network is not a passive subscriber to a list of names. It is a continuous, nationwide
sensor grid that can resolve an abstract record into a physical location in seconds. Wiring
ICE's warrant data into that grid converts a list of names into a live map.

---

## The Maass contradiction

Dave Maass's June 2026 EFF investigation
([deeplinks/2026/06](https://www.eff.org/deeplinks/2026/06/are-your-local-police-using-flock-safety-alprs-scan-immigrants))
documented agencies whose transparency portals simultaneously listed immigration
enforcement as a prohibited use and showed the Immigration Violator topic enabled in their
NCIC subscription.

We call this the **Maass contradiction**, and we automate its detection in
[`scripts/ncic-contradiction.py`](../../scripts/ncic-contradiction.py). The name is
Maass's, not ours — he found it first, by filing public records requests one agency at a
time. This repo does it at scale, every two hours, for 785 portals.

### Detection logic

The contradiction requires **both** conditions to hold for an agency:

| Signal | Source | Detection |
|---|---|---|
| Prohibits immigration enforcement | `prohibited_uses` in portal JSON | regex `(?i)\bimmigra` |
| Subscribes to national hotlists | `hotlists` field | regex `(?i)\bnational\b` |

Nationally, **137 of 785** agencies match. In Washington State, **30 of 74**.

Note the second column is a *bundle* check, not a per-topic check. Flock does not publish
which NCIC topics a given agency has individually enabled; agencies publish which bundles
they subscribe to. A subscription to "National and statewide hotlist sources" therefore
means *the Immigration Violator topic is available and unfiltered for that agency* — which
is precisely the configuration EFF documented. Whether a specific agency has the topic
ticked cannot be determined from public data; it is only obtainable through a records
request. Our claim is about **exposure and configuration**, not proven violation.

---

## The Washington legal overlay

### Keep Washington Working Act (2019, RCW 43.17.425 / 10.93.160)

Washington's longstanding rule bars state and local agencies from using their resources
for civil immigration enforcement: no asking about immigration status, no detaining on
ICE administrative warrants, no sharing personal information with ICE or CBP, no holding
on ICE detainers. Where a federal request conflicts, the state side prevails.

### The Driver Privacy Act — SB 6002 (signed 2026-03-30)

Washington's first ALPR-specific statute. Among its provisions:

- Unlawful to use an ALPR for immigration investigation or enforcement.
- Unlawful to use ALPR data to track access to protected health care, places of worship,
  schools, courts, food banks, or facilities conducting an immigration matter.
- **Vendors must provide technical controls preventing unauthorized data sharing, secondary
  transfer, or access by nonauthorized agencies, including federal civil immigration
  enforcement.** (Sec. 3(6))
- A positive ALPR match alone does not constitute reasonable suspicion to stop a vehicle.
- Agencies must register systems with the Attorney General's office within 180 days.
- Willful violation is a gross misdemeanor.

That vendor-control mandate is the provision that matters most for this analysis. It puts
the obligation on Flock — not merely on the subscribing agency — to build technical
barriers against exactly the secondary transfer these hotlist subscriptions enable. An
agency that ticks the Immigration Violator box is asking the vendor for a capability the
statute now obliges the vendor to technically restrict. The question of whether Flock's
current architecture satisfies Sec. 3(6) is unanswered as of this writing, and is a
legitimate target for a records request or an AG inquiry.

---

## The sharing network: how the contradiction propagates

An agency's Flock-level prohibition is a contractual setting on *its* account. It does not
travel with the data. `scripts/ncic-contradiction.py` builds the bilateral sharing graph
and traces where prohibited-use agencies' data lands.

Nationally:

- **70 agencies** share directly with partners that have no Flock-level prohibition.
- **82 agencies** have multi-hop paths (up to 5 hops) reaching such partners, yielding
  **245 distinct chains**.

The pattern in Washington matches UW Center for Human Rights' October 2025 finding that
Flock data from Washington jurisdictions was reached by US Border Patrol searches labeled
with reasons like "USBP", "immigration", and "DHS" — and by "side door" searches run by
out-of-state officers on ICE's behalf.

Neither path requires any Washington officer to break any rule. Each individual hop looks
routine. The composition does not.

---

## What this analysis does and does not claim

**Claims:**
- These agencies' published Flock configurations contain both a prohibition and a
  subscription to a bundle containing ICE's warrant data.
- In a number of cases their data is shared bilaterally with partners carrying no
  equivalent prohibition.
- Under Washington law, several provisions (KWW, SB 6002 Sec. 3(3) and 3(6)) are directly
  implicated by that configuration.

**Does not claim:**
- That any specific Washington agency has performed an immigration enforcement action via
  Flock. The audit-CSV scanner in `scripts/analyze-audit.py` flags immigration-keyword
  search reasons; keyword presence indicates the *reason field* was written that way, not
  the purpose.
- That Flock's bundle subscription is identical to enabling every topic in it.
- That any agency acted in bad faith. Administrative interface defaults, contract
  inheritance, and vendor-side bundling routinely produce configurations no human
  deliberately chose.

That last point is the one most often missed. **Nobody had to decide to do this.** An
administrator enabled a bundle to get NCIC topic A, and topic B came with it.

---

## What would resolve it

1. **Records requests** for Flock hotlist configuration exports — the actual per-topic
   toggle state, which the public portal does not expose. This is how EFF established its
   findings, and it remains the only path to a per-agency answer.
2. **An AG inquiry** into SB 6002 Sec. 3(6) vendor-control compliance.
3. **Portal schema change** — Flock publishing per-topic hotlist state would end the
   ambiguity entirely. This is a vendor-side fix and the highest-leverage one.
4. **Agency action** — unchecking the Immigration Violator topic is a single settings
   change, but as EFF notes, "if that's where it stops, the infrastructure for immigration
   surveillance stays fully intact, and the system is one policy, personnel change, or
   error away from being switched back on."

---

## Reproducing this

```bash
python3 scripts/ncic-contradiction.py            # full national report
python3 scripts/ncic-contradiction.py --commit-body  # CI integration
```

The matrix in [`conflict-matrix.md`](conflict-matrix.md) is generated by
`scripts/ncic-contradiction.py --wa-matrix`. Live dashboards are published at the
[companion site](https://pmocek.github.io/scrape-flock-safety-subscriber-portals/).

## Sources

- [EFF — Are Your Local Police Using Flock Safety ALPRs to Scan for Immigrants?](https://www.eff.org/deeplinks/2026/06/are-your-local-police-using-flock-safety-alprs-scan-immigrants) (Maass, June 2026)
- [UW Center for Human Rights — Leaving the Door Wide Open](https://jsis.washington.edu/humanrights/2025/10/21/leaving-the-door-wide-open/) (Oct 2025)
- [ACLU-WA — Gov. Ferguson Signs SB 6002, the Driver Privacy Act](https://www.aclu-wa.org/press-releases/gov-ferguson-signs-sb-6002-the-driver-privacy-act-into-law/)
- [RCW 43.17.425 / 10.93.160 — Keep Washington Working Act](https://app.leg.wa.gov/RCW/default.aspx?cite=43.17.425)
- [SB 6002 Session Law](https://lawfilesext.leg.wa.gov/biennium/2025-26/Htm/Bills/Session%20Laws/Senate/6002-S.SL.htm)
- [ACLU of Massachusetts — Flock Gives Law Enforcement All Over the Country Access to Your Location](https://data.aclum.org/2025/10/07/flock-gives-law-enforcement-all-over-the-country-access-to-your-location/)
- [VPM — The feds' hidden immigration weapon](https://www.vpm.org/news/2025-07-07/vcij-immigration-enforcement-flock-safety-license-plate-readers-poggenklass)