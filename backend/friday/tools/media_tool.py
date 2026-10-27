"""Windows Media Control Tool using direct Win32 virtual key dispatch.

Strictly avoids arbitrary shell execution. In compliance with security and honesty
requirements, playback state verification is marked unverified because Windows media
keys are dispatch-only without active WinRT SMTC session hooks.
"""

import sys
import ctypes
from typing import Any, Dict, Optional, Set, Tuple
from schemas.contracts import PermissionType
from backend.friday.tools.base import BaseTool

# Win32 Virtual Key Codes for Media
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


class ControlMediaTool(BaseTool):
    """Tool for controlling media playback on Windows via standard media key codes."""
    name = "control_media"
    description = (
        "Send a media control command to the active desktop media player. "
        "Allowed actions: 'play', 'pause', 'play_pause', 'next', 'previous'."
    )
    required_permission = PermissionType.MEDIA_CONTROL
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play", "pause", "play_pause", "next", "previous"],
                "description": "The playback action to trigger."
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    ALLOWED_ACTIONS: Set[str] = {"play", "pause", "play_pause", "next", "previous"}

    def _send_win32_media_key(self, vk_code: int) -> None:
        """Dispatch a virtual key press and release without using any shell process."""
        if sys.platform != "win32":
            raise NotImplementedError("Media control is currently implemented for Windows only.")
        
        user32 = ctypes.windll.user32
        # Key down
        user32.keybd_event(vk_code, 0, 0, 0)
        # Key up
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action", "")).lower().strip()
        if action not in self.ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported media action '{action}'. Allowed: {sorted(list(self.ALLOWED_ACTIONS))}")

        # Map actions to Win32 key codes
        if action in ("play", "pause", "play_pause"):
            vk_code = VK_MEDIA_PLAY_PAUSE
        elif action == "next":
            vk_code = VK_MEDIA_NEXT_TRACK
        elif action == "previous":
            vk_code = VK_MEDIA_PREV_TRACK
        else:
            raise ValueError(f"Unmapped action '{action}'")

        self._send_win32_media_key(vk_code)

        return {
            "action": action,
            "dispatched": True,
            "transport": "win32_keybd_event",
            "notice": "Media key dispatched to Windows system bus."
        }

    async def verify(self, arguments: Dict[str, Any], raw_output: Any) -> Tuple[bool, Optional[str]]:
        """Report honest verification limitation.
        
        Windows virtual key dispatch does not return playback state feedback.
        Per the F.R.I.D.A.Y. engineering blueprint, we never claim verified success
        without an independent state check.
        """
        return False, (
            "Windows media playback state cannot be verified without native WinRT SMTC "
            "session hooks; keystroke was dispatched without state confirmation."
        )
