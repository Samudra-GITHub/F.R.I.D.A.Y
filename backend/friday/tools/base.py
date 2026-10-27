"""Abstract Base Class for F.R.I.D.A.Y. tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from schemas.contracts import PermissionType, ToolExecutionResult


class BaseTool(ABC):
    """Abstract tool contract enforcing typed declarations and independent verification."""
    name: str
    description: str
    required_permission: PermissionType
    parameters_schema: Dict[str, Any]

    def to_ollama_definition(self) -> Dict[str, Any]:
        """Convert tool declaration to Ollama / OpenAI-compatible tool spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool action after Capability Broker authorization."""
        pass

    @abstractmethod
    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        """Independently verify whether the action achieved its intended state.
        
        Returns:
            Tuple[bool, Optional[str]]: (is_verified, verification_details)
        """
        pass
