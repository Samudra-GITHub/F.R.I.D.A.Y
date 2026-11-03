"""Abstract base interfaces for local Speech-to-Text and Text-to-Speech providers."""

from abc import ABC, abstractmethod
from typing import List, Optional

from schemas.contracts import STTTranscriptionResponse, TTSSynthesisResponse


class BaseSTTProvider(ABC):
    """Abstract interface for local speech-to-text recognition."""

    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the local speech engine and required models are installed."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        sample_rate_hz: int = 16000,
    ) -> STTTranscriptionResponse:
        """Transcribe local audio bytes to text offline.
        
        Must never send audio to remote/cloud APIs.
        Must clean up temporary files immediately upon completion or error.
        """
        pass


class BaseTTSProvider(ABC):
    """Abstract interface for local text-to-speech synthesis."""

    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the local synthesis engine is available."""
        pass

    @abstractmethod
    def get_available_voices(self) -> List[str]:
        """Return list of installed offline voice profiles."""
        pass

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_name: Optional[str] = None,
    ) -> TTSSynthesisResponse:
        """Synthesize text into offline WAV audio bytes.
        
        Must never use cloud TTS.
        Must bound text length and execution time.
        Must clean up temporary files immediately.
        """
        pass
