"""Live integration test against the local Ollama instance."""

import pytest
from pathlib import Path
from schemas.contracts import PermissionType, SessionPolicy
from backend.friday.config import settings
from backend.friday.models.ollama_adapter import OllamaAdapter
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.conversation.orchestrator import ConversationOrchestrator


@pytest.mark.asyncio
async def test_live_ollama_tool_calling(temp_workspace: Path):
    """Test full round-trip tool execution with local Ollama qwen2.5:7b."""
    ollama = OllamaAdapter(
        base_url=settings.ollama_base_url,
        model_name=settings.model_name,
        timeout=30.0,
    )
    if not await ollama.is_available():
        pytest.skip("Local Ollama service is not reachable on localhost:11434.")

    # Create dummy file in test workspace
    (temp_workspace / "welcome.txt").write_text("Hello from Friday test.")

    registry = ToolRegistry()
    registry.register(GetLocalTimeTool())
    registry.register(ListWorkspaceTool(workspace_root=temp_workspace))

    policy = SessionPolicy(
        allowed_permissions={PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ},
        allowed_workspace_root=str(temp_workspace),
    )
    broker = CapabilityBroker(registry=registry, session_policy=policy)
    orchestrator = ConversationOrchestrator(
        model_adapter=ollama,
        registry=registry,
        broker=broker,
    )

    # Ask a question that requires tool execution
    reply = await orchestrator.run_turn("What is the current time?")
    assert isinstance(reply, str)
    assert len(reply) > 0
