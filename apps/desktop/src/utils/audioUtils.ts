/**
 * Audio Processing, Resampling, Encoding, and Validation Utilities for W.E.D.N.E.S.D.A.Y.
 */

export function writeString(view: DataView, offset: number, string: string): void {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

/**
 * Resample arbitrary-rate Float32 audio buffer to clean 16000 Hz mono PCM.
 * Uses box-car area averaging for antialiased downsampling.
 */
export function resampleTo16k(audioData: Float32Array, origSampleRate: number): Float32Array {
  if (origSampleRate === 16000 || audioData.length === 0) return audioData;
  const targetSampleRate = 16000;
  const ratio = origSampleRate / targetSampleRate;
  const newLength = Math.max(1, Math.round(audioData.length / ratio));
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < audioData.length; i++) {
      accum += audioData[i];
      count++;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

/**
 * Peak volume normalization and silence thresholding.
 * Boosts soft microphone input to optimal recognition range (~0.75-0.85 peak) without clipping.
 */
export function normalizeAndFilterAudio(samples: Float32Array): Float32Array {
  if (samples.length === 0) return samples;
  let maxPeak = 0;
  let sumSquares = 0;
  for (let i = 0; i < samples.length; i++) {
    const abs = Math.abs(samples[i]);
    if (abs > maxPeak) maxPeak = abs;
    sumSquares += abs * abs;
  }
  const rms = Math.sqrt(sumSquares / samples.length);

  // If pure silence or near-zero noise floor (RMS < 0.003), leave as is
  if (maxPeak < 0.008 || rms < 0.002) {
    return samples;
  }

  // Target peak amplitude 0.80 for high SNR
  const targetPeak = 0.80;
  const gain = Math.min(6.0, targetPeak / maxPeak);
  if (gain <= 1.05 && gain >= 0.95) return samples;

  const normalized = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    normalized[i] = Math.max(-1, Math.min(1, samples[i] * gain));
  }
  return normalized;
}

/**
 * Convert Float32Array PCM samples to offline 16-bit mono RIFF WAV buffer.
 */
export function floatTo16BitPCM(samples: Float32Array, sampleRate: number = 16000): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  /* RIFF identifier */
  writeString(view, 0, 'RIFF');
  /* file length */
  view.setUint32(4, 36 + samples.length * 2, true);
  /* RIFF type */
  writeString(view, 8, 'WAVE');
  /* format chunk identifier */
  writeString(view, 12, 'fmt ');
  /* format chunk length */
  view.setUint32(16, 16, true);
  /* sample format (PCM = 1) */
  view.setUint16(20, 1, true);
  /* channel count (mono = 1) */
  view.setUint16(22, 1, true);
  /* sample rate */
  view.setUint32(24, sampleRate, true);
  /* byte rate (sample rate * block align) */
  view.setUint32(28, sampleRate * 2, true);
  /* block align (channel count * bytes per sample) */
  view.setUint16(32, 2, true);
  /* bits per sample (16-bit) */
  view.setUint16(34, 16, true);
  /* data chunk identifier */
  writeString(view, 36, 'data');
  /* data chunk length */
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/**
 * Encode ArrayBuffer to standard base64 string.
 */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + CHUNK)));
  }
  return globalThis.btoa(binary);
}

export interface AudioBufferMetrics {
  durationSeconds: number;
  sampleCount: number;
  peakAmplitude: number;
  rmsAmplitude: number;
  silenceRatio: number;
}

/**
 * Compute non-sensitive audio signal metrics directly from PCM float samples.
 */
export function calculateAudioMetrics(samples: Float32Array, sampleRate: number): AudioBufferMetrics {
  const sampleCount = samples.length;
  const durationSeconds = sampleRate > 0 ? sampleCount / sampleRate : 0;
  let maxPeak = 0;
  let sumSquares = 0;
  let silentCount = 0;

  for (let i = 0; i < samples.length; i++) {
    const abs = Math.abs(samples[i]);
    if (abs > maxPeak) maxPeak = abs;
    sumSquares += abs * abs;
    if (abs < 0.008) silentCount++;
  }

  const rmsAmplitude = sampleCount > 0 ? Math.sqrt(sumSquares / sampleCount) : 0;
  const silenceRatio = sampleCount > 0 ? silentCount / sampleCount : 0;

  return {
    durationSeconds: Math.round(durationSeconds * 100) / 100,
    sampleCount,
    peakAmplitude: Math.round(maxPeak * 1000) / 1000,
    rmsAmplitude: Math.round(rmsAmplitude * 1000) / 1000,
    silenceRatio: Math.round(silenceRatio * 1000) / 1000,
  };
}

export interface WordAccuracyResult {
  matchingWords: number;
  totalExpected: number;
  accuracyPercent: number;
  expectedTokens: string[];
  recognizedTokens: string[];
  matchedWords: string[];
  missingWords: string[];
}

/**
 * Compute Word Match Accuracy against an expected test phrase:
 * Formula: (matchingWords / totalExpectedWords) * 100%
 * Tokenizes, strips punctuation, case-normalizes, and aligns word matches.
 */
export function computeWordAccuracy(recognized: string, expected: string): WordAccuracyResult {
  const clean = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^\w\s]/g, '')
      .split(/\s+/)
      .filter(Boolean);

  const expectedTokens = clean(expected);
  const recognizedTokens = clean(recognized);

  if (expectedTokens.length === 0) {
    return {
      matchingWords: 0,
      totalExpected: 0,
      accuracyPercent: 0,
      expectedTokens: [],
      recognizedTokens: [],
      matchedWords: [],
      missingWords: [],
    };
  }

  const matchedWords: string[] = [];
  const missingWords: string[] = [];
  const recPool = [...recognizedTokens];

  for (const expWord of expectedTokens) {
    const idx = recPool.indexOf(expWord);
    if (idx !== -1) {
      matchedWords.push(expWord);
      recPool.splice(idx, 1);
    } else {
      missingWords.push(expWord);
    }
  }

  const matchingWords = matchedWords.length;
  const accuracyPercent = Math.round((matchingWords / expectedTokens.length) * 100);

  return {
    matchingWords,
    totalExpected: expectedTokens.length,
    accuracyPercent,
    expectedTokens,
    recognizedTokens,
    matchedWords,
    missingWords,
  };
}

const tokenize = (s: string) =>
  s
    .toLowerCase()
    .replace(/[’']/g, '')
    .replace(/[^\w\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean);

export interface WordErrorResult {
  /** (substitutions + deletions + insertions) / reference words. Can exceed 1. */
  wer: number;
  substitutions: number;
  deletions: number;
  insertions: number;
  referenceWords: number;
  /** Alignment for display: each reference word with what the recognizer produced. */
  alignment: { expected: string | null; heard: string | null; op: 'match' | 'sub' | 'del' | 'ins' }[];
}

/**
 * Word error rate via Levenshtein alignment over word tokens. Unlike a bag-of-words
 * match, word order and extra words count, which is the standard recognition metric.
 */
export function computeWordErrorRate(recognized: string, expected: string): WordErrorResult {
  const ref = tokenize(expected);
  const hyp = tokenize(recognized);
  const n = ref.length;
  const m = hyp.length;
  const d: number[][] = Array.from({ length: n + 1 }, (_, i) => Array.from({ length: m + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const cost = ref[i - 1] === hyp[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
    }
  }
  const alignment: WordErrorResult['alignment'] = [];
  let i = n;
  let j = m;
  let s = 0;
  let del = 0;
  let ins = 0;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && d[i][j] === d[i - 1][j - 1] + (ref[i - 1] === hyp[j - 1] ? 0 : 1)) {
      const match = ref[i - 1] === hyp[j - 1];
      if (!match) s++;
      alignment.unshift({ expected: ref[i - 1], heard: hyp[j - 1], op: match ? 'match' : 'sub' });
      i--;
      j--;
    } else if (i > 0 && d[i][j] === d[i - 1][j] + 1) {
      del++;
      alignment.unshift({ expected: ref[i - 1], heard: null, op: 'del' });
      i--;
    } else {
      ins++;
      alignment.unshift({ expected: null, heard: hyp[j - 1], op: 'ins' });
      j--;
    }
  }
  return {
    wer: n > 0 ? (s + del + ins) / n : m > 0 ? 1 : 0,
    substitutions: s,
    deletions: del,
    insertions: ins,
    referenceWords: n,
    alignment,
  };
}

/** Resample to 16 kHz mono and encode as 16-bit WAV, without changing gain. */
export function encodeClipForRecognition(samples: Float32Array, sampleRate: number): ArrayBuffer {
  return floatTo16BitPCM(resampleTo16k(samples, sampleRate), 16000);
}

const ENGINE_LABELS: Record<string, string> = {
  windows_sapi: 'Windows Speech',
  faster_whisper: 'Whisper (faster-whisper)',
};

export const engineLabel = (engine: string): string => ENGINE_LABELS[engine] ?? engine;

export interface EngineRun {
  engine: string;
  wer: WordErrorResult;
  latencyMs: number | null;
}

export interface EngineSummary {
  engine: string;
  phrases: number;
  /** Total errors / total reference words across this engine's scored phrases. */
  wer: number;
  errors: number;
  referenceWords: number;
  medianLatencyMs: number | null;
}

/** Totals each engine's scored phrases. Phrase scores are pooled by word, not averaged. */
export function summarizeEngineRuns(runs: EngineRun[]): EngineSummary[] {
  const byEngine = new Map<string, EngineRun[]>();
  for (const run of runs) byEngine.set(run.engine, [...(byEngine.get(run.engine) ?? []), run]);
  return [...byEngine.entries()].map(([engine, list]) => {
    const errors = list.reduce((n, r) => n + r.wer.substitutions + r.wer.deletions + r.wer.insertions, 0);
    const referenceWords = list.reduce((n, r) => n + r.wer.referenceWords, 0);
    const times = list.map((r) => r.latencyMs).filter((t): t is number => t !== null).sort((a, b) => a - b);
    const mid = Math.floor(times.length / 2);
    return {
      engine,
      phrases: list.length,
      wer: referenceWords ? errors / referenceWords : 0,
      errors,
      referenceWords,
      medianLatencyMs: !times.length ? null : times.length % 2 ? times[mid] : Math.round((times[mid - 1] + times[mid]) / 2),
    };
  });
}
