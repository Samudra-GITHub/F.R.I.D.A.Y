## 6. God's Eye View layers (ported 29 Oct 2026)

Reference: github.com/bilawalsidhu/gods-eye-view (MIT). The features were re-implemented in this
codebase's stack (Python providers, then globe.gl). No code was copied and CesiumJS was not added.

| Layer | Source (key?) | How it works here | Verified |
|---|---|---|---|
| Satellites (279) | CelesTrak GP elements: stations, visual, gps-ops, weather (no key) | Elements cached 6 h (CelesTrak's 2 h etiquette); positions propagated **locally with SGP4** every 20 s; drawn at true orbital altitude; selecting one draws its ±50 min ground track | ISS matched wheretheiss.at to within the seconds between calls (lat −20.75 vs −21.40, alt 427.2 vs 427.4 km, 7.654 km/s) |
| Aircraft | adsb.lol community ADS-B (no key, ODbL) | Regional query (≤150 nm) around the camera, only when zoomed in; refreshed every 20 s; contacts roster sorted by distance; click-to-track flies in and draws the trail **observed** since you started watching | 369 aircraft near Heathrow; G-HAZL detail with altitude, speed, track, squawk, and source |
| Launches (25) | Launch Library 2 (no key, 15 req/h) | Cached 30 min; pads on the globe; NET times ("in 28 h"), status, rocket, orbit, probability; link to Space Launch Now | Live |
| Active fires | NASA FIRMS (**needs free `FIRMS_MAP_KEY`**) | Without a key, reports `not_configured` and makes no request; with one, shows the 4,000 strongest detections by radiative power | Mocked tests only (no key here) |
| Precipitation | NASA GPM IMERG via GIBS WMS (no key) | A transparent shell just above the surface; refreshed every 30 min | Rendered; alignment checked against the UV mapping |
| Daily imagery | NASA VIIRS NOAA-20 true colour (no key) | Third imagery option ("Daily"), using yesterday's complete global mosaic, up to zoom level 9 | Rendered for 2026-10-28 |
| Sensor styles | — | CSS/SVG display filters: night vision, thermal (iron palette), noir, CRT. **Labelled in the UI as filters, not real sensor data.** | Rendered |

**Deliberately not ported:**
- OpenAI Realtime / Gemini voice: a cloud speech and LLM path, which the brief forbids.
- Public CCTV projection and ALPR (licence-plate camera) locations: surveillance features.
- Ships (AISStream needs a key and a persistent websocket), and Google/Cesium 3D Tiles (keys and a second mapping stack).
- Street-level imagery, traffic simulation, Director scenes, and share links: out of scope for now.

**New dependency:** `sgp4` 2.27 (MIT, 149 kB wheel, no transitive dependencies), added to `pyproject.toml`.
**New endpoints:** `/world/satellites`, `/world/satellites/{norad}/track`, `/world/flights`,
`/world/launches`, `/world/fires`.
**Tests:** +12 backend (orbital math, parsing, honesty on 429/503, no FIRMS call without a key,
caching) and +4 frontend. Totals: 167 backend, 36 frontend.
