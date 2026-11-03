import assert from 'node:assert/strict';
import test from 'node:test';

import {
  _resetEarthQueueForTest,
  describeToolCall,
  queueEarthActions,
  recordBatchResults,
  takeWaitingBatches,
  validateEarthAction,
} from '../src/services/earthActions.ts';

test('the desktop refuses actions outside the contract too', () => {
  for (const raw of [
    null,
    { type: 'eval' },
    { type: 'focus', latitude: 0, longitude: 200 },
    { type: 'set_layer', layer: 'detection', enabled: true },
    { type: 'select_aircraft', query: 'a;b' },
    { type: 'show_records', records: new Array(501).fill({}) },
  ]) {
    assert.equal(validateEarthAction(raw), null, JSON.stringify(raw)?.slice(0, 60));
  }
  assert.deepEqual(validateEarthAction({ type: 'focus', latitude: 1, longitude: 2, code: 'x' }), {
    type: 'focus',
    latitude: 1,
    longitude: 2,
    preset: 'regional',
  });
});

test('a batch waits until Earth takes it, and is done only when Earth reports back', () => {
  _resetEarthQueueForTest();
  const id = queueEarthActions([{ type: 'return_global' }, { type: 'nope' }], 'test');
  const [batch] = takeWaitingBatches();
  assert.equal(batch.id, id);
  assert.equal(batch.actions.length, 1, 'the invalid one never goes to Earth');
  assert.equal(takeWaitingBatches().length, 0, 'a batch is sent once');
  recordBatchResults(id, [{ type: 'return_global', ok: true }]);
  recordBatchResults('unknown', [{ ok: true }]);
});

test('a batch of only refused actions is done at once, with the refusals', () => {
  _resetEarthQueueForTest();
  queueEarthActions([{ type: 'nope' }], 'test');
  assert.equal(takeWaitingBatches().length, 0);
});

test('the interpreted request comes from the arguments the tools ran with', () => {
  assert.equal(describeToolCall('get_earthquakes', { min_magnitude: 4 }), 'Earthquakes · magnitude 4+');
  assert.equal(
    describeToolCall('get_aircraft_nearby', { latitude: 20.59, longitude: 78.96, radius_nm: 200 }),
    'Aircraft nearby · near 20.6, 79.0 · within 200 nm'
  );
  assert.equal(describeToolCall('control_earth', { action: 'focus_user' }), 'Earth view · focus user');
  assert.equal(describeToolCall('mystery_tool'), 'mystery tool');
});
