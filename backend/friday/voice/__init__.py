"""W.E.D.N.E.S.D.A.Y. Voice Subsystem.

Privacy-first local speech-to-text (STT) and text-to-speech (TTS) interfaces.
Zero cloud fallbacks; audio never leaves the user's local machine.
"""

from backend.friday.voice.base import BaseSTTProvider, BaseTTSProvider
from backend.friday.voice.service import VoiceService

__all__ = ["BaseSTTProvider", "BaseTTSProvider", "VoiceService"]
