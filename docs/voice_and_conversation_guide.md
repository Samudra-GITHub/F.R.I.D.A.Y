# W.E.D.N.E.S.D.A.Y. Voice & Conversational Intelligence Guide (Phase 4 & Phase 5)

This guide documents the local conversational intelligence layer and privacy-first voice interaction subsystem in W.E.D.N.E.S.D.A.Y.

---

## 1. Unified Architecture

Phase 4 (Conversational Intelligence & Safe Tool Orchestration) and Phase 5 (Local Voice Interaction) share a single unified execution pipeline:

```
[ User Input ]
  ├─> Text Composer (Keyboard)
  └─> Push-to-Talk (Microphone) -> Local STT (Windows.Speech / Faster-Whisper)
           │
           v
  [ Transcript Preview & Edit ]
           │
           v
  [ FastAPI Conversation Router: POST /api/chat ]
           │
           v
  [ Conversation Orchestrator ]
    ├─> Multi-turn Session Memory (LRU bounded)
    ├─> Local Ollama LLM (qwen2.5:7b)
    ├─> Capability Broker (Policy Enforcement: WORLD_READ, PLACES_SEARCH, etc.)
    ├─> Fixed Tool Registry (get_local_time, list_workspace, world_tools, etc.)
    ├─> Untrusted Data Wrapper (Mitigates Prompt Injection)
    └─> Source Citation Extractor (USGS, Open-Meteo, NASA EONET, GDACS, OSM)
           │
           v
  [ Grounded Assistant Response ]
           │
           ├─> Desktop UI: User & Assistant Bubbles + Verifiable Citation Links
           └─> Local TTS (Windows.Speech.Synthesis): Offline Spoken Answer
```

---

## 2. Speech Providers and Setup

### A. Speech-to-Text (STT)

1. **Default Provider**: `windows_sapi` (`Windows.Speech.Recognition`)
   - **Environment**: Built into Windows 11 out of the box. Zero download or installation required.
   - **Privacy**: Runs 100% offline via local desktop speech recognizers.
   - **Format**: Standard PCM 16-bit 16kHz mono WAV audio.
   - **Audio Bounds**: Duration capped at 30 seconds; payload size capped at 10 MB.

2. **Optional Modular Alternative**: `faster-whisper`
   - Can be configured via environment: `FRIDAY_STT_PROVIDER=faster_whisper`.
   - Requires manual model download: `whisper-base.en` or `whisper-small.en`.
   - Uses local NVIDIA GPU acceleration (CUDA) or CPU int8 quant.

### B. Text-to-Speech (TTS)

1. **Default Provider**: `windows_sapi` (`System.Speech.Synthesis`)
   - **Environment**: Native Windows 11 Speech Synthesizer.
   - **Voices**: Installed Windows desktop voices (e.g., `Microsoft David Desktop`, `Microsoft Hazel Desktop`, `Microsoft Zira Desktop`).
   - **Format**: Produces uncompressed PCM 16-bit WAV bytes.
   - **Bounds**: Input text bounded to 2,000 characters; execution timeout 12 seconds.

2. **Optional Modular Alternative**: `piper`
   - Offline neural TTS with fast inference on CPU.

---

## 3. Privacy Controls & Push-to-Talk Lifecycle

1. **Off by Default**: Microphone capture is strictly dormant on application startup.
2. **Explicit Activation Only**:
   - Audio capture begins only when the user holds or clicks the Push-to-Talk button.
   - Releasing or clicking finishes recording and immediately closes all media tracks (`stream.getTracks().forEach(t => t.stop())`).
3. **Transcript Preview & User Approval**:
   - Local STT produces a transcript preview card in the UI.
   - The user can review, edit, discard, or approve the text before dispatching to the conversation API.
4. **Barge-In / Instant Interruption**:
   - The user can interrupt spoken answers at any instant using the "Stop Speaking" button or by triggering a new Push-to-Talk turn.
   - Audio playback halts immediately and frees system resources.
5. **No Cloud Fallback**:
   - If an offline speech engine or the local Ollama instance is unreachable, an informative local error is returned. Audio is never routed to cloud providers.

---

## 4. Hardware Resource & GPU Considerations

- **Primary Reasoning Model**: `qwen2.5:7b` requires ~5 GB VRAM in Ollama (Q4_K_M).
- **GPU Sharing**: On machines with 6 GB VRAM (e.g. NVIDIA RTX 4050 Laptop GPU), Windows Speech (SAPI) runs entirely on the host CPU, avoiding VRAM contention with Ollama.
- **Memory Footprint**: Multi-session context history is bounded with an LRU cache (default 50 active sessions, 12 turns max per session).

---

## 5. Running Automated Tests

All automated tests are completely deterministic and mocked — no physical microphone, audio speakers, or running Ollama instance are required.

### Backend Tests
```bash
# Run all Phase 4 & Phase 5 unit and integration tests
.\.venv\Scripts\pytest.exe -q tests/unit/test_conversation_orchestrator.py tests/unit/test_voice_service.py tests/integration/test_conversation_and_voice_api.py

# Run complete backend test suite (147 tests)
.\.venv\Scripts\pytest.exe -q
```

### Frontend Tests
```bash
# Run all desktop tests (37 tests)
cd apps/desktop
npm test

# Verify production build
npm run build
```
