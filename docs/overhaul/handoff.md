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
- The model runs on the CPU here (no discrete GPU reported), so replies take about 10–55 s.
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
- The assistant core is `components/ui/Presence.tsx`: one W line with a different behaviour per state, CSS only. `executing` shows while an approved action runs, from the approval's own status. The backend doesn't stream, so a tool the model calls without needing approval shows as `thinking`.
- Screens open out of the planet with a circular reveal (`view-from-planet`), and Earth arrives with a slight scale.

## 3D models

Only the selected object gets a model, which keeps the draw count bounded. Thousands of fleet models are not drawn at global scale.

- `public/models/satellite.glb` and `ship.glb` are original, generated by `apps/gods-eye-view/scripts/generate-models.mjs`, about 10 to 13 KB each. Re-run that script after changing a shape; a test fails if the files drift.
- Selected satellites use the model unless the catalogue name marks a rocket body or debris (`looksLikeSpacecraft` in `src/layers/trackedModels.js`), which keep a plain marker.
- Selected ships use the model, facing the AIS heading, then course; with neither, the model faces north because the direction is unknown. This path needs an AISStream key to run on real data.
- The selected aircraft's minimum on-screen size was raised from 40 to 96 px in `src/layers/flights/policy.js`. Military flights keep their own constant at 40.
