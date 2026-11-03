"""Voice API Router for W.E.D.N.E.S.D.A.Y.

Routes are plain ``def`` so FastAPI runs them in its threadpool: recognition and
synthesis call blocking subprocesses and must not stall the event loop.

Exposes local, offline endpoints for Speech-to-Text, Text-to-Speech, and voice privacy controls.
Zero cloud network calls.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.friday.voice.service import VoiceService
from schemas.contracts import (
    STTTranscriptionRequest,
    STTTranscriptionResponse,
    TTSSynthesisRequest,
    TTSSynthesisResponse,
    VoiceConfigResponse,
    VoicePrivacyRequest,
    VoicePrivacyResponse,
)

# Global or dependency-injected voice service instance
_voice_service: VoiceService | None = None


def get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service


def set_voice_service(svc: VoiceService) -> None:
    global _voice_service
    _voice_service = svc


router = APIRouter(tags=["Voice"])


@router.get("/voice/config", response_model=VoiceConfigResponse)
def get_voice_config(service: VoiceService = Depends(get_voice_service)) -> VoiceConfigResponse:
    """Retrieve voice status, installed offline engines, and privacy posture."""
    return service.get_config()


@router.post("/voice/privacy", response_model=VoicePrivacyResponse)
def update_voice_privacy(
    request: VoicePrivacyRequest,
    service: VoiceService = Depends(get_voice_service),
) -> VoicePrivacyResponse:
    """Update voice enablement state or trigger emergency playback stop."""
    return service.update_privacy(request)


@router.post("/voice/transcribe", response_model=STTTranscriptionResponse)
def transcribe_audio(
    request: STTTranscriptionRequest,
    service: VoiceService = Depends(get_voice_service),
) -> STTTranscriptionResponse:
    """Transcribe push-to-talk audio bytes locally and offline."""
    return service.transcribe(request)


@router.post("/voice/synthesize", response_model=TTSSynthesisResponse)
def synthesize_speech(
    request: TTSSynthesisRequest,
    service: VoiceService = Depends(get_voice_service),
) -> TTSSynthesisResponse:
    """Synthesize text into offline WAV audio bytes."""
    return service.synthesize(request)
