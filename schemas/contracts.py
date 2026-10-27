"""Typed Pydantic data contracts for F.R.I.D.A.Y. Milestone 1.

These contracts enforce clear boundaries between the model,
the capability broker, tool execution, and the verification layer.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PermissionType(str, Enum):
    """Granular permissions governed by the Capability Broker."""
    SYSTEM_TIME = "system:time"
    WORKSPACE_READ = "workspace:read"
    MEDIA_CONTROL = "media:control"


class ToolCallProposal(BaseModel):
    """A tool call proposed by an AI model.
    
    Treated as an unverified request until evaluated by the Capability Broker.
    """
    tool_name: str = Field(..., description="The name of the requested tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Raw arguments supplied by the model")


class PolicyDecision(BaseModel):
    """The capability broker's authorization verdict for a tool call proposal."""
    allowed: bool = Field(..., description="Whether the tool execution is permitted")
    reason: str = Field(..., description="Human-readable rationale for the decision")
    requires_approval: bool = Field(default=False, description="Whether explicit interactive user consent is needed")


class ToolExecutionResult(BaseModel):
    """The outcome of an authorized tool execution, including independent verification."""
    tool_name: str
    ok: bool
    output: Any = Field(default=None, description="The returned data or output detail")
    error: Optional[str] = Field(default=None, description="Error detail if execution failed")
    is_untrusted_content: bool = Field(
        default=True,
        description="Flag indicating output contains external/untrusted data"
    )
    verified: bool = Field(
        default=False,
        description="Whether an independent state check confirmed the expected effect"
    )
    verification_details: Optional[str] = Field(
        default=None,
        description="Explanation or evidence from independent state inspection"
    )


class SessionPolicy(BaseModel):
    """Active permissions and policies for the current session.
    
    The model cannot modify this object.
    """
    allowed_permissions: set[PermissionType] = Field(
        default_factory=lambda: {PermissionType.SYSTEM_TIME, PermissionType.WORKSPACE_READ}
    )
    media_control_enabled: bool = Field(
        default=False,
        description="Whether media control is allowed in this session"
    )
    allowed_workspace_root: str = Field(
        ...,
        description="Absolute path to the only authorized workspace directory"
    )


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """A message in the conversational history."""
    role: ChatRole
    content: str
    tool_name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class HealthResponse(BaseModel):
    """Status payload returned by the health endpoint."""
    status: str
    version: str
    model: str
    ollama_reachable: bool
    workspace_root: str
    media_control_enabled: bool
