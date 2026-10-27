"""Unit tests for fixed tools and result verification."""

import pytest
from pathlib import Path
from backend.friday.tools.time_tool import GetLocalTimeTool
from backend.friday.tools.workspace_tool import ListWorkspaceTool
from backend.friday.tools.media_tool import ControlMediaTool


@pytest.mark.asyncio
async def test_get_local_time_tool():
    tool = GetLocalTimeTool()
    output = await tool.execute({})
    assert isinstance(output, str)
    assert len(output) > 10
    verified, details = await tool.verify({}, output)
    assert verified is True
    assert "Deterministic host time retrieved" in details


@pytest.mark.asyncio
async def test_list_workspace_tool(temp_workspace: Path):
    # Setup test workspace contents
    (temp_workspace / "file1.txt").write_text("sample content")
    (temp_workspace / "file2.py").write_text("print('test')")
    sub = temp_workspace / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("# Markdown")

    tool = ListWorkspaceTool(workspace_root=temp_workspace, max_entries=10)
    result = await tool.execute({})
    
    assert result["total_found"] == 3
    assert result["truncated"] is False
    assert result["subpath"] == ""
    entry_names = [e["name"] for e in result["entries"]]
    assert "subdir" in entry_names
    assert "file1.txt" in entry_names
    assert "file2.py" in entry_names

    # Test independent verification
    verified, details = await tool.verify({}, result)
    assert verified is True


@pytest.mark.asyncio
async def test_list_workspace_tool_truncation(temp_workspace: Path):
    # Create 15 files with max_entries=5
    for i in range(15):
        (temp_workspace / f"doc_{i:02d}.txt").write_text(f"content {i}")

    tool = ListWorkspaceTool(workspace_root=temp_workspace, max_entries=5)
    result = await tool.execute({})
    
    assert result["total_found"] == 15
    assert len(result["entries"]) == 5
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_control_media_tool_verification_honesty():
    """Verify that media control reports action execution without falsely claiming state verification."""
    tool = ControlMediaTool()
    
    # Check invalid action
    with pytest.raises(ValueError):
        await tool.execute({"action": "invalid_action"})

    # Check verification reports limitations honestly
    verified, details = await tool.verify({"action": "pause"}, {})
    assert verified is False
    assert "Windows media playback state cannot be verified" in details
