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
  * API endpoints: `https://api.flocksafety.com/`, `https://hpnotiq.flocksafety.com/`
* **Search Audits:** Search queries performed by police officers are logged centrally and exposed in rolling 30-day windows on transparency portals.
* **Lack of IP Firewalling:** Because cameras communicate over commercial cellular IoT SIMs (AT&T FirstNet, T-Mobile), traffic originates from mobile carrier Carrier-Grade NAT (CGNAT) pools (e.g., `100.64.0.0/10`). Because these IP addresses are dynamically assigned and shared across millions of general cellular subscribers, **Flock's cloud servers cannot enforce IP allowlisting or firewalling**. Ingestion endpoints must remain globally reachable on the public internet.

### C. Firmware Reverse Engineering & Authentication Breakdown (Micah Lee / Wired / 404 Media)
In investigations published by Micah Lee, *Wired*, and *404 Media* (following hardware acquisition and firmware leaks analyzed by collective *stegan0gram*), the internal architecture of Flock cameras was exposed:

1. **Operating System & Kernel:**
   * Cameras run an outdated, end-of-life build of **Android 8.1 (Oreo)** on a Qualcomm Snapdragon SoC (e.g., SDM450) with an obsolete **Linux 3.18** kernel.
   * Internal camera logic is implemented as standard Android services and APKs (`com.flocksafety.android.camera`, `com.flocksafety.android.common.lib`).

2. **Hardcoded Shared Authentication Keys:**
   * Embedded directly in the decompiled Java code of `com.flocksafety.android.common.lib` was a static, hardcoded API key:
     ```text
     HaJ3FgupAm8RrDJW3MHgT9X7Ft27eVaD
     ```
   * All deployed Falcon cameras utilized this identical shared key to authenticate initial bootstrap and registration requests to Flock's backend (`hpnotiq.flocksafety.com`).
   * Device enrollment was authenticated simply by transmitting this hardcoded key along with the camera's hardware MAC address.

3. **Plaintext Persistent Partitions Surviving OTA Updates:**
   * To prevent field units from bricking or losing network credentials during over-the-air (OTA) software updates, Flock configured an unencrypted persistent partition (such as `/persist` or `/data/flock`).
   * This partition stored critical operational secrets in **unencrypted plaintext**, including:
     * Auth0 client IDs, client secrets, and device OAuth2/JWT tokens.
     * Temporary AWS S3 credentials for direct image ingestion buckets.
     * Device private keys and mutual TLS client certificates.
     * Wi-Fi credentials and cellular APN connection strings.
     * Exact physical GPS coordinates logged at device boot.
     * The device's local disk encryption volume keys.

4. **Security & Architectural Implications:**
   * **No Network Perimeter Defense:** As established above, carrier CGNAT prevents network-level IP filtering. Cloud endpoints rely 100% on application-layer authentication.
   * **Trivial Impersonation & Ingestion Spoofing:** With cloud endpoints open to the world, a hardcoded global API key, and predictable hardware identifiers (MAC addresses), authenticating to the Flock cloud server requires no proprietary cryptographic handshake. An adversary with credentials extracted from a single lawfully acquired camera or leaked firmware image can communicate directly with the cloud ingestion backend, potentially spoofing plate reads, injecting false hotlist hits, or monitoring device fleet telemetry.

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
