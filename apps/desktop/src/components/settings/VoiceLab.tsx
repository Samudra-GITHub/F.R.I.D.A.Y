import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { useVoice } from '../../context/VoiceContext';
import {
  describeMicError,
  EMBEDDED_MIC_MESSAGE,
  isEmbeddedAppBrowser,
  MicAccess,
  microphoneAccess,
  MicRecorder,
} from '../../utils/micRecorder';
import {
  arrayBufferToBase64,
  calculateAudioMetrics,
  computeWordErrorRate,
  encodeClipForRecognition,
  engineLabel,
  summarizeEngineRuns,
  WordErrorResult,
} from '../../utils/audioUtils';
import { transcribeAudio } from '../../services/voiceApi';
import { STTTranscriptionResponse } from '../../types/voice';
import { Icon } from '../ui/Icon';
import './VoiceLab.css';

export const TEST_PHRASES = [
  'Hey Wednesday, what time is it?',
  "What's the weather like today?",
  'Find the latest earthquakes.',
  'Open my settings.',
  'Wednesday, find the latest earthquakes, then tell me what the weather is like today, and wait before opening my settings.',
];

interface Capture {
  url: string;
  wav: ArrayBuffer;
  durationS: number;
  nativeRate: number;
  peakDb: number;
  rmsDb: number;
  clippedPct: number;
  silencePct: number;
  device: string | null;
  dsp: string;
}

interface EngineResult {
  result?: STTTranscriptionResponse;
  /** Only set when the engine actually ran; a failed engine has no score. */
  wer?: WordErrorResult;
  roundTripMs?: number;
  error?: string;
}

interface Trial {
  capture: Capture;
  /** Results for this one recording, keyed by engine. */
  engines: Record<string, EngineResult>;
}

/**
 * Lives outside the component so recordings and scores survive moving to another screen,
 * and a transcription still in progress can finish. In memory only: closing or reloading
 * the window, or pressing Clear, removes everything.
 */
interface LabState {
  index: number;
  trials: Record<number, Trial>;
  working: boolean;
}
let labState: LabState = { index: 0, trials: {}, working: false };
const labListeners = new Set<() => void>();
const subscribeLab = (listener: () => void) => {
  labListeners.add(listener);
  return () => labListeners.delete(listener);
};
const getLab = () => labState;
const updateLab = (patch: Partial<LabState>) => {
  labState = { ...labState, ...patch };
  labListeners.forEach((l) => l());
};
const setTrials = (fn: (prev: Record<number, Trial>) => Record<number, Trial>) => updateLab({ trials: fn(labState.trials) });

/** Key for a run on the backend's default engine, when the engine list isn't known. */
const DEFAULT_ENGINE = 'default';

const db = (v: number) => (v > 0 ? 20 * Math.log10(v) : -Infinity);
const fmtDb = (v: number) => (Number.isFinite(v) ? `${v.toFixed(1)} dBFS` : '−∞');
const pct = (v: number) => `${Math.round(v * 100)}%`;
const label = (engine: string) => (engine === DEFAULT_ENGINE ? 'Default engine' : engineLabel(engine));

const LevelMeter: React.FC<{ recorder: MicRecorder; active: boolean }> = ({ recorder, active }) => {
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    const loop = () => {
      const level = recorder.level;
      // map −60…0 dBFS to 0…1
      const pos = Math.max(0, Math.min(1, (db(level) + 60) / 60));
      bar.current?.style.setProperty('--pos', pos.toFixed(3));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active, recorder]);
  return (
    <div className="meter" ref={bar} role="img" aria-label="Live input level">
      <div className="meter__fill" />
      <span className="meter__tick" style={{ left: `${(1 - 24 / 60) * 100}%` }} title="−24 dBFS" />
      <span className="meter__tick" style={{ left: `${(1 - 6 / 60) * 100}%` }} title="−6 dBFS" />
    </div>
  );
};

const EngineColumn: React.FC<{ engine: string; run?: EngineResult; running: boolean; lowest: boolean }> = ({ engine, run, running, lowest }) => (
  <section className="lab__engine" aria-label={`${label(engine)} result`}>
    <div className="lab__engine-head">
      <span className="lab__engine-name">{label(engine)}</span>
      {lowest && <span className="badge badge--ok">Lowest error</span>}
    </div>
    {running && !run && (
      <p className="small muted row">
        <span className="spinner" /> Transcribing…
      </p>
    )}
    {run?.error && <div className="notice notice--danger"><Icon name="alert" size={15} /><div>{run.error}</div></div>}
    {run?.result && !run.wer && <div className="notice notice--warn"><Icon name="alert" size={15} /><div>{run.result.details ?? `Not scored: ${run.result.status}`}</div></div>}
    {run?.result && run.wer && (
      <>
        <span className="lab__score-value mono">{pct(run.wer.wer)}</span>
        <span className="lab__score-label">Word error rate</span>
        <span className="lab__score-sub">
          {run.wer.substitutions} wrong · {run.wer.deletions} missed · {run.wer.insertions} extra, of {run.wer.referenceWords} words
        </span>
        <div className="lab__align" aria-label="Word alignment">
          {run.wer.alignment.map((a, i) => (
            <span key={i} className={`align align--${a.op}`} title={a.op === 'sub' ? `expected “${a.expected}”` : a.op === 'del' ? 'missed' : a.op === 'ins' ? 'extra word' : undefined}>
              {a.op === 'del' ? a.expected : a.heard}
            </span>
          ))}
        </div>
        <dl className="lab__engine-facts">
          <dt>Confidence</dt>
          <dd className="mono">{run.result.confidence != null ? pct(run.result.confidence) : 'not reported'}</dd>
          <dt>Recognition</dt>
          <dd className="mono">{run.result.latency_ms ?? '—'} ms</dd>
          <dt>Round trip</dt>
          <dd className="mono">{run.roundTripMs} ms</dd>
        </dl>
        {run.result.details && <p className="lab__score-sub">{run.result.details}</p>}
      </>
    )}
  </section>
);

export const VoiceLab: React.FC = () => {
  const { selectedMicrophone, stopAll, sttEngines, selectedEngine, setSelectedEngine, config } = useVoice();
  const recorder = useMemo(() => new MicRecorder(), []);
  const { index, trials, working } = useSyncExternalStore(subscribeLab, getLab, getLab);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [browserDsp, setBrowserDsp] = useState(true);
  const [copied, setCopied] = useState(false);
  const [micAccess, setMicAccess] = useState<MicAccess>('unknown');
  const embeddedBlocked = micAccess === 'denied' && isEmbeddedAppBrowser();

  useEffect(() => {
    microphoneAccess().then(setMicAccess);
  }, []);

  useEffect(() => () => recorder.cancel(), [recorder]);

  const clearAll = () => {
    Object.values(labState.trials).forEach((t) => URL.revokeObjectURL(t.capture.url));
    updateLab({ trials: {}, index: 0 });
    setError(null);
  };

  const phrase = TEST_PHRASES[index];
  const trial = trials[index];
  const engines = sttEngines.length ? sttEngines : [DEFAULT_ENGINE];
  const inUse = selectedEngine ?? config?.stt_engine ?? null;

  const start = async () => {
    setError(null);
    stopAll();
    try {
      await recorder.start({
        deviceId: selectedMicrophone,
        noiseSuppression: browserDsp,
        autoGainControl: browserDsp,
        echoCancellation: browserDsp,
      });
      setRecording(true);
    } catch (err) {
      setError(describeMicError(err));
      microphoneAccess().then(setMicAccess);
    }
  };

  const stop = async () => {
    setRecording(false);
    try {
      const rec = await recorder.stop();
      const m = calculateAudioMetrics(rec.samples, rec.sampleRate);
      let clipped = 0;
      for (let i = 0; i < rec.samples.length; i++) if (Math.abs(rec.samples[i]) >= 0.99) clipped++;
      const wav = encodeClipForRecognition(rec.samples, rec.sampleRate);
      const s = rec.trackSettings as (MediaTrackSettings & { noiseSuppression?: boolean; autoGainControl?: boolean }) | null;
      const capture: Capture = {
        url: URL.createObjectURL(new Blob([wav], { type: 'audio/wav' })),
        wav,
        durationS: m.durationSeconds,
        nativeRate: rec.sampleRate,
        peakDb: db(m.peakAmplitude),
        rmsDb: db(m.rmsAmplitude),
        clippedPct: rec.samples.length ? (clipped / rec.samples.length) * 100 : 0,
        silencePct: m.silenceRatio * 100,
        device: rec.deviceLabel,
        dsp: s
          ? `echo ${s.echoCancellation ? 'on' : 'off'} · noise ${s.noiseSuppression ? 'on' : 'off'} · AGC ${s.autoGainControl ? 'on' : 'off'}`
          : 'unknown',
      };
      setTrials((prev) => {
        if (prev[index]) URL.revokeObjectURL(prev[index].capture.url);
        return { ...prev, [index]: { capture, engines: {} } };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  // The same recording goes to every engine, one at a time so their timings don't interfere.
  const submit = async () => {
    if (!trial) return;
    updateLab({ working: true });
    const at = index;
    const expected = phrase;
    const audio = arrayBufferToBase64(trial.capture.wav);
    const record = (engine: string, run: EngineResult) =>
      setTrials((prev) => ({ ...prev, [at]: { ...prev[at], engines: { ...prev[at].engines, [engine]: run } } }));
    setTrials((prev) => ({ ...prev, [at]: { ...prev[at], engines: {} } }));
    for (const engine of engines) {
      const started = performance.now();
      try {
        const result = await transcribeAudio(audio, engine === DEFAULT_ENGINE ? null : engine);
        const ran = result.status === 'ok' || result.status === 'empty_transcript';
        record(engine, {
          result,
          roundTripMs: Math.round(performance.now() - started),
          wer: ran ? computeWordErrorRate(result.transcript || '', expected) : undefined,
        });
      } catch (err) {
        record(engine, { error: err instanceof Error ? err.message : String(err) });
      }
    }
    updateLab({ working: false });
  };

  const summaries = useMemo(
    () =>
      summarizeEngineRuns(
        Object.values(trials).flatMap((t) =>
          Object.entries(t.engines).flatMap(([engine, run]) =>
            run.wer ? [{ engine, wer: run.wer, latencyMs: run.result?.latency_ms ?? null }] : []
          )
        )
      ),
    [trials]
  );

  const copyReport = async () => {
    const report = {
      browser_dsp: browserDsp,
      engines: summaries.map((s) => ({
        engine: s.engine,
        phrases: s.phrases,
        overall_wer: Number(s.wer.toFixed(3)),
        median_recognition_ms: s.medianLatencyMs,
      })),
      trials: Object.entries(trials)
        .filter(([, t]) => Object.keys(t.engines).length)
        .map(([i, t]) => ({
          expected: TEST_PHRASES[Number(i)],
          duration_s: t.capture.durationS,
          peak_dbfs: Number(t.capture.peakDb.toFixed(1)),
          rms_dbfs: Number(t.capture.rmsDb.toFixed(1)),
          clipped_pct: Number(t.capture.clippedPct.toFixed(2)),
          browser_processing: t.capture.dsp,
          results: Object.fromEntries(
            Object.entries(t.engines).map(([engine, run]) => [
              engine,
              {
                engine_name: run.result?.engine,
                status: run.result?.status ?? 'request_failed',
                heard: run.result?.transcript,
                wer: run.wer ? Number(run.wer.wer.toFixed(3)) : null,
                substitutions: run.wer?.substitutions,
                deletions: run.wer?.deletions,
                insertions: run.wer?.insertions,
                recognizer_confidence: run.result?.confidence ?? null,
                server_latency_ms: run.result?.latency_ms,
                round_trip_ms: run.roundTripMs,
                error: run.error,
              },
            ])
          ),
        })),
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError('Clipboard is unavailable in this window.');
    }
  };

  const levelWarning = trial
    ? trial.capture.peakDb < -30
      ? 'Very quiet: peak is below −30 dBFS. Move closer or raise the input level in Windows sound settings.'
      : trial.capture.clippedPct > 0.5
      ? 'Clipping detected: lower the input level, since distorted audio hurts recognition.'
      : null
    : null;

  const scoredHere = trial ? Object.entries(trial.engines).filter(([, r]) => r.wer) : [];
  const lowestWer = scoredHere.length ? Math.min(...scoredHere.map(([, r]) => r.wer!.wer)) : null;
  // Only call one engine "lowest" when it is genuinely ahead of another on this recording.
  const hasLowest = scoredHere.length > 1 && scoredHere.filter(([, r]) => r.wer!.wer === lowestWer).length === 1;
  const showResults = trial && (working || Object.keys(trial.engines).length > 0);

  return (
    <div className="lab">
      <div className="lab__phrases" role="tablist" aria-label="Test phrases">
        {TEST_PHRASES.map((p, i) => {
          const t = trials[i];
          const runs = t ? Object.values(t.engines).filter((r) => r.wer) : [];
          const shown = t && inUse && t.engines[inUse]?.wer ? t.engines[inUse].wer! : runs[0]?.wer;
          const state = shown ? (shown.wer === 0 ? 'ok' : shown.wer <= 0.25 ? 'warn' : 'bad') : t ? 'rec' : 'none';
          return (
            <button key={i} type="button" role="tab" aria-selected={i === index} className="lab__phrase" data-state={state} onClick={() => !recording && updateLab({ index: i })} disabled={recording}>
              <span className="lab__num mono">{i + 1}</span>
              <span className="lab__phrase-text">{i === 4 ? 'Longer sentence with pauses' : p}</span>
              {runs.length > 0 && <span className="mono lab__phrase-wer">{runs.map((r) => pct(r.wer!.wer)).join(' · ')}</span>}
            </button>
          );
        })}
      </div>

      <div className="lab__stage">
        <p className="eyebrow">Say this, at a normal pace</p>
        <p className="lab__target">“{phrase}”</p>

        <LevelMeter recorder={recorder} active={recording} />

        <div className="row lab__controls">
          {recording ? (
            <button type="button" className="btn btn--primary" onClick={stop}>
              <Icon name="stop" size={13} strokeWidth={2.2} /> Stop recording
            </button>
          ) : (
            <button type="button" className="btn" onClick={start} disabled={working || embeddedBlocked}>
              <Icon name="mic" size={15} /> {trial ? 'Record again' : 'Record'}
            </button>
          )}
          {trial && !recording && (
            <>
              <button type="button" className="btn" onClick={() => new Audio(trial.capture.url).play()}>
                <Icon name="play" size={13} /> Listen
              </button>
              <button type="button" className="btn btn--primary" onClick={submit} disabled={working}>
                {working ? <span className="spinner" /> : <Icon name="wave" size={14} />}{' '}
                {engines.length > 1 ? `Transcribe with ${engines.length} engines` : 'Transcribe locally'}
              </button>
            </>
          )}
          <span className="spacer" />
          <label className="row small muted lab__dsp">
            <button type="button" role="switch" className="switch" aria-checked={browserDsp} onClick={() => setBrowserDsp(!browserDsp)} disabled={recording} aria-label="Browser noise suppression, echo cancellation and gain control" />
            Browser noise/echo/gain processing
          </label>
        </div>

        {embeddedBlocked && (
          <div className="notice notice--warn" role="status">
            <Icon name="mic" size={15} />
            <div>
              {EMBEDDED_MIC_MESSAGE} Go to <code>{window.location.href}</code>.
            </div>
          </div>
        )}
        {error && !embeddedBlocked && <div className="notice notice--danger" role="alert"><Icon name="alert" size={15} /><div>{error}</div></div>}
        {levelWarning && <div className="notice notice--warn"><Icon name="alert" size={15} /><div>{levelWarning}</div></div>}

        {trial && (
          <dl className="lab__metrics">
            <div><dt>Duration</dt><dd className="mono">{trial.capture.durationS.toFixed(2)} s</dd></div>
            <div><dt>Peak</dt><dd className="mono">{fmtDb(trial.capture.peakDb)}</dd></div>
            <div><dt>RMS</dt><dd className="mono">{fmtDb(trial.capture.rmsDb)}</dd></div>
            <div><dt>Clipped</dt><dd className="mono">{trial.capture.clippedPct.toFixed(2)}%</dd></div>
            <div><dt>Near-silent</dt><dd className="mono">{trial.capture.silencePct.toFixed(0)}%</dd></div>
            <div><dt>Capture rate</dt><dd className="mono">{trial.capture.nativeRate} Hz → 16 kHz</dd></div>
            <div className="lab__wide"><dt>Device</dt><dd>{trial.capture.device || 'Default input'} <span className="muted small">({trial.capture.dsp})</span></dd></div>
          </dl>
        )}

        {showResults && (
          <div className="lab__engines" aria-live="polite">
            {engines.map((engine) => (
              <EngineColumn
                key={engine}
                engine={engine}
                run={trial.engines[engine]}
                running={working}
                lowest={hasLowest && trial.engines[engine]?.wer?.wer === lowestWer}
              />
            ))}
          </div>
        )}
        {showResults && <p className="small muted">Every engine heard the same recording. Transcripts are shown exactly as recognized, with no post-processing.</p>}
      </div>

      {summaries.length > 0 && (
        <div className="lab__summary">
          <div className="lab__summary-head">
            <span className="eyebrow">Your results so far</span>
            <span className="spacer" />
            <button type="button" className="btn btn--sm btn--ghost" onClick={clearAll} disabled={working}>
              Clear recordings
            </button>
            <button type="button" className="btn btn--sm" onClick={copyReport}>
              <Icon name={copied ? 'check' : 'link'} size={13} /> {copied ? 'Copied' : 'Copy results (no audio)'}
            </button>
          </div>
          {summaries.map((s) => (
            <div key={s.engine} className="lab__summary-row">
              <span className="lab__summary-name">{label(s.engine)}</span>
              <span><strong className="mono">{pct(s.wer)}</strong> word error rate over {s.phrases} phrase{s.phrases === 1 ? '' : 's'}</span>
              {s.medianLatencyMs !== null && <span className="muted">median {s.medianLatencyMs} ms</span>}
              <span className="spacer" />
              {s.engine === DEFAULT_ENGINE ? null : inUse === s.engine ? (
                <span className="badge badge--accent">In use</span>
              ) : (
                <button type="button" className="btn btn--sm" onClick={() => setSelectedEngine(s.engine)}>
                  Use this engine
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="small muted">Recordings stay in this window’s memory until you clear them or close the window, and are never saved to disk. Audio is only sent to the local backend when you press Transcribe.</p>
    </div>
  );
};
