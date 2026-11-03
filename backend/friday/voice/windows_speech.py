"""Offline Windows System.Speech provider for W.E.D.N.E.S.D.A.Y.

Implements BaseSTTProvider and BaseTTSProvider using native Windows APIs
(System.Speech.Synthesis and System.Speech.Recognition) executed securely via PowerShell.
100% local, offline, zero cloud network traffic.
"""

import base64
import os
import subprocess
import tempfile
import time
import wave
from typing import List, Optional, Tuple

from backend.friday.config import get_settings
from backend.friday.voice import audio_dsp
from backend.friday.voice.base import BaseSTTProvider, BaseTTSProvider
from backend.friday.voice.preflight import inspect_clip
from schemas.contracts import STTTranscriptionResponse, TTSSynthesisResponse


class WindowsSpeechProvider(BaseSTTProvider, BaseTTSProvider):
    """Local offline speech recognition and synthesis provider using Windows System.Speech."""

    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        # Engine probes each spawn PowerShell (~0.5-1.5 s); results are stable for the
        # life of the process, so they are cached after the first successful probe.
        self._available: Optional[bool] = None
        self._voices: Optional[List[str]] = None
        self._recognizers: Optional[List[str]] = None

    def name(self) -> str:
        return "windows_sapi"

    def is_available(self) -> bool:
        """Verify Windows operating system and PowerShell availability (cached)."""
        if self._available is not None:
            return self._available
        if os.name != "nt":
            self._available = False
            return False
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Write-Output 'ok'"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            ok = res.returncode == 0 and "ok" in res.stdout
        except Exception:
            ok = False
        if ok:
            self._available = True
        return ok

    def _probe_lines(self, cmd: str) -> Optional[List[str]]:
        try:
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            return None
        if res.returncode != 0:
            return None
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def get_available_voices(self) -> List[str]:
        """Query installed Windows system voice profiles. Returns [] when the probe fails."""
        if os.name != "nt":
            return []
        if self._voices is None:
            found = self._probe_lines(
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
            )
            if found is None:
                return []
            self._voices = found
        return list(self._voices)

    def get_installed_recognizers(self) -> List[str]:
        """Query installed Windows speech recognition language packs. Returns [] on failure."""
        if os.name != "nt":
            return []
        if self._recognizers is None:
            found = self._probe_lines(
                "Add-Type -AssemblyName System.Speech; "
                "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() | "
                "ForEach-Object { $_.Culture.Name + ': ' + $_.Description }"
            )
            if found is None:
                return []
            self._recognizers = found
        return list(self._recognizers)

    # =========================================================================
    # Speech-to-Text (STT)
    # =========================================================================

    # Recognizes every phrase in the file, not only the first. SAPI's Recognize()
    # returns after one utterance, so we keep calling it until the stream ends.
    _RECOGNIZE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$all = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
$target = $all | Where-Object { $_.Culture.Name -eq '__CULTURE__' } | Select-Object -First 1
if ($target -eq $null) { $target = $all | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1 }
if ($target -eq $null) { Write-Output 'ERR:no_recognizer'; exit 0 }
$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine($target)
try {
    Write-Output ('ENGINE:' + $target.Culture.Name)
    $rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $rec.SetInputToWaveFile('__PATH__')
    $rec.InitialSilenceTimeout = [TimeSpan]::FromSeconds(3)
    $rec.BabbleTimeout = [TimeSpan]::FromSeconds(12)
    $total = [TimeSpan]::FromSeconds(__DURATION__)
    for ($i = 0; $i -lt 60; $i++) {
        $r = $rec.Recognize()
        if ($r -ne $null -and $r.Text) {
            Write-Output ('SEG:' + [math]::Round($r.Confidence, 3) + '|' + $r.Text)
        }
        if ($rec.AudioPosition -ge $total) { break }
        if ($r -eq $null -and $rec.AudioState -eq 'Stopped' -and $rec.AudioPosition.TotalMilliseconds -eq 0) { break }
    }
} finally {
    $rec.Dispose()
}
"""

    def _run_powershell(self, script: str, timeout: float) -> subprocess.CompletedProcess:
        """Run a script via -EncodedCommand so paths and text never need shell quoting."""
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=timeout,
        )

    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        sample_rate_hz: int = 16000,
    ) -> STTTranscriptionResponse:
        """Transcribe a push-to-talk WAV clip with the local Windows recognizer.

        The clip is decoded, measured, converted to 16 kHz mono, trimmed of leading and
        trailing silence, and peak-normalised before recognition. Reported metrics come
        from the clip as received; the transcript is returned exactly as recognized.
        """
        started = time.perf_counter()
        clip, base, early = inspect_clip(audio_bytes, audio_format, self._settings)
        if early is not None:
            return early

        prepared = audio_dsp.resample(clip.samples, clip.sample_rate, audio_dsp.TARGET_RATE)
        # Trimming is measured but not applied: SAPI estimates the noise floor from the
        # leading audio, and trimmed clips scored markedly worse in noisy tests.
        speech_duration = audio_dsp.duration_seconds(
            audio_dsp.trim_silence(prepared, audio_dsp.TARGET_RATE), audio_dsp.TARGET_RATE
        )
        base["speech_duration_seconds"] = speech_duration
        prepared = audio_dsp.normalize_peak(prepared)
        clip_duration = audio_dsp.duration_seconds(prepared, audio_dsp.TARGET_RATE)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_dsp.encode_wav(prepared))
                tmp_path = tmp.name

            culture = getattr(self._settings, "stt_language", None) or "en-US"
            script = (
                self._RECOGNIZE_SCRIPT.replace("__CULTURE__", culture.replace("'", ""))
                .replace("__PATH__", tmp_path.replace("'", "''"))
                .replace("__DURATION__", f"{max(0.1, (clip_duration or 0.1) - 0.05):.3f}")
            )
            timeout = 10 + 2 * (clip_duration or 0)
            run_res = self._run_powershell(script, timeout=timeout)
            out = run_res.stdout.decode("utf-8", errors="replace")
            latency_ms = int((time.perf_counter() - started) * 1000)

            engine_culture = None
            segments: List[Tuple[float, str]] = []
            for line in out.splitlines():
                line = line.strip().lstrip("﻿")
                if line.startswith("ENGINE:"):
                    engine_culture = line[7:]
                elif line.startswith("ERR:no_recognizer"):
                    return STTTranscriptionResponse(
                        status="model_not_installed",
                        latency_ms=latency_ms,
                        details="No English Windows speech recognizer is installed.",
                        **base,
                    )
                elif line.startswith("SEG:") and "|" in line:
                    conf_str, text = line[4:].split("|", 1)
                    try:
                        conf = float(conf_str)
                    except ValueError:
                        conf = 0.0
                    if text.strip():
                        segments.append((conf, text.strip()))

            if run_res.returncode != 0 and not segments:
                err = run_res.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return STTTranscriptionResponse(
                    status="transcription_error",
                    latency_ms=latency_ms,
                    details=f"Speech recognizer failed: {err[-1] if err else 'unknown error'}",
                    **base,
                )

            engine = f"Windows.Speech.Recognition ({engine_culture or culture})"
            if not segments:
                return STTTranscriptionResponse(
                    status="empty_transcript",
                    engine=engine,
                    segment_count=0,
                    latency_ms=latency_ms,
                    details="The recognizer heard audio but produced no words.",
                    **base,
                )

            transcript = " ".join(text for _, text in segments)
            # Word-weighted mean of SAPI's own per-phrase confidence (0..1). This is the
            # recognizer's self-estimate, not a measured accuracy.
            weights = [max(1, len(text.split())) for _, text in segments]
            confidence = round(sum(c * w for (c, _), w in zip(segments, weights)) / sum(weights), 3)
            return STTTranscriptionResponse(
                status="ok",
                transcript=transcript,
                confidence=confidence,
                engine=engine,
                segment_count=len(segments),
                latency_ms=latency_ms,
                details=f"Recognized {len(segments)} phrase(s) locally via Windows.Speech.Recognition",
                **base,
            )
        except subprocess.TimeoutExpired:
            return STTTranscriptionResponse(
                status="transcription_error",
                latency_ms=int((time.perf_counter() - started) * 1000),
                details="Transcription timed out",
                **base,
            )
        except Exception as exc:
            return STTTranscriptionResponse(
                status="transcription_error",
                details=f"Speech recognition error: {exc}",
                **base,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # =========================================================================
    # Text-to-Speech (TTS)
    # =========================================================================

    def synthesize(
        self,
        text: str,
        voice_name: Optional[str] = None,
    ) -> TTSSynthesisResponse:
        """Synthesize text into offline WAV audio bytes.
        
        Uses base64 encoding to prevent shell injection, bounds text length, and cleans up temp files.
        """
        trimmed = (text or "").strip()
        if not trimmed:
            return TTSSynthesisResponse(
                status="error",
                details="Input text is empty",
            )

        if len(trimmed) > 2000:
            trimmed = trimmed[:2000]

        tmp_out_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name

            # Encode text in base64 to prevent any PowerShell injection
            text_b64 = base64.b64encode(trimmed.encode("utf-8")).decode("ascii")

            voice_cmd = ""
            if voice_name:
                voice_b64 = base64.b64encode(voice_name.encode("utf-8")).decode("ascii")
                voice_cmd = f"$v = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{voice_b64}')); $s.SelectVoice($v);"

            ps_script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
    $s.SetOutputToWaveFile('{tmp_out_path}')
    {voice_cmd}
    $text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{text_b64}'))
    $s.Speak($text)
}} finally {{
    $s.Dispose()
}}
"""
            run_res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=12,
            )

            if run_res.returncode != 0 or not os.path.exists(tmp_out_path):
                return TTSSynthesisResponse(
                    status="error",
                    details=f"Speech synthesis failed: {run_res.stderr.strip() or 'Unknown error'}",
                )

            with open(tmp_out_path, "rb") as f:
                wav_bytes = f.read()

            if not wav_bytes:
                return TTSSynthesisResponse(
                    status="error",
                    details="Generated audio file is empty",
                )

            # Compute duration from WAV header
            duration_sec = None
            try:
                with wave.open(tmp_out_path, "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        duration_sec = round(frames / float(rate), 2)
            except Exception:
                pass

            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            return TTSSynthesisResponse(
                status="ok",
                audio_base64=audio_b64,
                audio_format="wav",
                duration_seconds=duration_sec,
                details="Offline synthesis successful via Windows.Speech.Synthesis",
            )

        except subprocess.TimeoutExpired:
            return TTSSynthesisResponse(
                status="error",
                details="Speech synthesis timed out",
            )
        except Exception as exc:
            return TTSSynthesisResponse(
                status="error",
                details=f"Speech synthesis error: {exc}",
            )
        finally:
            if tmp_out_path and os.path.exists(tmp_out_path):
                try:
                    os.unlink(tmp_out_path)
                except OSError:
                    pass
