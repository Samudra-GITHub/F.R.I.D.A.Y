"""FastAPI backend application for F.R.I.D.A.Y. Milestone 1.

Strictly binds to localhost (127.0.0.1) and enforces typed request/response contracts.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from schemas.contracts import HealthResponse, SessionPolicy
from backend.friday.config import settings
from backend.friday.models.ollama_adapter import OllamaAdapter
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.tools.media_tool import ControlMediaTool
from backend.friday.conversation.orchestrator import ConversationOrchestrator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User input prompt")


class ChatResponse(BaseModel):
    response: str
    model: str


# Module-level instances initialized during lifespan
tool_registry = ToolRegistry()
tool_registry.register(GetLocalTimeTool())
tool_registry.register(ListWorkspaceTool(workspace_root=settings.workspace_root, max_entries=settings.max_workspace_entries))
tool_registry.register(ControlMediaTool())

session_policy = SessionPolicy(
    media_control_enabled=settings.media_control_enabled,
    allowed_workspace_root=str(settings.workspace_root),
)

capability_broker = CapabilityBroker(registry=tool_registry, session_policy=session_policy)
ollama_adapter = OllamaAdapter(
    base_url=settings.ollama_base_url,
    model_name=settings.model_name,
    timeout=settings.request_timeout_seconds,
)
orchestrator = ConversationOrchestrator(
    model_adapter=ollama_adapter,
    registry=tool_registry,
    broker=capability_broker,
    max_turns=settings.max_turns_per_request,
    max_calls_per_turn=settings.max_tool_calls_per_turn,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    # Ensure workspace root exists
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="F.R.I.D.A.Y. Personal AI Desktop Assistant Backend",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return health status, active local model, and security policies."""
    is_ollama_online = await ollama_adapter.is_available()
    return HealthResponse(
        status="healthy",
        version=settings.version,
        model=settings.model_name,
        ollama_reachable=is_ollama_online,
        workspace_root=str(settings.workspace_root),
        media_control_enabled=settings.media_control_enabled,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Process a conversational turn through the Capability Broker and tools."""
    try:
        reply = await orchestrator.run_turn(request.message)
        return ChatResponse(response=reply, model=settings.model_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")
