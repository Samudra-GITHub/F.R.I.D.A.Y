"""faster-whisper provider and engine selection, using a fake model so no weights are needed."""

import array
import base64
import math
from types import SimpleNamespace

import pytest

from backend.friday.voice import audio_dsp
from backend.friday.voice.base import BaseSTTProvider
from backend.friday.voice.service import VoiceService
from backend.friday.voice.whisper_provider import FasterWhisperProvider
from schemas.contracts import STTTranscriptionRequest, STTTranscriptionResponse

SETTINGS = SimpleNamespace(
    whisper_model_path="does/not/exist/faster-whisper-base.en",
    max_audio_size_bytes=10 * 1024 * 1024,
    max_audio_duration_seconds=30,
)


def tone_wav(seconds=0.5, rate=48000, amp=0.5) -> bytes:
    n = int(rate * seconds)
    return audio_dsp.encode_wav(array.array("h", (int(amp * 32767 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n))), rate)


class FakeModel:
    def __init__(self, texts=(" Hey Wednesday, what time is it? ",), error=None):
        self.texts, self.error, self.calls = texts, error, []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        if self.error:
            raise self.error

        def generate():
            for text in self.texts:
                yield SimpleNamespace(text=text)

        return generate(), SimpleNamespace(language="en")


def provider(**kw):
    return FasterWhisperProvider(SETTINGS, model=FakeModel(**kw))


def test_transcribes_with_16khz_float_audio_and_invents_no_confidence():
    p = provider()
    res = p.transcribe(tone_wav())
    assert res.status == "ok"
    assert res.transcript == "Hey Wednesday, what time is it?"
    assert res.confidence is None, "Whisper has no calibrated confidence; none may be fabricated"
    assert res.segment_count == 1 and res.latency_ms is not None
    assert res.detected_sample_rate == 48000 and res.peak_amplitude == pytest.approx(0.5, abs=0.01)
    audio, kwargs = p._model.calls[0]
    assert audio.dtype.name == "float32" and abs(len(audio) - 8000) <= 1
    assert float(abs(audio).max()) <= 1.0
    assert kwargs["language"] == "en" and kwargs["vad_filter"] is True


def test_no_speech_is_empty_not_ok():
    res = provider(texts=("   ",)).transcribe(tone_wav())
    assert res.status == "empty_transcript" and res.transcript == ""


def test_decoding_failure_during_generation_is_reported_as_an_error():
    class FailsWhileDecoding(FakeModel):
        def transcribe(self, audio, **kwargs):
            def generate():
                raise RuntimeError("decoder crashed")
                yield

            return generate(), None

    res = FasterWhisperProvider(SETTINGS, model=FailsWhileDecoding()).transcribe(tone_wav())
    assert res.status == "transcription_error" and "decoder crashed" in res.details


def test_exception_is_not_success():
    res = provider(error=ValueError("bad")).transcribe(tone_wav())
    assert res.status == "transcription_error" and res.transcript == ""


def test_preflight_stops_silence_and_non_wav_before_the_model_runs():
    p = provider()
    silent = audio_dsp.encode_wav(array.array("h", [0] * 8000), 16000)
    assert p.transcribe(silent).status == "empty_transcript"
    assert p.transcribe(b"x" * 100).status == "format_unsupported"
    assert p._model.calls == []


def test_unavailable_without_model_files():
    assert FasterWhisperProvider(SETTINGS).is_available() is False


def test_loads_from_local_path_only_and_discloses_load_time(monkeypatch, tmp_path):
    pytest.importorskip("faster_whisper")
    created = {}

    class Recorder(FakeModel):
        def __init__(self, path, **kwargs):
            super().__init__()
            created.update(path=path, **kwargs)

    monkeypatch.setattr("faster_whisper.WhisperModel", Recorder)
    p = FasterWhisperProvider(SimpleNamespace(**{**vars(SETTINGS), "whisper_model_path": str(tmp_path)}))
    first = p.transcribe(tone_wav())
    second = p.transcribe(tone_wav())
    assert created["path"] == str(tmp_path) and created["local_files_only"] is True
    assert created["device"] == "cpu" and created["compute_type"] == "int8"
    assert "model loading" in first.details and "model loading" not in second.details


class NamedEngine(BaseSTTProvider):
    def __init__(self, engine_name, available=True):
        self.engine_name, self.available, self.calls = engine_name, available, 0

    def name(self):
        return self.engine_name

    def is_available(self):
        return self.available

    def transcribe(self, audio_bytes, audio_format="wav", sample_rate_hz=16000):
        self.calls += 1
        return STTTranscriptionResponse(status="ok", transcript=self.engine_name, engine=self.engine_name)


@pytest.fixture
def engines():
    svc = VoiceService(settings=SimpleNamespace(voice_enabled=False, stt_provider="windows_sapi"))
    sapi, whisper = NamedEngine("windows_sapi"), NamedEngine("faster_whisper")
    svc.stt_engines = {"windows_sapi": sapi, "faster_whisper": whisper}
    svc.stt_provider = sapi
    return svc, sapi, whisper


AUDIO = base64.b64encode(tone_wav(0.1)).decode()


def test_request_picks_the_named_engine_and_default_stays_sapi(engines):
    svc, sapi, whisper = engines
    assert svc.transcribe(STTTranscriptionRequest(audio_base64=AUDIO)).transcript == "windows_sapi"
    assert svc.transcribe(STTTranscriptionRequest(audio_base64=AUDIO, engine="faster_whisper")).transcript == "faster_whisper"
    assert (sapi.calls, whisper.calls) == (1, 1)


@pytest.mark.parametrize("engine", ["cloud_whisper", "faster_whisper_unavailable"])
def test_unknown_or_unavailable_engine_never_substitutes(engines, engine):
    svc, sapi, whisper = engines
    svc.stt_engines["faster_whisper_unavailable"] = NamedEngine("faster_whisper_unavailable", available=False)
    res = svc.transcribe(STTTranscriptionRequest(audio_base64=AUDIO, engine=engine))
    assert res.status == "model_not_installed" and engine in res.details
    assert (sapi.calls, whisper.calls) == (0, 0)


def test_config_lists_only_engines_that_can_run(engines):
    svc, _, whisper = engines
    svc.tts_provider = NamedTTS()
    assert svc.get_config().available_stt_engines == ["windows_sapi", "faster_whisper"]
    whisper.available = False
    assert svc.get_config().available_stt_engines == ["windows_sapi"]


class NamedTTS:
    def name(self):
        return "fake_tts"

    def is_available(self):
        return False
