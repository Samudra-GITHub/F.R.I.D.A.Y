"""Fixed Tool Registry for F.R.I.D.A.Y."""

from typing import Any, Dict, List, Optional
from backend.friday.tools.base import BaseTool


class ToolRegistry:
    """Explicit, fixed tool registry. The model cannot register new tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def to_ollama_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_ollama_definition() for tool in self._tools.values()]
