"""Security tests verifying workspace confinement and path escape protections."""

import pytest
from pathlib import Path
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from schemas.contracts import PermissionType, SessionPolicy, ToolCallProposal
from backend.friday.policy.broker import CapabilityBroker
from backend.friday.tools.registry import ToolRegistry


@pytest.mark.parametrize("malicious_path", [
    "../",
    "..\\",
    "../../",
    "..\\..\\",
    "folder/../../outside",
    "..",
    "C:\\Windows",
    "C:/Windows",
    "\\Windows\\System32",
    "/etc/passwd",
    "nested/../../../Windows",
])
@pytest.mark.asyncio
async def test_workspace_rejects_path_traversal(temp_workspace: Path, malicious_path: str):
    """Ensure ListWorkspaceTool strictly prevents accessing paths outside the root."""
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": malicious_path})
    assert "escapes" in str(exc_info.value).lower() or "relative" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_workspace_rejects_null_bytes(temp_workspace: Path):
    """Ensure null byte injection is rejected."""
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": "sub\0folder"})
    assert "null byte" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_broker_catches_path_traversal_before_execution(temp_workspace: Path):
    """Capability Broker pre-validates subpath arguments before invoking the filesystem."""
    registry = ToolRegistry()
    registry.register(ListWorkspaceTool(workspace_root=temp_workspace))

    policy = SessionPolicy(
        allowed_permissions={PermissionType.WORKSPACE_READ},
        allowed_workspace_root=str(temp_workspace),
    )
    broker = CapabilityBroker(registry=registry, session_policy=policy)

    proposal = ToolCallProposal(tool_name="list_workspace", arguments={"subpath": "../secret"})
    verdict = broker.evaluate(proposal)
    assert verdict.allowed is False
    assert "traversal sequence" in verdict.reason.lower()


@pytest.mark.asyncio
async def test_symlink_or_junction_outside_root(tmp_path: Path):
    """Ensure symlinks or junctions pointing outside workspace root cannot be traversed."""
    workspace = tmp_path / "FridayWorkspace"
    workspace.mkdir()
    outside_dir = tmp_path / "SensitiveOutsideDir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("classified")

    link_path = workspace / "escape_link"
    try:
        # Create a directory symlink or junction if OS allows (may require privileges on Windows)
        link_path.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation requires elevated privileges on this Windows configuration.")

    tool = ListWorkspaceTool(workspace_root=workspace)
    # Attempting to list through the external link must be rejected
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": "escape_link"})
    assert "escapes" in str(exc_info.value).lower() or "junction" in str(exc_info.value).lower()
