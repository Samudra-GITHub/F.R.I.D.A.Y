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
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": malicious_path})
    msg = str(exc_info.value).lower()
    assert "escapes" in msg or "relative" in msg or "drive" in msg or "stream" in msg


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
    link_path = workspace / "escape_link"
    link_created = False
    try:
        link_path.symlink_to(outside_dir, target_is_directory=True)
        link_created = True
    except OSError:
        # On Windows without Developer Mode, symlink_to raises WinError 1314.
        # Directory junctions do not require elevated privileges.
        try:
            import _winapi
            _winapi.CreateJunction(str(outside_dir), str(link_path))
            link_created = True
        except Exception:
            pass

    if not link_created:
        pytest.skip("Neither symlink nor junction could be created on this filesystem.")

    tool = ListWorkspaceTool(workspace_root=workspace)
    # Attempting to list through the external link must be rejected
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": "escape_link"})
    assert "escapes" in str(exc_info.value).lower() or "junction" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_workspace_rejects_alternate_data_streams(temp_workspace: Path):
    """Ensure alternate data stream colons are rejected."""
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(PermissionError) as exc_info:
        await tool.execute({"subpath": "test.txt:hidden_stream"})
    assert "alternate data streams" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_workspace_rejects_nonexistent_directory(temp_workspace: Path):
    """Ensure querying a nonexistent directory raises FileNotFoundError."""
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(FileNotFoundError):
        await tool.execute({"subpath": "nonexistent_folder_abc"})


@pytest.mark.asyncio
async def test_workspace_rejects_file_as_directory(temp_workspace: Path):
    """Ensure querying a file path raises NotADirectoryError."""
    file_path = temp_workspace / "sample_file.txt"
    file_path.write_text("just a text file")
    tool = ListWorkspaceTool(workspace_root=temp_workspace)
    with pytest.raises(NotADirectoryError):
        await tool.execute({"subpath": "sample_file.txt"})


@pytest.mark.asyncio
async def test_external_junction_flagged_in_listing(tmp_path: Path):
    """Ensure that an external junction inside workspace root is marked is_external_target=True."""
    workspace = tmp_path / "FridayWorkspace"
    workspace.mkdir()
    outside_dir = tmp_path / "ExternalDir"
    outside_dir.mkdir()

    junc_path = workspace / "ext_junction"
    try:
        import _winapi
        _winapi.CreateJunction(str(outside_dir), str(junc_path))
    except Exception:
        pytest.skip("Windows junction creation unavailable.")

    tool = ListWorkspaceTool(workspace_root=workspace)
    result = await tool.execute({})
    entries = {e["name"]: e for e in result["entries"]}
    assert "ext_junction" in entries
    assert entries["ext_junction"]["is_external_target"] is True
    assert entries["ext_junction"]["is_symlink"] is True

