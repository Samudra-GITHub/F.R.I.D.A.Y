import test from 'node:test';
import assert from 'node:assert/strict';
import {
  computeWordErrorRate,
  computeWordAccuracy,
  calculateAudioMetrics,
  resampleTo16k,
  normalizeAndFilterAudio,
  floatTo16BitPCM,
} from '../src/utils/audioUtils.ts';

test('Audio Utilities: Accuracy calculation and signal analysis', async (t) => {
  const TARGET = 'Hey Wednesday, what time is it?';

  await t.test('100% exact match recognition', () => {
    const res = computeWordAccuracy('Hey Wednesday what time is it', TARGET);
    assert.equal(res.matchingWords, 6);
    assert.equal(res.totalExpected, 6);
    assert.equal(res.accuracyPercent, 100);
    assert.equal(res.missingWords.length, 0);
  });

  await t.test('Case and punctuation normalization', () => {
    const res = computeWordAccuracy('hey wednesday, what time is it?', TARGET);
    assert.equal(res.accuracyPercent, 100);
  });

  await t.test('Partial recognition accuracy', () => {
    // 4 out of 6 words matched ("friday", "what", "time", "is")
    const res = computeWordAccuracy('Wednesday what time is now', TARGET);
    assert.equal(res.matchingWords, 4);
    assert.equal(res.totalExpected, 6);
    assert.equal(res.accuracyPercent, 67); // 4 / 6 = 66.67% -> 67%
    assert.ok(res.missingWords.includes('hey'));
    assert.ok(res.missingWords.includes('it'));
  });

  await t.test('0% recognition when empty or completely different', () => {
    const resEmpty = computeWordAccuracy('', TARGET);
    assert.equal(resEmpty.matchingWords, 0);
    assert.equal(resEmpty.accuracyPercent, 0);

    const resUnrelated = computeWordAccuracy('random unrelated noise', TARGET);
    assert.equal(resUnrelated.matchingWords, 0);
    assert.equal(resUnrelated.accuracyPercent, 0);
  });

  await t.test('calculateAudioMetrics detects silence and non-silence', () => {
    // 16000 samples of pure zeroes (1 second @ 16kHz)
    const silentBuffer = new Float32Array(16000);
    const silentMetrics = calculateAudioMetrics(silentBuffer, 16000);
    assert.equal(silentMetrics.durationSeconds, 1);
    assert.equal(silentMetrics.sampleCount, 16000);
    assert.equal(silentMetrics.peakAmplitude, 0);
    assert.equal(silentMetrics.rmsAmplitude, 0);
    assert.equal(silentMetrics.silenceRatio, 1);

    // Buffer with sine wave
    const activeBuffer = new Float32Array(16000);
    for (let i = 0; i < 16000; i++) {
      activeBuffer[i] = 0.5 * Math.sin((2 * Math.PI * 440 * i) / 16000);
    }
    const activeMetrics = calculateAudioMetrics(activeBuffer, 16000);
    assert.equal(activeMetrics.durationSeconds, 1);
    assert.ok(activeMetrics.peakAmplitude >= 0.49);
    assert.ok(activeMetrics.rmsAmplitude >= 0.35);
    assert.ok(activeMetrics.silenceRatio < 0.1);
  });

  await t.test('resampleTo16k downsamples 48kHz audio to 16kHz cleanly', () => {
    const input48k = new Float32Array(48000); // 1 second @ 48kHz
    const output16k = resampleTo16k(input48k, 48000);
    assert.equal(output16k.length, 16000);
  });

  await t.test('floatTo16BitPCM generates valid 44-byte WAV header', () => {
    const samples = new Float32Array(1600); // 0.1s @ 16kHz
    const buffer = floatTo16BitPCM(samples, 16000);
    assert.equal(buffer.byteLength, 44 + 1600 * 2);

    const view = new DataView(buffer);
    // RIFF check
    const riff = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
    assert.equal(riff, 'RIFF');
    // WAVE check
    const wave = String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11));
    assert.equal(wave, 'WAVE');
    // Sample rate check
    assert.equal(view.getUint32(24, true), 16000);
    // Channels check
    assert.equal(view.getUint16(22, true), 1);
    // Bits per sample
    assert.equal(view.getUint16(34, true), 16);
  });
});

test('Word error rate is order-aware and counts insertions and deletions', () => {
  assert.equal(computeWordErrorRate('Hey Wednesday what time is it', 'Hey Wednesday, what time is it?').wer, 0);
  const mishear = computeWordErrorRate('A Wednesday what time is it', 'Hey Wednesday, what time is it?');
  assert.equal(mishear.substitutions, 1);
  assert.ok(Math.abs(mishear.wer - 1 / 6) < 1e-9);
  assert.ok(computeWordErrorRate('it is time what friday hey', 'hey wednesday what time is it').wer > 0.5);
  assert.equal(computeWordErrorRate('I was looking at the map', 'I was looking at the map this morning').deletions, 2);
  assert.equal(computeWordErrorRate('', 'open my settings').wer, 1);
});
