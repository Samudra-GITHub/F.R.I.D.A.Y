"""Validation and signal measurement shared by every local speech-to-text engine."""

from typing import Any, Dict, Optional, Tuple

from backend.friday.voice import audio_dsp
from backend.friday.voice.audio_dsp import PcmClip
from schemas.contracts import STTTranscriptionResponse


def inspect_clip(
    audio_bytes: bytes,
    audio_format: str,
    settings: Any,
) -> Tuple[Optional[PcmClip], Dict[str, Any], Optional[STTTranscriptionResponse]]:
    """Return (clip, metric fields, early response). A non-None response means stop here."""
    payload_size = len(audio_bytes)
    max_bytes = getattr(settings, "max_audio_size_bytes", 10 * 1024 * 1024)
    if payload_size > max_bytes:
        return None, {}, STTTranscriptionResponse(
            status="transcription_error",
            audio_size_bytes=payload_size,
            details=f"Audio payload size ({payload_size} bytes) exceeds maximum limit ({max_bytes} bytes)",
        )
    if payload_size < 44:
        return None, {}, STTTranscriptionResponse(
            status="empty_transcript",
            audio_size_bytes=payload_size,
            details="Audio payload is empty or too short to contain audio data",
        )

    is_wav = audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"
    if not is_wav:
        return None, {}, STTTranscriptionResponse(
            status="format_unsupported",
            audio_size_bytes=payload_size,
            details=f"Audio format '{audio_format}' unsupported. The local engine requires 16-bit PCM WAV.",
        )

    try:
        clip = audio_dsp.decode_wav(audio_bytes)
    except ValueError as exc:
        return None, {}, STTTranscriptionResponse(
            status="format_unsupported", audio_size_bytes=payload_size, details=str(exc)
        )

    metrics = audio_dsp.measure(clip.samples)
    duration = audio_dsp.duration_seconds(clip.samples, clip.sample_rate)
    base: Dict[str, Any] = dict(
        duration_seconds=duration,
        detected_sample_rate=clip.sample_rate,
        detected_channels=clip.source_channels,
        audio_size_bytes=payload_size,
        peak_amplitude=metrics.peak,
        rms_amplitude=metrics.rms,
        silent_samples_ratio=metrics.silence_ratio,
        clipped_ratio=metrics.clipped_ratio,
        audio_samples_count=metrics.sample_count,
    )

    max_dur = getattr(settings, "max_audio_duration_seconds", 30)
    if duration is not None and duration > max_dur:
        return clip, base, STTTranscriptionResponse(
            status="transcription_error",
            details=f"Audio duration ({duration:.1f}s) exceeds maximum allowed limit ({max_dur}s)",
            **base,
        )
    if metrics.peak < 0.0015:
        return clip, base, STTTranscriptionResponse(
            status="empty_transcript",
            details="Recording contains only silence (peak below -56 dBFS). Check the selected microphone and its input level.",
            **base,
        )
    return clip, base, None
