"""Interactive Command-Line Interface for F.R.I.D.A.Y. Milestone 1.

Provides terminal interaction with the capability-brokered assistant engine.
"""

import asyncio
import sys
from pathlib import Path

# Add project root and backend to sys.path if running directly
sys_path_root = Path(__file__).resolve().parent.parent.parent
if str(sys_path_root) not in sys.path:
    sys.path.insert(0, str(sys_path_root))
backend_path = sys_path_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from schemas.contracts import PermissionType, SessionPolicy
from backend.friday.config import settings
from backend.friday.models.ollama_adapter import OllamaAdapter, ModelConnectionError
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.tools.media_tool import ControlMediaTool
from backend.friday.conversation.orchestrator import ConversationOrchestrator


async def main() -> None:
    print("=" * 60)
    print(" F.R.I.D.A.Y. — Personal AI Desktop Assistant (Milestone 1)")
    print("=" * 60)
    print(f"Backend Host:      {settings.host}:{settings.port}")
    print(f"Local Model:       {settings.model_name} (via {settings.ollama_base_url})")
    print(f"Workspace Root:    {settings.workspace_root}")
    print("-" * 60)

    # Check Ollama connection
    ollama = OllamaAdapter(
        base_url=settings.ollama_base_url,
        model_name=settings.model_name,
        timeout=settings.request_timeout_seconds,
    )
    is_online = await ollama.is_available()
    if is_online:
        print("[✓] Ollama service detected and operational.")
    else:
        print("[!] WARNING: Ollama service is not reachable at " + settings.ollama_base_url)
        print("    Ensure 'ollama serve' is running.")

    # Media control authorization prompt
    allow_media_input = input("\nAuthorize media control for this session? [y/N]: ").strip().lower()
    media_authorized = allow_media_input == "y"

    allowed_permissions = {PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ}
    if media_authorized:
        allowed_permissions.add(PermissionType.MEDIA_CONTROL)

    session_policy = SessionPolicy(
        allowed_permissions=allowed_permissions,
        media_control_enabled=media_authorized,
        allowed_workspace_root=str(settings.workspace_root),
    )

    registry = ToolRegistry()
    registry.register(GetLocalTimeTool())
    registry.register(ListWorkspaceTool(workspace_root=settings.workspace_root, max_entries=settings.max_workspace_entries))
    registry.register(ControlMediaTool())

    broker = CapabilityBroker(registry=registry, session_policy=session_policy)
    orchestrator = ConversationOrchestrator(
        model_adapter=ollama,
        registry=registry,
        broker=broker,
        max_turns=settings.max_turns_per_request,
        max_calls_per_turn=settings.max_tool_calls_per_turn,
    )

    print("\nSession initialized. Capability Broker active.")
    print("Type your message or 'exit' / 'quit' to end.\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("\nShutting down F.R.I.D.A.Y. session. Goodbye.")
                break
            if user_input.lower() == "status":
                print(f"[Policy Status] Media Allowed: {session_policy.media_control_enabled}")
                print(f"[Policy Status] Workspace: {session_policy.allowed_workspace_root}")
                print(f"[Policy Status] Registered Tools: {[t.name for t in registry.list_tools()]}")
                continue

            print("FRIDAY is thinking...")
            reply = await orchestrator.run_turn(user_input)
            print(f"\nFRIDAY: {reply}\n")

        except KeyboardInterrupt:
            print("\nEmergency stop triggered by keyboard interrupt. Halting session.")
            break
        except ModelConnectionError as exc:
            print(f"\n[Model Error] Failed to communicate with Ollama: {exc}\n")
        except Exception as exc:
            print(f"\n[Error] {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
