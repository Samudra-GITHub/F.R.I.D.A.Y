# Verification

All commands were run from the repository root on 29 Oct 2026 unless noted. Latest test and build results: 31 Oct 2026.

## Automated

| Check | Command | Result |
|---|---|---|
| Backend tests (baseline) | `.venv/Scripts/python -m pytest -q --ignore=tests/integration/test_ollama_live.py --ignore=tests/integration/test_real_windows_location.py` | 145 passed |
| Backend tests (now) | same | **190 passed** (includes `test_whisper_provider.py` and `test_reliability_fixes.py`, which use fakes) |
| Frontend tests (baseline → now) | `npm --prefix apps/desktop test` | 46 passed → **45 passed** (fixture-only suites replaced by earth, WER, markdown, mic-error, engine-comparison, and view tests) |
| Type check | `npx tsc --noEmit -p apps/desktop` | clean |
| Production build | `npm --prefix apps/desktop run build` | passes; JS 248.5 kB (78.4 kB gzip). The Earth screen is being replaced in a separate session, so the earlier 2,049.7 kB globe chunk no longer appears in this build |
| Lint | — | no lint configuration in the repository; not run |

Excluded on purpose: `test_ollama_live.py` (calls the live model) and `test_real_windows_location.py` (reads the real device location).

## Running-app journeys (Claude's in-app browser against the real backend and Ollama)

| Journey | Steps exercised | Result |
|---|---|---|
| A: Conversation | "What time is it?" → reply with a `get_local_time` tool call and a source; long prompt → Stop at 2.5 s → "Stopped…" → reset → 0 messages; no late reply appeared | **Verified** |
| B: Voice diagnostic | Recording, playback, and transcription UI exercised; recognition checked with synthetic SAPI speech (see below) | **Pending real microphone**: Claude cannot speak into your microphone |
| C: Earth | Globe with NASA imagery, borders, and all feeds live; event select → camera flies there; "Kyoto" search → weather and 3-day forecast; ISS orbit track; aircraft near Heathrow; precipitation; daily imagery; sensor styles; layer toggles | **Verified** |
| D: Permission | "Pause the music." → broker denies → approval card with `action: "pause"` → Deny → status denied; audit shows decision/denied, approval/requested, approval/denied with the same digest | **Verified** (Approve was not clicked live, to avoid pressing a real media key; covered by unit tests with a fake tool) |
| E: Failure recovery | Backend stopped → "Backend unreachable" and Retry; no fabricated reply → backend restarted → Retry → real answer in 10.7 s | **Verified** |
| Responsive | All 7 screens at 1024, 768, and 390 px: no horizontal overflow (measured with `scrollWidth`) | **Verified** |

## Earth screen as God's Eye View (31 Oct 2026, live data)

Started from `npm --prefix apps/desktop run dev` alone. Full interface shown in the frame; screen switching keeps the same frame. Framing headers: `?embed=1` allows only `localhost:5173` and `127.0.0.1:5173`; other documents send `DENY`. Listens on loopback (`[::1]:4173`). Upstream `embed.test.mjs`: 10 passed, with the patch applied.

Seen with no keys: 5,100 aircraft near London, 49 military aircraft, 828 satellites (about 10,600 more Starlink with DENSE), 41 earthquakes, 4,000 cameras, 2,600 cables, 4,400 data centers, 716 dams, 105 fire perimeters, 141 installations, 21 launches, 750 radio stations. Weather, transit, bike share, GNSS, air quality, and ALPR layers enabled without errors; their content was not inspected.

Not working without keys: vessels and active fires ("unavailable"); street traffic is simulated. Not tested: cockpit view, directions, street level, recent imagery, local ADS-B, voice, POWER UP key entry in the frame. Console showed 502 and 429 responses from some upstream feeds; the sources were not traced.

## Earth restyle and opening location (31 Oct 2026)

Seen in the running app: W.E.D.N.E.S.D.A.Y. name and logo on the loading screen and title, Obsidian Signal colours and system fonts, layer filter ("fire" narrowed the list to two rows), Display panel and Visual presets tray open, live counts still arriving (828 satellites, about 5.2K flights). With a real Windows reading (±83 m), Earth flew to that position with a marker at screen centre, and the reported camera position was within 0.2° of it, the offset expected from a tilted camera.

Tests: desktop 47 passed; desktop build passes; Earth suite 9,094 of 9,109 passed, 4 failed (11 skipped). Three of the 4 are time-limited tests that pass when run alone, so they failed under full-suite load on this machine. The fourth, the sky asset test, can't find an image that does exist, because of how it builds a Windows path. Not tested after the restyle: cockpit view, Cyber layout, phone layout, voice, directions, street level, recent imagery, local ADS-B, POWER UP. The failure message when Windows location is off was not triggered.

## W.E.D.N.E.S.D.A.Y. rebuild (31 Oct 2026)

Seen in the running app at 1280x800: opens on the whole planet with day and night lighting, slow turn while idle, dial needle following altitude (GLOBAL, CONTINENT, LOCAL), device marker, Focus on me, Reset, Return to global. Earthquake selection showed the USGS magnitude, place, depth, and age; aircraft selection showed a real callsign, altitude, speed, and trail. Location modes against real Windows readings: Once, Continuous (worker started, status reached "Tracking"), Pause, Stop (worker gone, stored position cleared, no marker). Assistant core: all seven states rendered side by side by setting the state directly.

Tests: backend 205 passed; desktop 40 passed, type check and build clean; Earth 9,105 of 9,118 passed, 11 skipped, 2 failed. The ranking budget test passes alone. The sky asset test fails alone too, because of how it builds a Windows path.

Not tested: real microphone with either engine, core states from a real voice or approval flow, permission denied in Windows (unit tests only), network failure, WebGL failure, frame rate on the RTX 4050 (the pane doesn't represent it), cockpit, Cyber layout. The phone layout is unfinished: the voice card covers the dial stops.

## Voice evidence (synthetic only)

SAPI TTS output fed through the real backend recognizer:

| Phrase | Before | After |
|---|---|---|
| Long sentence (21 words) | first clause only (8 words) | 20–21 / 21 words |
| "Hey Friday, what time is it?" | regex turned "A Friday" into "Hey Friday" | raw "A Friday what time is it" (WER 1/6) |
| Same with −30 dB noise | "C5 1/4 time is if" | unchanged: an engine limit |

## Real-microphone results (2 of 5 phrases, reported from the Voice lab)

Microphone Array (Realtek), browser echo, noise, and gain processing on, en-US recognizer.

| Expected | Heard | WER | Engine confidence | Peak / RMS (dBFS) | Clipped | Recognition |
|---|---|---|---|---|---|---|
| Hey Friday, what time is it? | it has regulatory news of the head | 117% (6 wrong, 1 extra) | 8% | −6.4 / −26.0 | 0.00% | 1805 ms |
| What's the weather like today? | but when starr leather light duty | 120% (5 wrong, 1 extra) | 14% | −3.2 / −23.0 | 0.00% | 1435 ms |

Levels are healthy, and the second result is phonetically close (weather→leather, like→light, today→duty), which points to the recognizer rather than capture. Playback quality has not been confirmed by the user, so this is not yet a proven root cause.

## Engine comparison (SYNTHETIC speech, not your voice)

SAPI text-to-speech through the real providers, with Python sockets blocked for Whisper, over the five test phrases (38 reference words) on 31 Oct 2026. This shows the engines behaving differently under noise; it does **not** predict accuracy on a real microphone, and the speech is a Windows voice that SAPI should favour.

| Condition | SAPI WER | Whisper base.en WER | SAPI mean time | Whisper mean time |
|---|---|---|---|---|
| Clean | 15.8% | 0.0% | 1179 ms | 539 ms |
| Noise −36 dB | 81.6% | 0.0% | 1420 ms | 482 ms |
| Noise −30 dB | 94.7% | 7.9% | 1409 ms | 507 ms |
| Noise −24 dB | 100.0% | 2.6% | 999 ms | 494 ms |

Voice lab UI check: synthesized speech replaced `getUserMedia` in the page (test stub in that page session only, not in the code) because the pane blocks the microphone. Record → Stop → Transcribe with 2 engines → side-by-side results → Use this engine → push-to-talk request carried `engine: "faster_whisper"`, with the correct transcript. API check: unknown engine → `model_not_installed` with no substitution.

## Reliability checks (live, real backend and Ollama, 31 Oct 2026)

| Check | Result |
|---|---|
| Long reply, direct to Ollama (`num_predict` 700) | 110.6 s, above the old 60 s limit |
| Same prompt through the app | ok in 129.0 s, 3074 characters |
| Stop during generation | returned 0.1–0.2 s after Stop |
| Next question right after Stop (quiet machine) | 14.0 s, vs 15.2 s warm baseline: nothing queued |
| Backend file touched, dev runner | down after 1.5 s, serving again at 3.6 s |
| "What time is it?" | "10:58 AM on Saturday, 31 October 2026"; system clock agreed |
| Recorder via `AudioWorklet` (synthetic speech stub) | "Open my settings" 0% WER on both engines, with the CPU also loaded |

The `AudioWorklet` move is a precaution: `ScriptProcessor` is deprecated and runs on the page's main thread, but dropped audio was **not** demonstrated. An early 33% result was caused by the test stub starting its audio before capture was ready. The level meter could not be re-checked in the pane, which rendered 0 animation frames at the time.

**Not run:** Whisper on a real microphone, the other 3 real-microphone phrases on SAPI, processing-off comparison, screen-reader passes, Windows display-scaling tests, measured frame rates.
