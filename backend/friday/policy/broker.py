"""Application-enforced Capability Broker for F.R.I.D.A.Y.

The model proposes actions; the Capability Broker independently enforces
identity, permissions, argument schemas, scopes, and safety boundaries.
"""

from typing import Any, Dict, List, Optional, Tuple
from schemas.contracts import (
    PermissionType,
    PolicyDecision,
    SessionPolicy,
    ToolCallProposal,
)
from backend.friday.tools.base import BaseTool
from backend.friday.tools.registry import ToolRegistry


class CapabilityBroker:
    """Independent security authority governing tool execution."""

    def __init__(self, registry: ToolRegistry, session_policy: SessionPolicy) -> None:
        self.registry = registry
        self.session_policy = session_policy

    def _validate_schema(self, schema: Dict[str, Any], arguments: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate proposed arguments against declared JSON schema."""
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional_allowed = schema.get("additionalProperties", True)

        # Check required fields
        for req_field in required:
            if req_field not in arguments:
                return False, f"Missing required parameter '{req_field}'"

        # Check unexpected extra fields if additionalProperties is False
        if not additional_allowed:
            for arg_key in arguments:
                if arg_key not in properties:
                    return False, f"Unexpected parameter '{arg_key}' not allowed by schema"

        # Check enum constraints and basic types
        for key, val in arguments.items():
            if key in properties:
                prop_spec = properties[key]
                if "enum" in prop_spec and val not in prop_spec["enum"]:
                    return False, f"Parameter '{key}' value '{val}' not in allowed enum: {prop_spec['enum']}"
                expected_type = prop_spec.get("type")
                if expected_type == "string" and not isinstance(val, str):
                    return False, f"Parameter '{key}' expected string, got {type(val).__name__}"
                elif expected_type == "integer" and not isinstance(val, int):
                    return False, f"Parameter '{key}' expected integer, got {type(val).__name__}"
                elif expected_type == "boolean" and not isinstance(val, bool):
                    return False, f"Parameter '{key}' expected boolean, got {type(val).__name__}"

        return True, "Schema valid"

    def evaluate(self, proposal: ToolCallProposal) -> PolicyDecision:
        """Evaluate a model's tool proposal against fixed registry and session policy.
        
        Guarantees:
        - Unknown tools rejected immediately.
        - Invalid schemas rejected before any system action.
        - Permissions enforced independently of model desires.
        - Scopes and boundaries rigidly validated.
        """
        # 1. Check fixed tool registry
        tool: Optional[BaseTool] = self.registry.get(proposal.tool_name)
        if tool is None:
            return PolicyDecision(
                allowed=False,
                reason=f"Rejected: Tool '{proposal.tool_name}' does not exist in the fixed registry."
            )

        # 2. Check schema conformity
        is_valid_schema, schema_error = self._validate_schema(tool.parameters_schema, proposal.arguments)
        if not is_valid_schema:
            return PolicyDecision(
                allowed=False,
                reason=f"Rejected: Arguments failed schema validation: {schema_error}"
            )

        # 3. Check session permissions
        if tool.required_permission not in self.session_policy.allowed_permissions:
            return PolicyDecision(
                allowed=False,
                reason=f"Rejected: Session lacks required permission '{tool.required_permission.value}'."
            )

        # 4. Tool-specific scope validation
        if tool.name == "control_media":
            if not self.session_policy.media_control_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Rejected: Media control is disabled for this session."
                )

        if tool.name == "list_workspace":
            subpath = proposal.arguments.get("subpath", "")
            # Basic syntactic pre-check at broker level before tool resolution
            if "\0" in str(subpath):
                return PolicyDecision(
                    allowed=False,
                    reason="Rejected: Path contains forbidden null byte."
                )
            if ".." in str(subpath).replace("\\", "/").split("/"):
                # Path traversal attempt detected
                return PolicyDecision(
                    allowed=False,
                    reason=f"Rejected: Path traversal sequence '..' detected in subpath '{subpath}'."
                )

        return PolicyDecision(
            allowed=True,
            reason="Authorized by Capability Broker."
        )
