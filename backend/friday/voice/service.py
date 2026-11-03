"""Voice interaction service for W.E.D.N.E.S.D.A.Y.

Coordinates offline STT, offline TTS, privacy posture, and audio lifecycle.
Enforces strict local execution: zero cloud calls, zero ambient recording.
"""

import base64
import logging
import threading
from typing import Dict, Optional

from backend.friday.config import Settings, get_settings
from backend.friday.voice.base import BaseSTTProvider, BaseTTSProvider
from backend.friday.voice.whisper_provider import FasterWhisperProvider
from backend.friday.voice.windows_speech import WindowsSpeechProvider
from schemas.contracts import (
    STTTranscriptionRequest,
    STTTranscriptionResponse,
    TTSSynthesisRequest,
    TTSSynthesisResponse,
    VoiceConfigResponse,
    VoicePrivacyRequest,
    VoicePrivacyResponse,
    VoiceStateEnum,
)

logger = logging.getLogger(__name__)

# Each recognition/synthesis spawns a PowerShell + SAPI process. Bound concurrency so a
# burst of requests queues instead of saturating the CPU.
_ENGINE_SLOTS = threading.BoundedSemaphore(2)


class VoiceService:
    """Service managing offline voice transcription, speech synthesis, and privacy state."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        stt_provider: Optional[BaseSTTProvider] = None,
        tts_provider: Optional[BaseTTSProvider] = None,
    ):
        self._settings = settings or get_settings()

        # Offline providers
        default_provider = WindowsSpeechProvider(self._settings)
        self.tts_provider: BaseTTSProvider = tts_provider or default_provider
        if stt_provider is not None:
            self.stt_engines: Dict[str, BaseSTTProvider] = {stt_provider.name(): stt_provider}
            self.stt_provider: BaseSTTProvider = stt_provider
        else:
            self.stt_engines = {
                "windows_sapi": default_provider,
                "faster_whisper": FasterWhisperProvider(self._settings),
            }
            configured = getattr(self._settings, "stt_provider", "windows_sapi")
            if configured not in self.stt_engines:
                logger.warning("Unknown FRIDAY_STT_PROVIDER '%s'; using windows_sapi", configured)
            self.stt_provider = self.stt_engines.get(configured, default_provider)

        # Privacy posture: voice is OFF by default on startup
        self.voice_enabled: bool = getattr(self._settings, "voice_enabled", False)
        self.voice_output_enabled: bool = True
        self.current_state: VoiceStateEnum = (
            VoiceStateEnum.STANDBY if self.voice_enabled else VoiceStateEnum.DISABLED
        )
        self._active_playback_id: Optional[str] = None

    def get_config(self) -> VoiceConfigResponse:
        """Return current voice configuration, engine status, and privacy settings."""
        stt_avail = self.stt_provider.is_available()
        tts_avail = self.tts_provider.is_available()

        voices = []
        if tts_avail:
            try:
                voices = self.tts_provider.get_available_voices()
            except Exception as e:
                logger.warning(f"Failed to list voices: {e}")

        speech_packs = []
        # Windows language packs are listed even when another engine is the default.
        pack_source = self.stt_engines.get("windows_sapi", self.stt_provider)
        if hasattr(pack_source, "get_installed_recognizers"):
            try:
                speech_packs = pack_source.get_installed_recognizers()
            except Exception as e:
                logger.warning(f"Failed to list speech packs: {e}")

        return VoiceConfigResponse(
            voice_enabled=self.voice_enabled,
            stt_available=stt_avail,
            tts_available=tts_avail,
            stt_engine=self.stt_provider.name(),
            tts_engine=self.tts_provider.name(),
            available_voices=voices,
            available_stt_engines=[n for n, p in self.stt_engines.items() if p.is_available()],
            installed_speech_packs=speech_packs,
            wake_word_active=False,  # Wake phrase is strictly inactive/dormant
        )

    def update_privacy(self, request: VoicePrivacyRequest) -> VoicePrivacyResponse:
        """Update voice privacy settings or trigger playback stop."""
        action = request.action.lower().strip()

        if action == "enable":
            self.voice_enabled = True
            self.current_state = VoiceStateEnum.STANDBY
            return VoicePrivacyResponse(
                status="ok",
                voice_enabled=True,
                current_state=VoiceStateEnum.STANDBY,
                details="Local voice mode enabled by user",
            )
        elif action == "disable":
            self.voice_enabled = False
            self.stop_playback()
            self.current_state = VoiceStateEnum.DISABLED
            return VoicePrivacyResponse(
                status="ok",
                voice_enabled=False,
                current_state=VoiceStateEnum.DISABLED,
                details="Local voice mode disabled; recording and playback stopped",
            )
        elif action in ("stop_playback", "stop", "interrupt"):
            self.stop_playback()
            self.current_state = (
                VoiceStateEnum.INTERRUPTED if self.voice_enabled else VoiceStateEnum.DISABLED
            )
            return VoicePrivacyResponse(
                status="ok",
                voice_enabled=self.voice_enabled,
                current_state=self.current_state,
                details="Audio playback interrupted",
            )
        else:
            return VoicePrivacyResponse(
                status="error",
                voice_enabled=self.voice_enabled,
                current_state=self.current_state,
                details=f"Unrecognized voice privacy action: '{request.action}'",
            )

    def stop_playback(self) -> None:
        """Interrupt and cancel any active speech playback."""
        self._active_playback_id = None
        if self.voice_enabled and self.current_state == VoiceStateEnum.SPEAKING:
            self.current_state = VoiceStateEnum.STANDBY

    def transcribe(self, request: STTTranscriptionRequest) -> STTTranscriptionResponse:
        """Process push-to-talk audio bytes with local STT.
        
        Validates payload, enforces privacy, and cleans up temporary resources.
        """
        # Validate base64 audio
        try:
            audio_bytes = base64.b64decode(request.audio_base64)
        except Exception as exc:
            return STTTranscriptionResponse(
                status="transcription_error",
                transcript="",
                details=f"Malformed base64 audio data: {exc}",
            )

        # An unavailable engine is reported, never silently swapped for another one.
        provider = self.stt_engines.get(request.engine) if request.engine else self.stt_provider
        if provider is None or not provider.is_available():
            return STTTranscriptionResponse(
                status="model_not_installed",
                transcript="",
                details=(
                    f"Local speech-to-text engine '{request.engine}' is not available on this system"
                    if request.engine
                    else "Local speech-to-text provider is unavailable on this system"
                ),
            )

        self.current_state = VoiceStateEnum.THINKING
        try:
            with _ENGINE_SLOTS:
                resp = provider.transcribe(
                    audio_bytes=audio_bytes,
                    audio_format=request.audio_format,
                    sample_rate_hz=request.sample_rate_hz,
                )
            return resp
        finally:
            self.current_state = (
                VoiceStateEnum.STANDBY if self.voice_enabled else VoiceStateEnum.DISABLED
            )

    def synthesize(self, request: TTSSynthesisRequest) -> TTSSynthesisResponse:
        """Synthesize assistant response text into spoken audio offline."""
        if not self.voice_enabled and not self.voice_output_enabled:
            return TTSSynthesisResponse(
                status="disabled",
                details="Voice output is currently disabled",
            )

        if not self.tts_provider.is_available():
            return TTSSynthesisResponse(
                status="model_not_installed",
                details="Local text-to-speech engine is unavailable on this system",
            )

        self.current_state = VoiceStateEnum.SPEAKING
        try:
            with _ENGINE_SLOTS:
                resp = self.tts_provider.synthesize(
                    text=request.text,
                    voice_name=request.voice_name,
                )
            return resp
        finally:
            self.current_state = (
                VoiceStateEnum.STANDBY if self.voice_enabled else VoiceStateEnum.DISABLED
            )
