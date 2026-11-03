"""Application-enforced Capability Broker for W.E.D.N.E.S.D.A.Y.

The model proposes actions; the Capability Broker independently enforces
identity, permissions, argument schemas, scopes, and safety boundaries.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Deque, Dict, List, Optional, Tuple
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

    # Consents the user may grant or revoke for the session from the authenticated UI.
    # The model has no path to these methods.
    CONSENT_FIELDS: Dict[str, Tuple[str, PermissionType]] = {
        "media_control": ("media_control_enabled", PermissionType.MEDIA_CONTROL),
        "location_read": ("location_read_enabled", PermissionType.LOCATION_READ),
        "places_search": ("places_search_enabled", PermissionType.PLACES_SEARCH),
        "world_read": ("world_read_enabled", PermissionType.WORLD_READ),
    }

    # Side-effecting tools whose denied calls may be approved once, for the exact arguments,
    # by the user in the UI. Everything else stays a plain denial.
    APPROVABLE_TOOLS = {"control_media"}
    APPROVAL_TTL_SECONDS = 300

    def __init__(self, registry: ToolRegistry, session_policy: SessionPolicy, audit_size: int = 200) -> None:
        self.registry = registry
        self.session_policy = session_policy
        # Redacted, in-memory decision log: tool name, decision, reason, and a digest of
        # the arguments. Argument values are never stored.
        self._audit: Deque[Dict[str, Any]] = deque(maxlen=audit_size)
        self._audit_seq = 0
        self._approvals: Dict[str, Dict[str, Any]] = {}

    # ---- Argument-bound, single-use approvals -------------------------------------------
    #
    # Lifecycle: pending → executing → succeeded | failed | outcome_unknown, or
    # pending → denied | expired. An approval binds the conversation, tool, canonical
    # arguments (digest), and expiry. It is consumed before dispatch, so a repeated or
    # concurrent decision can never run the action twice. Only the UI endpoint calls
    # decide(); the model has no path to it.

    def request_approval(self, proposal: ToolCallProposal, conversation_id: str, reason: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        approval_id = "apr_" + hashlib.sha256(f"{now.timestamp()}:{self._audit_seq}:{proposal.tool_name}".encode()).hexdigest()[:16]
        record = {
            "approval_id": approval_id,
            "conversation_id": conversation_id,
            "tool_name": proposal.tool_name,
            "arguments": dict(proposal.arguments),
            "args_digest": self.argument_digest(proposal.arguments),
            "reason": reason,
            "status": "pending",
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": datetime.fromtimestamp(now.timestamp() + self.APPROVAL_TTL_SECONDS, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "result": None,
        }
        if len(self._approvals) >= 100:
            oldest = sorted(self._approvals.values(), key=lambda r: r["created_at"])[:20]
            for r in oldest:
                self._approvals.pop(r["approval_id"], None)
        self._approvals[approval_id] = record
        self.record("approval", proposal.tool_name, "requested", "Awaiting user approval", proposal.arguments)
        return dict(record)

    def _refresh_expiry(self, record: Dict[str, Any]) -> None:
        if record["status"] == "pending" and datetime.now(timezone.utc).isoformat() > record["expires_at"].replace("Z", "+00:00"):
            record["status"] = "expired"

    def list_approvals(self, conversation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for r in self._approvals.values():
            self._refresh_expiry(r)
            if conversation_id is None or r["conversation_id"] == conversation_id:
                out.append(dict(r))
        return sorted(out, key=lambda r: r["created_at"], reverse=True)

    async def decide(self, approval_id: str, approve: bool) -> Dict[str, Any]:
        """Apply the user's decision. Raises KeyError (unknown) or ValueError (not pending)."""
        record = self._approvals[approval_id]
        self._refresh_expiry(record)
        if record["status"] != "pending":
            raise ValueError(f"Approval is {record['status']}, not pending")
        if not approve:
            record["status"] = "denied"
            self.record("approval", record["tool_name"], "denied", "Denied by user", record["arguments"])
            return dict(record)

        # Consume before dispatch: from here on this approval can never run again.
        record["status"] = "executing"
        tool = self.registry.get(record["tool_name"])
        proposal = ToolCallProposal(tool_name=record["tool_name"], arguments=record["arguments"])
        ok_schema, schema_error = self._validate_schema(tool.parameters_schema, proposal.arguments) if tool else (False, "Unknown tool")
        if tool is None or not ok_schema or self.argument_digest(proposal.arguments) != record["args_digest"]:
            record["status"] = "failed"
            record["result"] = {"ok": False, "error": schema_error if tool else "Tool no longer registered"}
            self.record("approval", record["tool_name"], "failed", "Re-validation failed", record["arguments"])
            return dict(record)

        self.record("approval", record["tool_name"], "approved", "Approved by user for these exact arguments", record["arguments"])
        try:
            output = await tool.execute(proposal.arguments)
            verified, details = await tool.verify(proposal.arguments, output)
            record["status"] = "succeeded"
            record["result"] = {"ok": True, "verified": verified, "verification_details": details, "output": output}
            self.record("execution", record["tool_name"], "succeeded" if verified else "dispatched_unverified", details or "", record["arguments"])
        except TimeoutError as exc:
            # The action may or may not have happened; never retry automatically.
            record["status"] = "outcome_unknown"
            record["result"] = {"ok": False, "error": f"Timed out after dispatch: {exc}"}
            self.record("execution", record["tool_name"], "outcome_unknown", "Timeout after dispatch", record["arguments"])
        except Exception as exc:
            record["status"] = "failed"
            record["result"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            self.record("execution", record["tool_name"], "failed", type(exc).__name__, record["arguments"])
        return dict(record)

    @staticmethod
    def argument_digest(arguments: Dict[str, Any]) -> str:
        canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def record(self, kind: str, tool_name: str, outcome: str, reason: str = "", arguments: Optional[Dict[str, Any]] = None) -> None:
        """Append a redacted audit event."""
        self._audit_seq += 1
        self._audit.append({
            "seq": self._audit_seq,
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "tool": tool_name,
            "outcome": outcome,
            "reason": reason[:300],
            "args_digest": self.argument_digest(arguments) if arguments is not None else None,
        })

    def audit_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._audit)[-limit:][::-1]

    def consents(self) -> Dict[str, bool]:
        return {key: bool(getattr(self.session_policy, attr, False)) for key, (attr, _) in self.CONSENT_FIELDS.items()}

    def set_consent(self, key: str, enabled: bool) -> Dict[str, bool]:
        if key not in self.CONSENT_FIELDS:
            raise KeyError(key)
        attr, permission = self.CONSENT_FIELDS[key]
        setattr(self.session_policy, attr, enabled)
        if enabled:
            self.session_policy.allowed_permissions.add(permission)
        else:
            self.session_policy.allowed_permissions.discard(permission)
        self.record("consent", key, "granted" if enabled else "revoked", "Changed by user in the desktop UI")
        return self.consents()

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
                # bool is a subclass of int in Python, so it is excluded explicitly.
                if expected_type == "string" and not isinstance(val, str):
                    return False, f"Parameter '{key}' expected string, got {type(val).__name__}"
                elif expected_type == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
                    return False, f"Parameter '{key}' expected integer, got {type(val).__name__}"
                elif expected_type == "boolean" and not isinstance(val, bool):
                    return False, f"Parameter '{key}' expected boolean, got {type(val).__name__}"
                elif expected_type == "number" and (isinstance(val, bool) or not isinstance(val, (int, float))):
                    return False, f"Parameter '{key}' expected number, got {type(val).__name__}"
                if expected_type in ("integer", "number") and isinstance(val, (int, float)):
                    if "minimum" in prop_spec and val < prop_spec["minimum"]:
                        return False, f"Parameter '{key}' value {val} is below minimum {prop_spec['minimum']}"
                    if "maximum" in prop_spec and val > prop_spec["maximum"]:
                        return False, f"Parameter '{key}' value {val} exceeds maximum {prop_spec['maximum']}"
                if expected_type == "string" and isinstance(val, str) and "maxLength" in prop_spec:
                    if len(val) > prop_spec["maxLength"]:
                        return False, f"Parameter '{key}' exceeds maximum length {prop_spec['maxLength']}"

        return True, "Schema valid"

    def evaluate(self, proposal: ToolCallProposal) -> PolicyDecision:
        """Evaluate a proposal and record the decision in the redacted audit log."""
        decision = self._evaluate(proposal)
        self.record(
            "decision",
            proposal.tool_name,
            "allowed" if decision.allowed else "denied",
            decision.reason,
            proposal.arguments if isinstance(proposal.arguments, dict) else None,
        )
        return decision

    def _evaluate(self, proposal: ToolCallProposal) -> PolicyDecision:
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
            if tool.name in self.APPROVABLE_TOOLS:
                # Not executed. The user may approve this exact call from the UI.
                return PolicyDecision(
                    allowed=False,
                    requires_approval=True,
                    reason=(
                        f"Rejected: Session lacks required permission '{tool.required_permission.value}'. "
                        "The user can approve this exact action once from the W.E.D.N.E.S.D.A.Y. interface."
                    ),
                )
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

        if tool.name == "get_device_location":
            if not self.session_policy.location_read_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Rejected: Device location reading is disabled for this session."
                )

        if tool.required_permission == PermissionType.PLACES_SEARCH or tool.name in ("reverse_geocode", "search_nearby_places"):
            if not self.session_policy.places_search_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Rejected: Places search and geocoding is disabled for this session."
                )

        if tool.required_permission == PermissionType.WORLD_READ or tool.name in (
            "get_earthquakes", "get_weather", "get_natural_events", "get_disaster_alerts", "get_world_status"
        ):
            if not getattr(self.session_policy, "world_read_enabled", True):
                return PolicyDecision(
                    allowed=False,
                    reason="Rejected: World intelligence reading is disabled for this session."
                )
            if tool.name == "get_weather":
                lat = proposal.arguments.get("latitude")
                lng = proposal.arguments.get("longitude")
                if isinstance(lat, (int, float)) and not (-90.0 <= lat <= 90.0):
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Rejected: Latitude {lat} out of valid range [-90, 90]."
                    )
                if isinstance(lng, (int, float)) and not (-180.0 <= lng <= 180.0):
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Rejected: Longitude {lng} out of valid range [-180, 180]."
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
