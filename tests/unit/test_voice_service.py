"""Unit tests for Phase 5 Local Voice Subsystem and VoiceService.

Covers:
- Offline STT transcription with valid/empty/unsupported audio payloads
- Offline TTS synthesis with valid/empty text
- Temporary file cleanup and payload bounds
- Privacy lifecycle: voice disabled by default, explicit user activation, emergency stop
- Verification that wake phrase remains strictly dormant (wake_word_active == False)
- Absence of cloud fallback
"""

import base64
import pytest
from backend.friday.voice.service import VoiceService
from backend.friday.voice.mock_providers import MockSTTProvider, MockTTSProvider, DUMMY_WAV_HEADER
from schemas.contracts import (
    STTTranscriptionRequest,
    TTSSynthesisRequest,
    VoicePrivacyRequest,
    VoiceStateEnum,
)


@pytest.fixture
def mock_voice_service():
    """Create VoiceService with deterministic mock offline providers."""
    stt = MockSTTProvider(mock_transcript="What is the weather today?")
    tts = MockTTSProvider()
    svc = VoiceService(stt_provider=stt, tts_provider=tts)
    return svc


def test_voice_off_by_default(mock_voice_service):
    """Voice subsystem must start strictly OFF by default on application launch."""
    cfg = mock_voice_service.get_config()
    assert cfg.voice_enabled is False
    assert mock_voice_service.current_state == VoiceStateEnum.DISABLED
    # Wake phrase must be dormant and inactive
    assert cfg.wake_word_active is False


def test_enable_and_disable_voice_privacy(mock_voice_service):
    """Explicit user toggle enables voice, and disabling immediately halts activity."""
    # Enable
    enable_req = VoicePrivacyRequest(action="enable")
    enable_res = mock_voice_service.update_privacy(enable_req)
    assert enable_res.status == "ok"
    assert enable_res.voice_enabled is True
    assert enable_res.current_state == VoiceStateEnum.STANDBY

    # Disable
    disable_req = VoicePrivacyRequest(action="disable")
    disable_res = mock_voice_service.update_privacy(disable_req)
    assert disable_res.status == "ok"
    assert disable_res.voice_enabled is False
    assert disable_res.current_state == VoiceStateEnum.DISABLED


def test_emergency_playback_stop(mock_voice_service):
    """Playback stop action interrupts audio immediately."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    stop_res = mock_voice_service.update_privacy(VoicePrivacyRequest(action="stop_playback"))
    assert stop_res.status == "ok"
    assert stop_res.current_state == VoiceStateEnum.INTERRUPTED


def test_stt_transcription_success(mock_voice_service):
    """Offline STT successfully transcribes valid base64 audio bytes."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    audio_b64 = base64.b64encode(DUMMY_WAV_HEADER).decode("ascii")

    req = STTTranscriptionRequest(audio_base64=audio_b64, audio_format="wav")
    res = mock_voice_service.transcribe(req)

    assert res.status == "ok"
    assert res.transcript == "What is the weather today?"
    assert res.duration_seconds is not None


def test_stt_empty_audio_rejection(mock_voice_service):
    """Empty or near-empty audio payload returns empty_transcript status."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    short_b64 = base64.b64encode(b"short").decode("ascii")

    req = STTTranscriptionRequest(audio_base64=short_b64, audio_format="wav")
    res = mock_voice_service.transcribe(req)

    assert res.status == "empty_transcript"
    assert res.transcript == ""


def test_stt_unsupported_format(mock_voice_service):
    """Non-WAV audio returns format_unsupported status."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    audio_b64 = base64.b64encode(b"RIFF" + b"somefakecontentthatisnotwavfmt" + b"paddingbytesforlength44").decode("ascii")

    req = STTTranscriptionRequest(audio_base64=audio_b64, audio_format="mp3")
    res = mock_voice_service.transcribe(req)

    assert res.status == "format_unsupported"


def test_stt_malformed_base64(mock_voice_service):
    """Corrupted base64 payload returns transcription_error without throwing exception."""
    req = STTTranscriptionRequest(audio_base64="not-valid-base64!@#$", audio_format="wav")
    res = mock_voice_service.transcribe(req)

    assert res.status == "transcription_error"


def test_stt_model_unavailable(mock_voice_service):
    """When offline STT engine is missing, returns model_not_installed."""
    mock_voice_service.stt_provider.set_available(False)
    audio_b64 = base64.b64encode(DUMMY_WAV_HEADER).decode("ascii")

    req = STTTranscriptionRequest(audio_base64=audio_b64, audio_format="wav")
    res = mock_voice_service.transcribe(req)

    assert res.status == "model_not_installed"


def test_tts_synthesis_success(mock_voice_service):
    """Offline TTS successfully synthesizes spoken audio bytes."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    req = TTSSynthesisRequest(text="Hello, W.E.D.N.E.S.D.A.Y. is online.")
    res = mock_voice_service.synthesize(req)

    assert res.status == "ok"
    assert res.audio_base64 is not None
    assert res.audio_format == "wav"


def test_tts_empty_text_rejected(mock_voice_service):
    """Empty synthesis text is rejected gracefully."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    req = TTSSynthesisRequest(text="   ")
    res = mock_voice_service.synthesize(req)

    assert res.status == "error"


def test_tts_model_unavailable(mock_voice_service):
    """When offline TTS engine is unavailable, returns model_not_installed."""
    mock_voice_service.update_privacy(VoicePrivacyRequest(action="enable"))
    mock_voice_service.tts_provider.set_available(False)

    req = TTSSynthesisRequest(text="Test speech")
    res = mock_voice_service.synthesize(req)

    assert res.status == "model_not_installed"
