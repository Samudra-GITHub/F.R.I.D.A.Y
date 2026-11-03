"""Pure-Python PCM helpers for the local voice pipeline.

Replaces the deprecated ``audioop`` module (removed in Python 3.13). All functions
operate on signed 16-bit little-endian mono/stereo PCM and never touch the network.
"""

import array
import io
import math
import sys
import wave
from dataclasses import dataclass
from typing import Optional

TARGET_RATE = 16000
SILENCE_THRESHOLD = 200  # |sample| below this (~ -44 dBFS) counts as silent


@dataclass
class PcmClip:
    samples: array.array  # signed 16-bit mono
    sample_rate: int
    source_channels: int
    source_sample_width: int


@dataclass
class SignalMetrics:
    peak: float
    rms: float
    silence_ratio: float
    clipped_ratio: float
    sample_count: int


def _as_int16(raw: bytes) -> array.array:
    data = array.array("h")
    data.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if sys.byteorder != "little":
        data.byteswap()
    return data


def decode_wav(audio_bytes: bytes) -> PcmClip:
    """Decode a PCM WAV payload into 16-bit mono samples. Raises ``ValueError`` when unsupported."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid WAV payload: {exc}") from exc

    if width != 2:
        raise ValueError(f"Unsupported sample width {width * 8}-bit; 16-bit PCM is required")
    if channels not in (1, 2):
        raise ValueError(f"Unsupported channel count {channels}")
    if rate <= 0:
        raise ValueError("WAV header declares an invalid sample rate")

    samples = _as_int16(raw)
    if channels == 2:
        samples = array.array("h", ((samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)))
    return PcmClip(samples=samples, sample_rate=rate, source_channels=channels, source_sample_width=width)


def measure(samples: array.array) -> SignalMetrics:
    n = len(samples)
    if n == 0:
        return SignalMetrics(0.0, 0.0, 1.0, 0.0, 0)
    peak = max(abs(min(samples)), max(samples))
    sum_sq = math.fsum(s * s for s in samples)
    silent = sum(1 for s in samples if -SILENCE_THRESHOLD < s < SILENCE_THRESHOLD)
    clipped = sum(1 for s in samples if s >= 32700 or s <= -32700)
    return SignalMetrics(
        peak=round(min(peak, 32767) / 32767.0, 4),
        rms=round(math.sqrt(sum_sq / n) / 32767.0, 4),
        silence_ratio=round(silent / n, 3),
        clipped_ratio=round(clipped / n, 4),
        sample_count=n,
    )


def resample(samples: array.array, src_rate: int, dst_rate: int = TARGET_RATE) -> array.array:
    """Linear-interpolation resampler, preceded by a box filter when downsampling."""
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    src = samples
    if src_rate > dst_rate:
        width = max(1, round(src_rate / dst_rate))
        if width > 1:
            acc = 0
            smoothed = array.array("h", [0] * len(src))
            for i, s in enumerate(src):
                acc += s
                if i >= width:
                    acc -= src[i - width]
                smoothed[i] = int(acc / min(i + 1, width))
            src = smoothed
    ratio = src_rate / dst_rate
    out_len = max(1, int(len(src) / ratio))
    out = array.array("h", [0] * out_len)
    last = len(src) - 1
    for i in range(out_len):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        a = src[j]
        b = src[j + 1] if j < last else a
        out[i] = int(a + (b - a) * frac)
    return out


def trim_silence(samples: array.array, rate: int, pad_ms: int = 250, frame_ms: int = 20) -> array.array:
    """Remove leading/trailing frames whose energy sits near the noise floor, keeping padding."""
    frame = max(1, rate * frame_ms // 1000)
    if len(samples) < frame * 3:
        return samples
    energies = []
    for start in range(0, len(samples), frame):
        chunk = samples[start : start + frame]
        energies.append(math.sqrt(math.fsum(s * s for s in chunk) / len(chunk)))
    floor = sorted(energies)[len(energies) // 10]  # 10th percentile ~ background noise
    threshold = max(floor * 3.0, 120.0)
    voiced = [i for i, e in enumerate(energies) if e > threshold]
    if not voiced:
        return samples
    pad = max(0, pad_ms // frame_ms)
    first = max(0, voiced[0] - pad) * frame
    last = min(len(energies), voiced[-1] + 1 + pad) * frame
    return samples[first:last]


def normalize_peak(samples: array.array, target: float = 0.7, max_gain: float = 8.0) -> array.array:
    if len(samples) == 0:
        return samples
    peak = max(abs(min(samples)), max(samples))
    if peak < 1:
        return samples
    gain = min(max_gain, (target * 32767) / peak)
    if 0.95 <= gain <= 1.05:
        return samples
    return array.array("h", (max(-32768, min(32767, int(s * gain))) for s in samples))


def encode_wav(samples: array.array, rate: int = TARGET_RATE) -> bytes:
    data = array.array("h", samples)
    if sys.byteorder != "little":
        data.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())
    return buf.getvalue()


def duration_seconds(samples: array.array, rate: int) -> Optional[float]:
    return round(len(samples) / float(rate), 3) if rate > 0 else None
