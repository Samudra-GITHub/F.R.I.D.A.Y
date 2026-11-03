"""Integration tests for Phase 4 & Phase 5 API endpoints through ASGI transport."""

import base64
import pytest
import httpx
from backend.friday.api.app import app
from backend.friday.api.voice_router import set_voice_service
from backend.friday.voice.service import VoiceService
from backend.friday.voice.mock_providers import MockSTTProvider, MockTTSProvider, DUMMY_WAV_HEADER


@pytest.fixture(autouse=True)
def setup_mock_voice_service():
    """Install mock voice service into API router for deterministic integration tests."""
    mock_svc = VoiceService(
        stt_provider=MockSTTProvider(mock_transcript="Tokyo earthquake report"),
        tts_provider=MockTTSProvider(),
    )
    mock_svc.update_privacy(type("Obj", (), {"action": "enable"})())
    set_voice_service(mock_svc)
    yield mock_svc


@pytest.mark.asyncio
async def test_api_chat_root_and_proxied_paths():
    """Verify both /chat and /api/chat paths respond with ConversationResponse."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        # Direct /chat
        res1 = await client.post("/chat", json={"message": "What is the time?"})
        assert res1.status_code == 200
        data1 = res1.json()
        assert "response" in data1
        assert "model" in data1
        assert "sources" in data1
        assert "tool_calls" in data1

        # Proxied /api/chat
        res2 = await client.post("/api/chat", json={"message": "Hello"})
        assert res2.status_code == 200
        data2 = res2.json()
        assert "response" in data2
        assert "sources" in data2


@pytest.mark.asyncio
async def test_api_chat_reset_endpoints():
    """Verify /chat/reset and /api/chat/reset paths clear conversation history."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        res1 = await client.post("/chat/reset", json={"conversation_id": "test-session-1"})
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "ok"
        assert data1["conversation_id"] == "test-session-1"

        res2 = await client.post("/api/chat/reset", json={})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "ok"


@pytest.mark.asyncio
async def test_api_voice_config_and_privacy():
    """Verify /voice/config and /voice/privacy endpoints under both root and /api prefixes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        # GET config
        res = await client.get("/api/voice/config")
        assert res.status_code == 200
        cfg = res.json()
        assert "voice_enabled" in cfg
        assert "stt_available" in cfg
        assert "tts_available" in cfg
        assert cfg["wake_word_active"] is False  # Inactive by design

        # POST privacy toggle
        res_priv = await client.post("/api/voice/privacy", json={"action": "disable"})
        assert res_priv.status_code == 200
        priv_data = res_priv.json()
        assert priv_data["status"] == "ok"
        assert priv_data["voice_enabled"] is False
        assert priv_data["current_state"] == "DISABLED"


@pytest.mark.asyncio
async def test_api_voice_transcribe_and_synthesize():
    """Verify offline STT transcription and TTS synthesis via API."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000"
    ) as client:
        # Transcribe
        audio_b64 = base64.b64encode(DUMMY_WAV_HEADER).decode("ascii")
        res_stt = await client.post(
            "/api/voice/transcribe",
            json={"audio_base64": audio_b64, "audio_format": "wav"},
        )
        assert res_stt.status_code == 200
        stt_data = res_stt.json()
        assert stt_data["status"] == "ok"
        assert stt_data["transcript"] == "Tokyo earthquake report"

        # Synthesize
        res_tts = await client.post(
            "/api/voice/synthesize",
            json={"text": "Tokyo recorded a magnitude 5.2 earthquake."},
        )
        assert res_tts.status_code == 200
        tts_data = res_tts.json()
        assert tts_data["status"] == "ok"
        assert "audio_base64" in tts_data
        assert tts_data["audio_format"] == "wav"
