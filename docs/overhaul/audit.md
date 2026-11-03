# Audit

Scope: both reference PDFs, the whole repository, and live behaviour on this machine (29 Oct 2026).
The PDFs are treated as recommendations, not authority.

## Environment (observed)

| Item | Value |
|---|---|
| OS / shell | Windows 11 Home (10.0.26300), Git Bash + PowerShell 5.1 |
| Repository | `C:\Users\samud\OneDrive\Desktop\My_Projects\Friday`, branch `main` |
| Python | 3.12.10 in `.venv` (pyproject allows ≥3.11) |
| Node / npm | v24.19.0 / 11.17.0; `apps/desktop/package-lock.json` present; no Python lockfile |
| Hardware | Intel i5-13450HX, 23.7 GB RAM; only Intel UHD Graphics reported, so models run on the CPU |
| Ollama | Reachable; models installed: `qwen2.5:7b` (configured), `qwen2.5:1.5b`, `phi4-mini`, `qwen2.5-coder:7b` |
| Speech | SAPI recognizers en-US, en-GB; voices David, Hazel, Zira |
| Repo instructions | No `CLAUDE.md` |
| Config env vars | `.env` absent; `LOCATION_PROVIDER`, `GOOGLE_MAPS_API_KEY`, `FIRMS_MAP_KEY`, and `OSM_CONTACT_EMAIL` unset (names only, never values) |

Pre-existing user work at the start: 10 modified tracked files and a large untracked tree (`apps/`,
location/world/voice packages, tests). It was all edited in place; nothing was reset, stashed, or
regenerated.

## PDF comparison

Both PDFs were read in full, including the appendix broker (Research pp. 28–31). Text was
extracted with a local script, because the PDF renderer was unavailable.

| Topic | Blueprint v1 (27 Oct) | Research v2.0 (29 Oct) | Applies here? |
|---|---|---|---|
| Shape | Modular monolith; FastAPI, Pydantic, React/Vite (p.5) | Same, plus strict fields and a lockfile (p.6) | Yes; already matches |
| Authority | "Broad capability, narrow authority" (p.4); broker decides (p.6) | Approval bound to user, task, tool, canonical arguments, expiry (p.12) | **Implemented**: argument-bound, single-use approvals |
| Task state | Action IDs; no blind retry after timeout (p.8) | CREATED…OUTCOME_UNKNOWN state machine, reconciliation (pp.10–11) | Partially: approvals record `outcome_unknown`; no durable task store |
| Voice | Push-to-talk first; faster-whisper candidate (p.5, p.9) | Measure each latency stage; test on the real mic (p.14) | Yes; SAPI kept as default, Whisper added after approval |
| Memory | SQLite + FTS5 with provenance (p.12) | Tombstones; no invented confidence (pp.17–18) | **Implemented** (stdlib SQLite/FTS5) |
| Security | Stop control independent of the model (p.16) | Origin checks, authenticated IPC, trust zones (pp.22–23) | Host check, CORS, and Esc stop done; no session authentication |
| Platform | Linux/Hyprland, playerctl (p.17) | PipeWire, portal, and `hyprctl` diagnostics (p.16) | **No**: this is a Windows app; SAPI, WinRT, and Win32 media keys are kept |

The appendix broker is illustrative only: its own text notes a TOCTOU race and no auth (p.28). Its
expiring-grant and audit ideas were adopted; its code was not copied.

Gaps neither document covers: Windows SAPI behaviour; frontend/backend contract drift; browser
audio capture details; geospatial data licensing.

## Architecture (actual)

```
apps/desktop (React 18 + Vite 5, :5173, /api proxy → 127.0.0.1:8000)
  main.tsx → VoiceProvider → AppProvider → App (rail nav, hash routes)
  Assistant  → /chat, /chat/cancel, /chat/reset, /approvals/{id}/decision, /voice/*
  Earth      → /world/* (USGS, EONET, GDACS, RSS, Open-Meteo, satellites, flights, launches, fires),
               /location/{status,enable,…,search,geocode,nearby}   (lazy-loaded globe.gl chunk)
  Activity   → /audit         Memory → /memories        Access → /capabilities, /policy/consent
  Settings   → /voice/config, /health                    Diagnostics → /diagnostics
backend/friday (FastAPI, TrustedHost + CORS allow-list, bound to 127.0.0.1)
  ConversationOrchestrator ─ OllamaAdapter
        │ proposes                       ┌─ approvals (pending→executing→succeeded|failed|outcome_unknown)
  CapabilityBroker ─ ToolRegistry (11) ──┤  audit ring buffer (argument digests only)
  VoiceService (bounded) ─ WindowsSpeechProvider ─ powershell.exe -EncodedCommand → System.Speech
  MemoryStore (SQLite + FTS5)   WorldIntelligenceService + Satellite/Flight/Launch/Fire providers
```

Trust boundaries: the model only proposes; consents and approvals are reachable only through UI
endpoints; tool output is labelled as untrusted data; memories enter context as reference data
that grants nothing.

## Defect ledger

Status key: **V** = verified (reproduced or read in code), with a regression test where noted.

| ID | Sev | Workflow | Observed → expected | Root cause | Fix (files) | Regression evidence | Status |
|---|---|---|---|---|---|---|---|
| D1 | High | Voice | Long phrases truncated after the first pause → full text | SAPI `Recognize()` called once | Loop until the stream ends (`voice/windows_speech.py`) | Synthetic run: 8 → 21 of 21 words | V, fixed |
| D2 | High | Voice | Server froze during recognition → stays responsive | Blocking subprocess inside `async def` | Sync routes (threadpool), bounded engine slots (`voice_router.py`, `voice/service.py`) | Voice tests | V, fixed |
| D3 | Med | Voice | Transcript rewritten "A Friday" → "Hey Friday" | Regex post-processing | Removed; raw transcript | WER test | V, fixed |
| D4 | Med | Voice | Confidence shown as "Match %" | Mislabelled metric | WER and confidence shown separately (`VoiceLab.tsx`) | `audio_utils.test` | V, fixed |
| D5 | Med | Voice | `audioop` removed in Python 3.13; failures were silent | Deprecated stdlib module | `voice/audio_dsp.py` | `test_overhaul_backend` | V, fixed |
| D6 | Low | Settings | Language packs shown as literal `$($_.Culture.Name)…` | PowerShell single quotes don't expand variables | String concatenation (`windows_speech.py`) | Probe now lists en-US and en-GB | V, fixed |
| D7 | High | All UI | Fabricated activity, memories, offline "success" replies, fixture events | Hard-coded fixtures | Real endpoints; fixtures removed | View tests | V, fixed |
| D8 | High | Earth | EONET events never placed; GDACS/weather fields missing | Frontend types didn't match `contracts.py` | Types mirror the backend (`types/intelligence.ts`) | `earth.test` | V, fixed |
| D9 | Med | Earth | 422 on feed requests | Limits above backend bounds | Limits corrected | Browser network log | V, fixed |
| D10 | High | Security | DNS rebinding possible | No Host check | `TrustedHostMiddleware` | `test_api_rejects_foreign_host…` | V, fixed |
| D11 | Med | Tools | `true` accepted as integer; min/max ignored | `bool` is an `int` subclass | Strict checks (`policy/broker.py`) | `test_broker_rejects_bool…` | V, fixed |
| D12 | Med | Tools | Identical calls in a turn ran twice | No dedup | Per-turn digest dedup (`orchestrator.py`) | `test_duplicate_calls…` | V, fixed |
| D13 | Med | Chat | No cancel; reset could show a late "cancelled" reply in the new chat | No request ID or generation guard | `/chat/cancel` and a generation guard (`AppProvider.tsx`) | Browser Journey A | V, fixed |
| D14 | Med | Access | Media toggle showed "granted" while the backend denied | UI-only state | `/policy/consent` | Browser | V, fixed |
| D15 | Low | Location | Tracking interval ignored | Frontend sent `interval_seconds`, backend expects `interval_s` | `worldApi.locationAction` | Code review | V, fixed |
| D16 | Med | Earth | Aircraft never loaded after a programmatic fly-to | OrbitControls doesn't emit `change` during tweens | View published after each transition (`EarthGlobe.tsx`) | Browser | V, fixed |
| D17 | Med | Perf | ~60 re-renders/s while idle | Orb energy kept in React state each frame | CSS-only presence mark | Code review | V, fixed |
| D19 | High | Chat | Long replies failed at 60 s → complete | Timeout shorter than real CPU inference (measured 110.6 s and 129 s) | 300 s default, `FRIDAY_MODEL_TIMEOUT` (`config.py`) | Live: 129 s reply completed | V, fixed |
| D20 | High | Chat | A slow model was reported as "Ollama unavailable" | `httpx.TimeoutException` caught as `RequestError` | Separate timeout path (`ollama_adapter.py`) | `test_model_timeout_is_a_timeout…` | V, fixed |
| D21 | High | Chat | Stop left the model generating, so the next message queued behind it | Cancellation only checked between steps | Model call runs as a cancellable task (`orchestrator.py`) | Live: returned in 0.1 s; next question 14.0 s vs 15.2 s baseline | V, fixed |
| D22 | Med | Config | `.env` was never read, though `.env.example` said to use it | No loader | `load_dotenv` (stdlib), real environment wins, placeholders ignored (`config.py`) | `test_dotenv_loads…` | V, fixed |
| D23 | Med | Dev | Backend stopped picking up edits and needed a manual kill | uvicorn reloader's `CTRL_C_EVENT` can't reach a console-less worker, and it joins with no timeout | `scripts/dev_backend.py`; `launch.json` | Live: restart in 3.6 s; hang reproduced on throwaway ports | V, fixed |
| D24 | Med | Chat | Model stated a wrong weekday ("Thursday, 31 October") | Model computed it, copying a prompt example added during this work | Time tool supplies the readable date (`time_tool.py`) | Live: "Saturday, 31 October 2026", matches the clock | V, fixed |
| D25 | Med | Voice | Voice lab results lost on leaving Settings | State lived in the component | Store outside the component, plus Clear recordings (`VoiceLab.tsx`) | Browser check | V, fixed |
| D26 | Low | Voice | Unknown `FRIDAY_STT_PROVIDER` silently became Windows Speech | No validation | Logged and shown in Diagnostics | Code review | V, fixed |
| D27 | Low | Chat | Backend down showed "500: Internal Server Error" | Proxy response shown as-is | Clear message (`voiceApi.ts`) | Code review; not re-run with the backend down | V, fixed |
| D18 | — | Voice | SAPI accuracy collapses with noise ("C5 1/4 time is if" at −30 dB) | Engine limitation, not a pipeline bug | Voice lab compares engines on one recording; Whisper added as an optional engine | SAPI 117%/120% WER on real mic (2 phrases); Whisper synthetic only | **Pending real-mic comparison** |
