import test from 'node:test';
import assert from 'node:assert/strict';
import { transcribeAudio } from '../src/services/voiceApi.ts';
import { computeWordErrorRate, engineLabel, summarizeEngineRuns } from '../src/utils/audioUtils.ts';

const captureBody = async (call) => {
  const original = globalThis.fetch;
  let body;
  globalThis.fetch = async (_url, init) => {
    body = JSON.parse(init.body);
    return new Response(JSON.stringify({ status: 'ok', transcript: '' }), { status: 200 });
  };
  try {
    await call();
  } finally {
    globalThis.fetch = original;
  }
  return body;
};

test('transcribeAudio names the engine only when one is chosen', async () => {
  const chosen = await captureBody(() => transcribeAudio('QUJD', 'faster_whisper'));
  assert.equal(chosen.engine, 'faster_whisper');
  assert.equal(chosen.audio_format, 'wav');
  assert.equal(chosen.sample_rate_hz, 16000);
  const byDefault = await captureBody(() => transcribeAudio('QUJD', null));
  assert.ok(!('engine' in byDefault), 'null leaves the choice to the backend default');
});

test('engine summaries pool errors by word and report a true median', () => {
  const ref = 'hey friday what time is it';
  const [sapi, whisper] = summarizeEngineRuns([
    { engine: 'windows_sapi', wer: computeWordErrorRate('it has regulatory news of the head', ref), latencyMs: 1800 },
    { engine: 'faster_whisper', wer: computeWordErrorRate('hey friday what time is it', ref), latencyMs: 400 },
    { engine: 'windows_sapi', wer: computeWordErrorRate('open my settings', 'open my settings'), latencyMs: 1000 },
    { engine: 'faster_whisper', wer: computeWordErrorRate('open my settings', 'open my settings'), latencyMs: 600 },
  ]);
  assert.equal(sapi.engine, 'windows_sapi');
  assert.equal(sapi.phrases, 2);
  assert.equal(sapi.errors, 7);
  assert.equal(sapi.referenceWords, 9);
  assert.ok(Math.abs(sapi.wer - 7 / 9) < 1e-9);
  assert.equal(sapi.medianLatencyMs, 1400);
  assert.equal(whisper.wer, 0);
  assert.equal(whisper.medianLatencyMs, 500);
});

test('missing latency is unknown rather than zero, and an empty list has no engines', () => {
  const [only] = summarizeEngineRuns([{ engine: 'x', wer: computeWordErrorRate('a', 'a'), latencyMs: null }]);
  assert.equal(only.medianLatencyMs, null);
  assert.deepEqual(summarizeEngineRuns([]), []);
});

test('unknown engines keep their own name', () => {
  assert.equal(engineLabel('windows_sapi'), 'Windows Speech');
  assert.equal(engineLabel('mystery'), 'mystery');
});
