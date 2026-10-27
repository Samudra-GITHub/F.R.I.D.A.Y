# F.R.I.D.A.Y. — Personal AI Desktop Assistant

F.R.I.D.A.Y. is a conversational, multimodal AI desktop assistant designed with **bounded autonomy, verifiable actions, and strict security isolation**. Inspired by the F.R.I.D.A.Y. engineering blueprint, the architecture separates reasoning from execution authority: the language model proposes intents, but an application-level **Capability Broker** independently authorizes all actions.

---

## Milestone 1: Core Foundation & Capability Broker

This milestone establishes the initial Python backend foundation, strictly bound to localhost (`127.0.0.1`).

### Key Architectural Controls
- **Capability Broker:** Every tool proposal is independently evaluated against fixed schema contracts, session permissions, and workspace boundaries before any OS action is performed.
- **Untrusted Data Boundary:** Workspace file names, file contents, and tool execution outputs are labeled as untrusted data. External text cannot grant permissions or trigger commands (mitigating indirect prompt injection).
- **Workspace Confinement:** File inspection is restricted to an explicitly configured `FridayWorkspace` directory, with strict rejection of path traversals (`..`), drive prefixes, null bytes, and external symlink/junction targets.
- **Honest Verification:** Tool outcomes report execution status separately from verified physical state. Actions where state feedback is unavailable (such as Windows virtual key dispatch) are explicitly marked unverified.
- **Localhost Privacy:** All network services are bound to `127.0.0.1`. No cloud fallbacks or telemetry data leakage.

---

## Project Structure

```
Friday/
├── backend/
│   └── friday/
│       ├── api/               # FastAPI backend (health check, chat endpoints)
│       ├── conversation/      # Conversation orchestrator and turn management
│       ├── models/            # Replaceable model adapters (Ollama adapter)
│       ├── policy/            # Capability Broker and permission rules
│       ├── tools/             # Fixed tool registry & implementations
│       │   ├── time_tool.py   # Host date/time retrieval (deterministic)
│       │   ├── workspace_tool.py # Bounded, secure workspace listing
│       │   └── media_tool.py  # Windows media control adapter
│       ├── cli.py             # Interactive CLI REPL for testing
│       └── config.py          # Central security limits & settings
├── schemas/                   # Pydantic data contracts (proposals, results, policies)
├── tests/
│   ├── unit/                  # Schema, tool, and broker unit tests
│   ├── integration/           # FastAPI and live Ollama tests
│   └── security/              # Path traversal & adversarial prompt injection tests
├── pyproject.toml             # Project dependencies and configuration
└── .gitignore                 # Excludes venvs, caches, logs, and private data
```

---

## Prerequisites

1. **Python:** 3.11 or 3.12 (64-bit)
2. **Ollama:** Installed and running locally (`ollama serve`).
3. **Local Model:** `qwen2.5:7b` (run `ollama pull qwen2.5:7b`).

---

## Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Samudra-GITHub/F.R.I.D.A.Y.git
   cd F.R.I.D.A.Y
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```powershell
   pip install fastapi uvicorn pydantic httpx pytest pytest-asyncio
   ```

---

## Running the Assistant

### 1. Interactive CLI REPL
Test conversation and tool execution directly in the terminal:
```powershell
python backend/friday/cli.py
```
- During startup, you will be prompted to grant or deny media control permission for the session.
- Type `status` to inspect active session permissions.
- Type `exit` or `quit` to end the session.

### 2. FastAPI Backend Service
Start the local REST API (bound to `127.0.0.1` only):
```powershell
uvicorn backend.friday.api.app:app --host 127.0.0.1 --port 8000
```
- Health Check: `GET http://127.0.0.1:8000/health`
- Chat Endpoint: `POST http://127.0.0.1:8000/chat`

---

## Running the Test Suite

Run the full unit, integration, and security test suite:
```powershell
pytest -v
```

The test suite covers:
- Contract validation and schema conformity.
- Fixed tool execution and result verification.
- Capability Broker authorization and unknown tool rejection.
- Path traversal escapes (`../`, `..\`, absolute paths, null bytes, junctions).
- Adversarial prompt injection defense (blocking unauthorized arbitrary command execution).
- Live local Ollama round-trip execution using `qwen2.5:7b`.
