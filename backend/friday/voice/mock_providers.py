"""Mock local speech providers for deterministic offline testing."""

import base64
from typing import List, Optional

from backend.friday.voice.base import BaseSTTProvider, BaseTTSProvider
from schemas.contracts import STTTranscriptionResponse, TTSSynthesisResponse


# Minimal valid 44-byte RIFF WAV header for testing
DUMMY_WAV_HEADER = (
    b"RIFF\x2c\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x08\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00"
)


class MockSTTProvider(BaseSTTProvider):
    """Deterministic STT provider for automated test suites."""

    def __init__(self, mock_transcript: str = "What is the weather in Tokyo?"):
        self.mock_transcript = mock_transcript
        self._available = True

    def name(self) -> str:
        return "mock_stt"

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        sample_rate_hz: int = 16000,
    ) -> STTTranscriptionResponse:
        if not self._available:
            return STTTranscriptionResponse(
                status="model_not_installed",
                transcript="",
                details="Mock STT engine unavailable",
            )

        if len(audio_bytes) < 44:
            return STTTranscriptionResponse(
                status="empty_transcript",
                transcript="",
                details="Audio too short or empty",
            )

        fmt = audio_format.lower()
        if fmt not in ("wav", "wave"):
            return STTTranscriptionResponse(
                status="format_unsupported",
                transcript="",
                details=f"Audio format '{audio_format}' unsupported",
            )

        return STTTranscriptionResponse(
            status="ok",
            transcript=self.mock_transcript,
            duration_seconds=1.5,
            details="Mock transcription successful",
        )


class MockTTSProvider(BaseTTSProvider):
    """Deterministic TTS provider for automated test suites."""

    def __init__(self):
        self._available = True
        self.voices = ["MockVoice Alice", "MockVoice Bob"]

    def name(self) -> str:
        return "mock_tts"

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def get_available_voices(self) -> List[str]:
        return list(self.voices)

    def synthesize(
        self,
        text: str,
        voice_name: Optional[str] = None,
    ) -> TTSSynthesisResponse:
        if not self._available:
            return TTSSynthesisResponse(
                status="model_not_installed",
                details="Mock TTS engine unavailable",
            )

        trimmed = (text or "").strip()
        if not trimmed:
            return TTSSynthesisResponse(
                status="error",
                details="Input text is empty",
            )

        audio_b64 = base64.b64encode(DUMMY_WAV_HEADER).decode("ascii")
        return TTSSynthesisResponse(
            status="ok",
            audio_base64=audio_b64,
            audio_format="wav",
            duration_seconds=1.0,
            details="Mock synthesis successful",
        )
