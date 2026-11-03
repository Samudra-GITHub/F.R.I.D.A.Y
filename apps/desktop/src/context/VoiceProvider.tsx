import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PendingTranscript, VoiceConfigResponse, VoiceContextValue } from '../types/voice';
import { VoiceContext } from './VoiceContext';
import { fetchVoiceConfig, synthesizeSpeech, transcribeAudio, updateVoicePrivacy } from '../services/voiceApi';
import { arrayBufferToBase64, encodeClipForRecognition } from '../utils/audioUtils';
import { describeMicError, listMicrophones, MicRecorder } from '../utils/micRecorder';

const MIN_CLIP_SECONDS = 0.35;

const readPref = (key: string): string | null => {
  try {
    return localStorage.getItem(`friday.${key}`);
  } catch {
    return null;
  }
};
const writePref = (key: string, value: string | null) => {
  try {
    if (value === null) localStorage.removeItem(`friday.${key}`);
    else localStorage.setItem(`friday.${key}`, value);
  } catch {
    /* storage unavailable: preference lasts for this session only */
  }
};

export const VoiceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const recorderRef = useRef<MicRecorder | null>(null);
  if (!recorderRef.current) recorderRef.current = new MicRecorder();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speakTokenRef = useRef(0);

  const [phase, setPhase] = useState<VoiceContextValue['phase']>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingTranscript | null>(null);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [outputEnabled, setOutputEnabledState] = useState<boolean>(() => readPref('voiceOutput') === 'on');
  const [config, setConfig] = useState<VoiceConfigResponse | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [selectedVoice, setSelectedVoiceState] = useState<string | null>(() => readPref('voice'));
  const [selectedEngine, setSelectedEngineState] = useState<string | null>(() => readPref('sttEngine'));
  const [microphones, setMicrophones] = useState<MediaDeviceInfo[]>([]);
  const [selectedMicrophone, setSelectedMicrophoneState] = useState<string | null>(() => readPref('microphone'));

  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await fetchVoiceConfig();
      setConfig(cfg);
      setConfigError(null);
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const refreshMicrophones = useCallback(async () => {
    try {
      setMicrophones(await listMicrophones());
    } catch {
      setMicrophones([]);
    }
  }, []);

  useEffect(() => {
    refreshConfig();
    refreshMicrophones();
    const md = navigator.mediaDevices;
    md?.addEventListener?.('devicechange', refreshMicrophones);
    return () => md?.removeEventListener?.('devicechange', refreshMicrophones);
  }, [refreshConfig, refreshMicrophones]);

  const setOutputEnabled = useCallback((enabled: boolean) => {
    setOutputEnabledState(enabled);
    writePref('voiceOutput', enabled ? 'on' : 'off');
  }, []);
  const setSelectedVoice = useCallback((v: string | null) => {
    setSelectedVoiceState(v);
    writePref('voice', v);
  }, []);
  const setSelectedEngine = useCallback((engine: string | null) => {
    setSelectedEngineState(engine);
    writePref('sttEngine', engine);
  }, []);
  const setSelectedMicrophone = useCallback((id: string | null) => {
    setSelectedMicrophoneState(id);
    writePref('microphone', id);
  }, []);

  const stopSpeaking = useCallback(() => {
    speakTokenRef.current++;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    setIsSpeaking(false);
    setPhase((p) => (p === 'speaking' ? 'idle' : p));
    updateVoicePrivacy('stop_playback').catch(() => {});
  }, []);

  const discardPending = useCallback(() => {
    setPending((prev) => {
      if (prev?.audioUrl) URL.revokeObjectURL(prev.audioUrl);
      return null;
    });
  }, []);

  const startRecording = useCallback(async () => {
    const rec = recorderRef.current!;
    if (rec.active) return;
    stopSpeaking();
    discardPending();
    setVoiceError(null);
    try {
      await rec.start({ deviceId: selectedMicrophone });
      setRecordingStartedAt(performance.now());
      setPhase('listening');
      // Labels only become readable after the first permission grant.
      refreshMicrophones();
    } catch (err) {
      setVoiceError(describeMicError(err));
      setPhase('idle');
    }
  }, [selectedMicrophone, stopSpeaking, discardPending, refreshMicrophones]);

  const cancelRecording = useCallback(() => {
    recorderRef.current?.cancel();
    setRecordingStartedAt(null);
    setPhase('idle');
  }, []);

  const stopRecording = useCallback(async () => {
    const rec = recorderRef.current!;
    if (!rec.active) return;
    setRecordingStartedAt(null);
    setPhase('transcribing');
    try {
      const { samples, sampleRate } = await rec.stop();
      if (samples.length / sampleRate < MIN_CLIP_SECONDS) {
        setVoiceError('That recording was too short. Hold the microphone open while you speak.');
        setPhase('idle');
        return;
      }
      const wav = encodeClipForRecognition(samples, sampleRate);
      const audioUrl = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }));
      const started = performance.now();
      const result = await transcribeAudio(arrayBufferToBase64(wav), selectedEngine);
      setPending({
        text: result.status === 'ok' ? result.transcript : '',
        audioUrl,
        result,
        clientRoundTripMs: Math.round(performance.now() - started),
      });
      if (result.status !== 'ok') setVoiceError(result.details || 'No speech was recognized.');
    } catch (err) {
      setVoiceError(`Transcription failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPhase('idle');
    }
  }, [selectedEngine]);

  const setPendingText = useCallback((text: string) => {
    setPending((prev) => (prev ? { ...prev, text } : prev));
  }, []);

  const playPendingAudio = useCallback(() => {
    if (!pending?.audioUrl) return;
    new Audio(pending.audioUrl).play().catch((err) => setVoiceError(`Playback failed: ${err.message}`));
  }, [pending]);

  const speak = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      stopSpeaking();
      const token = ++speakTokenRef.current;
      try {
        const res = await synthesizeSpeech(text.slice(0, 2000), selectedVoice);
        if (token !== speakTokenRef.current) return; // stopped while synthesizing
        if (res.status !== 'ok' || !res.audio_base64) {
          setVoiceError(res.details || 'Speech synthesis is unavailable.');
          return;
        }
        const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`);
        audioRef.current = audio;
        const done = () => {
          if (audioRef.current === audio) audioRef.current = null;
          setIsSpeaking(false);
          setPhase((p) => (p === 'speaking' ? 'idle' : p));
        };
        audio.onended = done;
        audio.onerror = done;
        setIsSpeaking(true);
        setPhase('speaking');
        await audio.play();
      } catch (err) {
        if (token === speakTokenRef.current) {
          setIsSpeaking(false);
          setPhase((p) => (p === 'speaking' ? 'idle' : p));
          setVoiceError(`Speech output failed: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    },
    [selectedVoice, stopSpeaking]
  );

  const stopAll = useCallback(() => {
    recorderRef.current?.cancel();
    setRecordingStartedAt(null);
    stopSpeaking();
    setPhase('idle');
  }, [stopSpeaking]);

  useEffect(
    () => () => {
      recorderRef.current?.cancel();
      audioRef.current?.pause();
    },
    []
  );

  const value = useMemo<VoiceContextValue>(
    () => ({
      phase,
      voiceError,
      clearVoiceError: () => setVoiceError(null),
      isRecording: phase === 'listening',
      recordingStartedAt,
      startRecording,
      stopRecording,
      cancelRecording,
      readLevel: () => recorderRef.current?.level ?? 0,
      pending,
      setPendingText,
      discardPending,
      playPendingAudio,
      outputEnabled,
      setOutputEnabled,
      isSpeaking,
      speak,
      stopSpeaking,
      config,
      configError,
      refreshConfig,
      voices: config?.available_voices ?? [],
      selectedVoice,
      setSelectedVoice,
      sttEngines: config?.available_stt_engines ?? [],
      selectedEngine,
      setSelectedEngine,
      microphones,
      selectedMicrophone,
      setSelectedMicrophone,
      refreshMicrophones,
      stopAll,
    }),
    [
      phase, voiceError, recordingStartedAt, startRecording, stopRecording, cancelRecording, pending, setPendingText,
      discardPending, playPendingAudio, outputEnabled, setOutputEnabled, isSpeaking, speak,
      stopSpeaking, config, configError, refreshConfig, selectedVoice, setSelectedVoice,
      selectedEngine, setSelectedEngine, microphones, selectedMicrophone, setSelectedMicrophone, refreshMicrophones, stopAll,
    ]
  );

  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
};
