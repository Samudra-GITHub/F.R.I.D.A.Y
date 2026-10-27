"""Tool for querying the host local date and time."""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from schemas.contracts import PermissionType
from backend.friday.tools.base import BaseTool


class GetLocalTimeTool(BaseTool):
    name = "get_local_time"
    description = "Return the host's current local date, time, and timezone in ISO-8601 format."
    required_permission = PermissionType.SYSTEM_TIME
    parameters_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    async def execute(self, arguments: Dict[str, Any]) -> str:
        # Ignore any unsolicited arguments
        return datetime.now().astimezone().isoformat()

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        try:
            datetime.fromisoformat(str(raw_output))
            return True, "Deterministic host time retrieved."
        except Exception as exc:
            return False, f"Failed to verify ISO-8601 format: {exc}"
