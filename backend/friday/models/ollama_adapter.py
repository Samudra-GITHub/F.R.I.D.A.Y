"""Ollama model adapter using native asynchronous HTTP client."""

import json
from typing import Any, Dict, List, Optional
import httpx
from schemas.contracts import ChatMessage, ChatRole
from backend.friday.models.base import BaseModelAdapter, ModelResponse


class ModelConnectionError(RuntimeError):
    """Raised when the local model service cannot be reached."""
    pass


class OllamaAdapter(BaseModelAdapter):
    """Model adapter communicating with a local Ollama instance."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model_name: str = "qwen2.5:7b",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Check if Ollama is running and responding."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def _convert_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Convert internal ChatMessage schemas to Ollama API message payloads."""
        payload: List[Dict[str, Any]] = []
        for msg in messages:
            item: Dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.role == ChatRole.TOOL and msg.tool_name:
                item["name"] = msg.tool_name
            if msg.tool_calls:
                item["tool_calls"] = msg.tool_calls
            payload.append(item)
        return payload

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ModelResponse:
        """Send chat request to Ollama `/api/chat` with tool definitions."""
        request_body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": self._convert_messages(messages),
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 700,
            },
        }
        if tools:
            request_body["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=request_body,
                )
                if response.status_code != 200:
                    raise ModelConnectionError(
                        f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                data = response.json()
        except httpx.RequestError as exc:
            raise ModelConnectionError(f"Could not connect to Ollama at {self.base_url}: {exc}") from exc

        message_data = data.get("message", {})
        content = message_data.get("content", "") or ""
        tool_calls = message_data.get("tool_calls", [])

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            raw_metadata={
                "total_duration": data.get("total_duration"),
                "eval_count": data.get("eval_count"),
            },
        )
