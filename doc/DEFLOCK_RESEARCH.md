# Community Research & Reverse-Engineering: DeFlock and ALPR Ecosystem

## 1. Executive Summary

This document synthesizes public intelligence, reverse-engineering findings, and data methodologies developed by civil liberties researchers and open-source intelligence (OSINT) groups monitoring **Flock Safety** mass surveillance infrastructure.

Key projects analyzed include:
* **DeFlock** ([deflock.me](https://deflock.me/)): Crowdsourced geospatial mapping of ALPR cameras into OpenStreetMap.
* **EyesOnFlock** ([eyesonflock.com](https://eyesonflock.com/)): Aggregation of subscriber transparency portals nationwide.
* **HaveIBeenFlocked** ([haveibeenflocked.com](https://haveibeenflocked.com/)): Public search audit query tool.
* **Hardware & RF Teardowns**: Independent hacker and security research analyzing camera edge compute, cellular telemetry, and solar hardware.

---

## 2. DeFlock Data Architecture & OpenStreetMap Tagging

[DeFlock](https://deflock.me/) (created by Will Freeman with legal backing from the Electronic Frontier Foundation) tracks the physical expansion of ALPR cameras using **OpenStreetMap (OSM)** as its decentralized spatial database.

### Standardized OpenStreetMap ALPR Taxonomy
When community members map a Flock camera via DeFlock mobile apps or OSM editors (iD / JOSM), the camera node receives standardized key-value tags:

```osm
man_made=surveillance
surveillance=outdoor
surveillance:type=ALPR
camera:type=fixed
camera:mount=pole             # or street_lamp, traffic_signals
camera:direction=180          # degrees azimuth pointing towards vehicle traffic
operator=Flock Safety         # or local subscriber (e.g. "Auburn Police Department")
ref=F-12345                   # physical sticker serial number on device or solar panel
power_source=solar            # or mains
```

### Overpass API Querying
We can programmatically retrieve all known physical Flock cameras in any jurisdiction (such as Washington State) using the Overpass QL API:

```overpass
[out:json][timeout:30];
area["ISO3166-2"="US-WA"]->.wa;
(
  node["surveillance:type"="ALPR"]["operator"~"Flock",i](area.wa);
  node["surveillance:type"="ALPR"]["camera:mount"](area.wa);
);
out body;
>;
out skel qt;
```

---

## 3. Hardware & Network Reverse-Engineering Findings

Security researchers and hardware teardowns have documented the physical and communications architecture of Flock Safety's primary camera devices:

### A. Core Hardware Components
1. **Flock Falcon (Standard ALPR):**
   * **Optics & Sensor:** High-speed global shutter image sensor paired with pulsed infrared (850nm / 940nm) LED arrays to illuminate retroreflective license plates in day and total darkness.
   * **Edge SoC / Processing Board:** Embedded Linux system-on-chip running an optimized convolutional neural network (CNN) for real-time edge ALPR, OCR, and vehicle attribute classification ("Flock Vehicle Fingerprint": color, make, model, body style, roof racks, bumper stickers, missing plates).
   * **Cellular Telemetry:** Quectel or Sierra Wireless LTE Cat-M1 / Cat-4 cellular modem with multi-carrier IoT eSIMs (primarily AT&T and T-Mobile). Cameras do not rely on local Wi-Fi or city municipal networks; they transmit directly to Amazon Web Services over cellular uplinks.
   * **Power Subsystem:** 12V 30W–50W monocrystalline solar panel coupled with a lithium iron phosphate ($LiFePO_4$) battery enclosure mounted to the pole.

2. **Flock Sparrow (Neighborhood / HOA ALPR):**
   * Lightweight, lower-power variant designed for residential sub-divisions, private drives, and small municipal installations.

3. **Flock Raven (Acoustic Audio Sensor):**
   * Acoustic array detecting gunshots and impulsive noises, triangulating location using cellular time-difference-of-arrival (TDOA) algorithms.

4. **Flock Condor (PTZ Live Video):**
   * Live streaming pan-tilt-zoom optical camera designed for real-time situational monitoring, often integrated directly alongside Falcon ALPR units.

### B. Network Traffic & Cloud Architecture
* **Upload Targets:** Captured plate events, high-resolution vehicle stills, and search sessions are uploaded via TLS to Flock cloud infrastructure hosted in AWS US-East:
  * Public assets: `https://prod-flock-org-files-public.s3.us-east-1.amazonaws.com/`
  * API endpoints: `https://api.flocksafety.com/` (protected by mutual TLS and OAuth2/JWT).
* **Search Audits:** Search queries performed by police officers are logged centrally and exposed in rolling 30-day windows on transparency portals.

---

## 4. Intersection with Our Scraper & Synergies

Our repository captures administrative, policy, and usage disclosures directly from the vendor's official transparency portals. Cross-referencing our dataset with DeFlock's spatial data unlocks several high-value investigations:

1. **Reconciliation of Disclosed vs. Physical Cameras (`total_cameras` vs. OSM Nodes):**
   * Compare an agency’s claimed `total_cameras` from `stats.jsonl` against physical camera counts mapped in OpenStreetMap by DeFlock.
   * Highlight jurisdictions where physical camera counts significantly exceed numbers disclosed to city councils and the public.

2. **Geocoding Disclosed Camera Locations:**
   * In ADR 002, our parser extracts explicit street intersection disclosures from `#more-info` (e.g. Lucas County OH SO listing 34 intersections).
   * We can geocode these intersections to verify whether community mappers have located them in OpenStreetMap, or contribute new high-precision locations back to open databases.

3. **Multi-Hop Backdoor Sharing Mapping:**
   * While DeFlock tracks physical hardware, our scraper tracks the **data sharing graph** (`shares_data_with`, `receives_data_from`).
   * Combining both answers the critical question: *"Even if my city has no Flock cameras, does my police department search cameras in neighboring cities, or does out-of-state federal law enforcement access local cameras?"*
