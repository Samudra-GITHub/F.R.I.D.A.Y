# Handoff

## Launch (repository-verified)

Backend (PowerShell or Git Bash, from the repository root):
```bash
.venv/Scripts/python -m uvicorn backend.friday.api.app:app --host 127.0.0.1 --port 8000
```
For development, this restarts the server when backend files change, and also works without a console:
```bash
.venv/Scripts/python scripts/dev_backend.py --port 8000
```
Desktop app (dev server on http://127.0.0.1:5173):
```bash
npm --prefix apps/desktop run dev
```
Prerequisites: Ollama running with `qwen2.5:7b` pulled; `pip install -e .[dev]` in `.venv` (now includes `sgp4`). `requirements.lock` records the exact versions tested on this machine (`pip install -r requirements.lock`).

Optional offline recognizer (already installed on this machine):
```bash
.venv/Scripts/pip install -e .[whisper]
```
```bash
.venv/Scripts/python -c "from pathlib import Path; from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-base.en', revision='3d3d5dee26484f91867d81cb899cfcf72b96be6c', local_dir=str(Path.home() / '.friday' / 'models' / 'faster-whisper-base.en'))"
```
The app never downloads weights itself. Without these two steps, Whisper just isn't offered as an engine.

Don't use `uvicorn --reload` for a server with no console: on Windows it stops its worker with `CTRL_C_EVENT`, which only reaches processes sharing a console, and then waits with no timeout, so it hangs on the first file change. In a normal terminal window it's fine.

## Tests

```bash
.venv/Scripts/python -m pytest -q --ignore=tests/integration/test_ollama_live.py --ignore=tests/integration/test_real_windows_location.py
```
```bash
npm --prefix apps/desktop test
```
```bash
npm --prefix apps/desktop run build
```

## Configuration (optional; copy `.env.example` to `.env` in the repository root)

The backend loads `.env` on startup. Variables already set in the environment win, and values are never logged.

| Variable | Effect |
|---|---|
| `FIRMS_MAP_KEY` | Enables the active-fires layer (free NASA key) |
| `OSM_CONTACT_EMAIL` | Identifies you to Nominatim, as its usage policy asks |
| `LOCATION_PROVIDER` | `osm` (default), `google`, or `none` |
| `FRIDAY_STT_PROVIDER` | Backend default engine: `windows_sapi` (default) or `faster_whisper`. The choice in Settings → Voice overrides it for that browser |
| `FRIDAY_WHISPER_MODEL` | Whisper model folder (default `~/.friday/models/faster-whisper-base.en`) |
| `FRIDAY_STT_LANGUAGE` | SAPI recognizer culture (default `en-US`; `en-GB` is also installed) |
| `FRIDAY_MODEL_TIMEOUT` | Seconds allowed per model call (default 300; a long reply measured about 110–130 s on this CPU) |
| `FRIDAY_MEMORY_DB` | Memory store path (default `~/.friday/memory.sqlite3`) |

## How to compare engines on your own voice (pending)

Use Chrome or Edge at http://localhost:5173/#settings; the built-in browser pane blocks the microphone.

1. Open Settings → Voice and pick your microphone.
2. In **Voice lab**, select phrase 1, press Record, say it, press Stop.
3. Press Listen. If the audio is quiet, distorted, or silent, fix the input level first (the lab warns below −30 dBFS peak or on clipping).
4. Press **Transcribe with 2 engines**. Both engines get the same recording, and their scores appear side by side. Repeat for all five phrases, then try again with browser noise processing off.
5. Under **Your results so far**, press **Use this engine** on the one you prefer. Push-to-talk uses it from then on.
6. Press "Copy results (no audio)" to share the JSON; it has per-engine WER, confidence, and timings, never audio.

Recordings and scores stay in this window's memory when you move between screens. Press **Clear recordings**, reload, or close the window to remove them.

## Known limitations

- Whisper is unmeasured on a real microphone, and SAPI has only 2 of 5 phrases measured (D18). Whisper reports no confidence score, so the lab shows "not reported".
- No user authentication on the local API: loopback bind, Host check, and CORS only.
- Audit log and approvals are in memory: lost on restart, and pending approvals expire after 5 minutes.
- No durable task store; a backend restart drops in-flight requests (reported as failures, never retried).
- The model runs on the CPU here: Ollama's log shows `total_vram="0 B"` and drops the Intel UHD 770, so it never sees the RTX 4050. Plain replies take about 10–55 s; an Ask the Earth question takes 6–7 minutes, mostly reading the 13 tool definitions (about 1,900 prompt tokens at about 28 tokens/s) twice and writing the answer. Check the NVIDIA driver and the laptop's graphics mode (MUX or Optimus) before tuning anything else.
- qwen2.5:7b lists every record in its answer even when told not to, and sometimes prints raw UTC timestamps. An instruction to keep it short was tried and made no difference, so it was removed. It also invented a record twice in live runs, so `unmatched_record_mentions` in `backend/friday/earth/actions.py` checks every "M x.x - place" in the answer against the records the tools returned and sends any misses in `unmatched_mentions`; the app warns above the answer. It covers earthquakes only.
- The Vite dev server can restart without its `/api` proxy if many files change at once (a branch switch, say). Pulse then shows `Unexpected token '<'`. Restart the desktop dev server.
- Dark theme only. The light-theme tokens exist as names, but no light palette was shipped.
- Earth's keyless map is flat Esri satellite imagery. Photorealistic 3D needs a Cesium ion or Google key, and ships, active fires, and live traffic need their own keys.
- Approve-path media keys were verified with a fake tool, not by pressing a real key.

## Naming

W.E.D.N.E.S.D.A.Y. is the product name everywhere a person can see it. These stay as they were, on purpose, because renaming them would break imports, stored preferences, or existing configuration: the `backend.friday` package, `FRIDAY_*` environment variables, `~/.friday/` and `~/FridayWorkspace`, `friday.*` browser storage keys, the Python project name, and the repository folder. The Earth app's folder is still `apps/gods-eye-view`.

## Earth screen

The Earth screen is a locally changed copy of the MIT-licensed app at github.com/bilawalsidhu/gods-eye-view (commit a725178). Its upstream `LICENSE` must stay in the folder. `npm --prefix apps/desktop run dev` starts it (`earthServer` in `apps/desktop/vite.config.ts`), and stopping that server stops it. A `vite preview` or static build does not start it.

- It's cloned at `apps/gods-eye-view` with its own git history, excluded by the root `.gitignore`. On a fresh machine, clone it there, install with `PUPPETEER_SKIP_DOWNLOAD=1 npm ci`, and apply `patches/wednesday-earth.patch`, which holds every local change. After a `git pull` there, reapply it and run its `npm test`.
- It runs on `localhost:4173` in a frame. `GEV_EMBED_FRAME_ANCESTORS` limits framing to the desktop app's address. Pages without `?embed=1` keep `X-Frame-Options: DENY`.
- Local code: `src/app/wednesdayEarth.js` (whole-planet opening, orbit dial, device marker, orbital flight, focus mode, quiet state, remembered layers, shell messages) and `src/ui/styles/wednesday.css` (theme and layout).
- It always opens at GLOBAL, lit by the real sun, with DETECT callouts off because they bury the planet from that distance. LOCAL and STREET turn them on when the camera arrives; Display → DETECT toggles them any time. Layers on at last visit are restored; a first visit enables satellites, flights, and earthquakes.
- While untouched at GLOBAL, it turns one revolution in six minutes after 8 seconds and fades its controls after 6. Any input stops both. The turn holds the render governor open, so it renders continuously while spinning; it stops when another screen is open (the shell sends `wednesday:visibility`) and when reduced motion is set.
- Selecting something (`gev:entity-selected`, `gev:awareness-subject-selected`) sets `body[data-earth-focus]` and shows the lens. Earthquakes had no selection, so their overlay labels are now interactive and the click handler reads the USGS record from the entity.
- Its map and data requests go directly to their providers, so the local-first guarantee doesn't cover this screen. Keys are optional and go in POWER UP or that folder's `.env`. Space Missions and Radio are exclusive modes that block other layers.

## Location

- Modes (Settings → Location): **Off** reads nothing and clears the stored position. **Once**, the default, reads once when Earth opens or on request. **Continuous** runs a worker.
- The worker is passed the backend's process ID and exits within about 5 seconds of the backend ending, and a normal shutdown stops it directly, so it can't run with nothing on screen showing it. The preference persists, and it resumes when the backend starts, unless paused.
- Polling slows to at most 3× the interval while the device moves under 50 m, capped so the fix never goes stale.
- Only the latest fix is stored (`~/.friday/location_state.json`); there is no history. Coordinates reach the Earth frame by `postMessage` to its origin only, never in a URL.
- All user-facing location wording comes from `describeLocation` in `apps/desktop/src/services/earthLocation.ts`.

## Visual identity ("Orbit")

- The planet fills the window on Earth. The navigation rail and status bar float over it (`App.css`), and the rail dims when Earth is quiet. The location indicator never dims, because tracking must stay visible.
- The assistant core is `components/ui/Presence.tsx`: one W line with a different behaviour per state, CSS only. States come from real state in `AppProvider`: `retrieving` while a `get_*` tool runs (from `GET /chat/progress/{id}`), `executing` while any other tool or an approved action runs, and `awaiting` while an approval is pending with no request in flight.
- Screens open out of the planet with a circular reveal (`view-from-planet`), and Earth arrives with a slight scale.

## 3D models

Only the selected object gets a model, which keeps the draw count bounded. Thousands of fleet models are not drawn at global scale.

- `public/models/satellite.glb` and `ship.glb` are original, generated by `apps/gods-eye-view/scripts/generate-models.mjs`, about 10 to 13 KB each. Re-run that script after changing a shape; a test fails if the files drift.
- The ISS (NORAD 25544) gets `public/models/station.glb` instead: a simplified original layout of the station (truss, eight wings, modules, radiators, Russian segment), about 57 KB, facing its direction of travel computed from the orbit a second ahead (`travelOrientation` in `src/layers/trackedModels.js`).
- Selected satellites use the model unless the catalogue name marks a rocket body or debris (`looksLikeSpacecraft` in `src/layers/trackedModels.js`), which keep a plain marker.
- Selected ships use the model, facing the AIS heading, then course; with neither, the model faces north because the direction is unknown. This path needs an AISStream key to run on real data.
- The selected aircraft's minimum on-screen size was raised from 40 to 96 px in `src/layers/flights/policy.js`. Military flights keep their own constant at 40.

## Ask the Earth, Time, Orbit, Pulse

One contract carries every change the assistant or a panel asks Earth to make. It is defined three times and each copy refuses anything outside it: `backend/friday/earth/actions.py` (pydantic, `extra="forbid"`), `apps/desktop/src/services/earthActions.ts`, and `readEarthAction` in the frame's `src/app/wednesdayEarth.js`.

- Actions: `set_preset`, `focus`, `focus_user`, `return_global`, `set_layer`, `show_records` (groups `ask`, `time`, `compare`, `investigate`, `pulse`; at most 500 records), `select_record`, `select_aircraft` and `select_satellite` (a name matching `^[A-Za-z0-9 ()/.\-]+$`), and `clear_selection`. Record links must be https.
- The model reaches Earth in two ways, both through `ConversationOrchestrator` and the existing `ToolRegistry`: the `control_earth` tool (permission `earth:view`), and records from world tools, which `actions_for_tool_result` maps to actions. At most 12 actions per turn are sent, in `ConversationResponse.earth_actions`. `control_earth` never reports success; its verification says Earth will confirm.
- The app queues each reply's actions as a batch and sends it to the frame once Earth is ready (`wednesday:actions`). The frame runs them in order and answers `wednesday:action-results` with an ok or error for each one; the answer panel shows those results, not the model's claim.
- **What happened here?** The frame's dial button starts pick mode (Escape cancels). A click draws a 250 km ring and sends `wednesday:investigate`; the app calls `GET /world/investigate`, which keeps only records whose own coordinates are inside the circle and lists every provider that couldn't be reached. The place name is only looked up when nearby-place search is allowed.
- **Time.** `GET /world/history` reads USGS FDSN and NASA EONET for up to 92 days, never the future or before 1900. A failed archive goes in `missing`, never in the records as an empty result. Leaving Time mode removes its records from the globe.
- **Orbit** turns on the satellite and flight layers, follows the ISS by name, and finds aircraft around your last known position, if there is one.
- **Pulse** (`GET /world/briefing`) lists USGS M4.5+, GDACS and EONET records with source and time. `POST /world/briefing/summary` asks the local model for a summary, with the records wrapped as data, and the panel labels it as the model's reading.
- Tests: `tests/unit/test_earth_actions.py`, `apps/desktop/test/earthActions.test.mjs`, and the frame's `wednesdayEarth.test.mjs` and `wednesdayRecords.test.mjs`.

## Render quality

`src/app/renderQuality.js`, installed next to the render governor in `src/app/tools.js`.

- Cesium's default draws at CSS pixels and ignores `devicePixelRatio`, so on a high-DPI or 4K screen the globe was drawn at a fraction of the screen's resolution and stretched. It now draws at the device's own pixels, capped at a 3840×2160 frame, and asks for finer map tiles to match (`maximumScreenSpaceError` from 2 down to 1). Up to 1,000 globe tiles stay cached, not 100, so going back to a place doesn't refetch it.
- A frame-time monitor averages 45 continuous frames. Above 22 ms it first swaps 4× MSAA for FXAA (MSAA cost about 12 ms a frame on the Intel GPU), then lowers resolution in 0.15 steps down to CSS pixels. Below 14 ms it restores resolution, then MSAA; if restoring MSAA makes frames slow again, MSAA stays off for the session. On-demand (idle) rendering is never measured.
- Measured at 1280×800 with flights and satellites on: 29.9 ms median per frame before, 19.7 ms after, on the Intel UHD 770.
- **The browser renders on the Intel UHD 770, not the RTX 4050** (`UNMASKED_RENDERER_WEBGL`). Full resolution needs the RTX: Windows Settings → System → Display → Graphics, set the browser (or the desktop app's runtime) to High performance. The same setting, or the NVIDIA driver, is why Ollama sees no GPU.
