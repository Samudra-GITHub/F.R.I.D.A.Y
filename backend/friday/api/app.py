"""FastAPI backend application for W.E.D.N.E.S.D.A.Y. Milestone 1.

Strictly binds to localhost (127.0.0.1) and enforces typed request/response contracts.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from typing import Literal, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from schemas.contracts import (
    HealthResponse,
    SessionPolicy,
    PermissionType,
    ConversationRequest,
    ConversationResponse,
    ConversationResetRequest,
    ConversationResetResponse,
)
from backend.friday.api.voice_router import router as voice_router, set_voice_service, get_voice_service

from backend.friday.config import settings
from backend.friday.models.ollama_adapter import OllamaAdapter
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.tools.media_tool import ControlMediaTool
from backend.friday.tools.location_tool import GetDeviceLocationTool
from backend.friday.tools.places_tool import ReverseGeocodeTool, SearchNearbyPlacesTool
from backend.friday.tools.world_tools import (
    GetDisasterAlertsTool,
    GetEarthquakesTool,
    GetNaturalEventsTool,
    GetWeatherTool,
    GetWorldStatusTool,
)
from backend.friday.location.service import LocationService
from backend.friday.api.location_router import router as location_router, location_service
from backend.friday.api.world_router import router as world_router, world_service
from backend.friday.conversation.orchestrator import ConversationOrchestrator
from backend.friday.memory import MEMORY_KINDS, MemoryStore


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
tool_registry.register(GetDeviceLocationTool(location_service=location_service))
tool_registry.register(ReverseGeocodeTool(location_service=location_service))
tool_registry.register(SearchNearbyPlacesTool(location_service=location_service))
tool_registry.register(GetEarthquakesTool(world_service=world_service))
tool_registry.register(GetWeatherTool(world_service=world_service))
tool_registry.register(GetNaturalEventsTool(world_service=world_service))
tool_registry.register(GetDisasterAlertsTool(world_service=world_service))
tool_registry.register(GetWorldStatusTool(world_service=world_service))

# Configure initial allowed permissions
initial_permissions = {PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ}
if settings.location_read_enabled:
    initial_permissions.add(PermissionType.LOCATION_READ)
if settings.places_search_enabled:
    initial_permissions.add(PermissionType.PLACES_SEARCH)
if settings.media_control_enabled:
    initial_permissions.add(PermissionType.MEDIA_CONTROL)
if getattr(settings, "world_read_enabled", True):
    initial_permissions.add(PermissionType.WORLD_READ)

session_policy = SessionPolicy(
    allowed_permissions=initial_permissions,
    media_control_enabled=settings.media_control_enabled,
    location_read_enabled=settings.location_read_enabled,
    location_control_enabled=False,  # Control actions are never automated by the LLM
    places_search_enabled=settings.places_search_enabled,
    world_read_enabled=getattr(settings, "world_read_enabled", True),
    allowed_workspace_root=str(settings.workspace_root),
)

capability_broker = CapabilityBroker(registry=tool_registry, session_policy=session_policy)
memory_store = MemoryStore(settings.memory_db_path)
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
    memory_store=memory_store,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    # Ensure workspace root exists
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    # Continuous location resumes only if the user opted in, and ends with the app.
    location_service.resume_if_opted_in()
    yield
    location_service.stop_worker_for_shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="W.E.D.N.E.S.D.A.Y. Personal AI Desktop Assistant Backend",
    lifespan=lifespan,
)

# Reject requests whose Host header is not local (DNS-rebinding protection). "testserver"
# is the host used by FastAPI's in-process TestClient.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount Routers (both prefix paths for direct and proxied calls)
app.include_router(location_router)
app.include_router(location_router, prefix="/api")
app.include_router(world_router)
app.include_router(world_router, prefix="/api")
app.include_router(voice_router)
app.include_router(voice_router, prefix="/api")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return health status, active local model, and security policies."""
    is_ollama_online = await ollama_adapter.is_available()
    loc_status = location_service.get_status()
    return HealthResponse(
        status="healthy",
        version=settings.version,
        model=settings.model_name,
        ollama_reachable=is_ollama_online,
        workspace_root=str(settings.workspace_root),
        media_control_enabled=settings.media_control_enabled,
        location_read_enabled=session_policy.location_read_enabled,
        location_tracking_enabled=loc_status.tracking_enabled,
        places_search_enabled=session_policy.places_search_enabled,
        world_read_enabled=session_policy.world_read_enabled,
    )


@app.post("/chat", response_model=ConversationResponse)
@app.post("/api/chat", response_model=ConversationResponse)
async def chat_endpoint(request: ConversationRequest) -> ConversationResponse:
    """Process a conversational turn through the Capability Broker and tools."""
    try:
        return await orchestrator.execute_turn(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")


@app.post("/chat/reset", response_model=ConversationResetResponse)
@app.post("/api/chat/reset", response_model=ConversationResetResponse)
async def chat_reset_endpoint(
    request: ConversationResetRequest = ConversationResetRequest(),
) -> ConversationResetResponse:
    """Reset conversation session history."""
    try:
        orchestrator.reset_conversation(request.conversation_id)
        return ConversationResetResponse(
            status="ok",
            conversation_id=request.conversation_id,
            message="Conversation history cleared",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reset error: {exc}")



class ChatCancelRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=128)


@app.post("/chat/cancel")
@app.post("/api/chat/cancel")
async def chat_cancel_endpoint(request: ChatCancelRequest) -> dict:
    """Stop an in-flight turn before its next model call or tool dispatch."""
    orchestrator.cancel(request.request_id)
    return {"status": "ok", "request_id": request.request_id}


# ---- Capabilities, consent, and audit ---------------------------------------

@app.get("/capabilities")
@app.get("/api/capabilities")
async def capabilities_endpoint() -> dict:
    """Describe every registered tool and whether the current session permits it."""
    tools = []
    for tool in tool_registry.list_tools():
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "permission": tool.required_permission.value,
            "permitted": tool.required_permission in session_policy.allowed_permissions,
            "parameters": tool.parameters_schema,
        })
    return {"tools": tools, "consents": capability_broker.consents()}


class ConsentRequest(BaseModel):
    consent: Literal["media_control", "location_read", "places_search", "world_read"]
    enabled: bool


@app.post("/policy/consent")
@app.post("/api/policy/consent")
async def policy_consent_endpoint(request: ConsentRequest) -> dict:
    """Grant or revoke a session consent. Only reachable from the local UI, never from the model."""
    return {"consents": capability_broker.set_consent(request.consent, request.enabled)}


@app.get("/audit")
@app.get("/api/audit")
async def audit_endpoint(limit: int = 100) -> dict:
    """Recent broker decisions (redacted: argument digests only, never values)."""
    return {"events": capability_broker.audit_events(max(1, min(limit, 200)))}


# ---- Memory -----------------------------------------------------------------

class MemoryCreateRequest(BaseModel):
    kind: str = Field(..., description=f"One of: {', '.join(MEMORY_KINDS)}")
    content: str = Field(..., min_length=1, max_length=1000)
    scope: str = Field(default="personal", max_length=64)
    expires_at: Optional[str] = Field(default=None, description="ISO-8601 UTC expiry, or null to keep until deleted")


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    kind: Optional[str] = None


@app.get("/memories")
@app.get("/api/memories")
def list_memories(q: Optional[str] = None) -> dict:
    items = memory_store.search(q) if q else memory_store.list()
    return {"memories": items}


@app.post("/memories")
@app.post("/api/memories")
def create_memory(request: MemoryCreateRequest) -> dict:
    try:
        record = memory_store.create(
            kind=request.kind,
            content=request.content,
            scope=request.scope,
            source_kind="explicit_user_statement",
            expires_at=request.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    capability_broker.record("memory", "memory.create", "stored", f"kind={request.kind}")
    return {"memory": record}


@app.patch("/memories/{memory_id}")
@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: str, request: MemoryUpdateRequest) -> dict:
    try:
        record = memory_store.update(memory_id, content=request.content, kind=request.kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if record is None:
        raise HTTPException(status_code=404, detail="Memory not found or already deleted")
    capability_broker.record("memory", "memory.update", "corrected", memory_id)
    return {"memory": record}


@app.delete("/memories/{memory_id}")
@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str) -> dict:
    if not memory_store.delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found or already deleted")
    capability_broker.record("memory", "memory.delete", "deleted", memory_id)
    return {"status": "deleted", "id": memory_id}


# ---- Approvals (argument-bound, single use; reachable only from the local UI) ------

class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]


@app.get("/approvals")
@app.get("/api/approvals")
async def list_approvals(conversation_id: Optional[str] = None) -> dict:
    return {"approvals": capability_broker.list_approvals(conversation_id)}


@app.post("/approvals/{approval_id}/decision")
@app.post("/api/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, request: ApprovalDecisionRequest) -> dict:
    """Approve or deny one pending action. A second decision on the same approval returns 409."""
    try:
        record = await capability_broker.decide(approval_id, request.decision == "approve")
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown approval")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"approval": record}


# ---- Diagnostics -----------------------------------------------------------------
from backend.friday.api import diagnostics as _diagnostics  # noqa: E402

_diagnostics.configure(
    ollama_adapter=ollama_adapter,
    voice_service=get_voice_service,
    world_service=world_service,
    memory_store=memory_store,
    location_service=location_service,
)
app.include_router(_diagnostics.router)
