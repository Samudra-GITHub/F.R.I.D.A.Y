"""Offline speech-to-text with faster-whisper (optional engine).

The model is loaded from a local directory only, so this provider can never download
weights or contact a network service. If the package or model is missing it reports
itself unavailable; the service does not silently substitute another engine.

Whisper exposes no calibrated confidence. ``confidence`` stays None rather than dressing
up a log-probability as a percentage.
"""

import importlib.util
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from backend.friday.config import get_settings
from backend.friday.voice import audio_dsp
from backend.friday.voice.base import BaseSTTProvider
from backend.friday.voice.preflight import inspect_clip
from schemas.contracts import STTTranscriptionResponse

logger = logging.getLogger(__name__)


class FasterWhisperProvider(BaseSTTProvider):
    def __init__(self, settings=None, model: Any = None) -> None:
        self._settings = settings or get_settings()
        self._model = model
        self._load_lock = threading.Lock()
        # Set once when the model loads, so the first result can say its time includes loading.
        self._pending_load_ms: Optional[int] = None

    @property
    def model_path(self) -> Path:
        return Path(self._settings.whisper_model_path)

    @property
    def engine_label(self) -> str:
        return f"faster-whisper {self.model_path.name.replace('faster-whisper-', '')} (CPU, int8)"

    def name(self) -> str:
        return "faster_whisper"

    def is_available(self) -> bool:
        if self._model is not None:
            return True
        return importlib.util.find_spec("faster_whisper") is not None and (self.model_path / "model.bin").is_file()

    def _load(self) -> Any:
        with self._load_lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                load_started = time.perf_counter()
                self._model = WhisperModel(
                    str(self.model_path),
                    device="cpu",
                    compute_type="int8",
                    local_files_only=True,
                )
                self._pending_load_ms = int((time.perf_counter() - load_started) * 1000)
            return self._model

    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        sample_rate_hz: int = 16000,
    ) -> STTTranscriptionResponse:
        started = time.perf_counter()
        clip, base, early = inspect_clip(audio_bytes, audio_format, self._settings)
        if early is not None:
            return early

        import numpy as np

        prepared = audio_dsp.resample(clip.samples, clip.sample_rate, audio_dsp.TARGET_RATE)
        base["speech_duration_seconds"] = audio_dsp.duration_seconds(
            audio_dsp.trim_silence(prepared, audio_dsp.TARGET_RATE), audio_dsp.TARGET_RATE
        )
        audio = np.frombuffer(prepared.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
        ms = lambda: int((time.perf_counter() - started) * 1000)

        try:
            segments, _info = self._load().transcribe(
                audio,
                language="en",
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            # The generator does the actual decoding, so it must be consumed inside the try.
            parts = [s for s in segments if s.text.strip()]
        except Exception as exc:
            logger.warning("faster-whisper failed: %s", type(exc).__name__)
            return STTTranscriptionResponse(
                status="transcription_error",
                engine=self.engine_label,
                latency_ms=ms(),
                details=f"Speech recognition error: {type(exc).__name__}: {exc}",
                **base,
            )

        load_ms, self._pending_load_ms = self._pending_load_ms, None
        load_note = f" This first run includes {load_ms} ms of model loading." if load_ms is not None else ""

        if not parts:
            return STTTranscriptionResponse(
                status="empty_transcript",
                engine=self.engine_label,
                segment_count=0,
                latency_ms=ms(),
                details=f"The recognizer found no speech in this recording.{load_note}",
                **base,
            )
        return STTTranscriptionResponse(
            status="ok",
            transcript=" ".join(s.text.strip() for s in parts),
            confidence=None,
            engine=self.engine_label,
            segment_count=len(parts),
            latency_ms=ms(),
            details=f"Recognized {len(parts)} segment(s) locally. This engine reports no confidence score.{load_note}",
            **base,
        )
