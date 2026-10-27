"""Abstract Base Class for replaceable AI model adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from schemas.contracts import ChatMessage


class ModelResponse:
    """Standardized response from any model adapter."""
    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw_metadata = raw_metadata or {}


class BaseModelAdapter(ABC):
    """Abstract model interface allowing seamless replacement of model providers."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the model runtime is reachable and ready."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Generate response with optional tool specifications."""
        pass
