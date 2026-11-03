import assert from 'node:assert/strict';
import test from 'node:test';

import { ago, describeLocation, permissionLabel, usableFix } from '../src/services/earthLocation.ts';

const NOW = Date.parse('2026-10-31T12:00:00Z');
const fix = (over = {}) => ({
  latitude: 22.57,
  longitude: 88.36,
  accuracy_m: 80,
  status: 'fresh',
  provider: 'test',
  is_stale: false,
  timestamp_utc: '2026-10-31T11:58:00Z',
  ...over,
});
const status = (over = {}) => ({
  mode: 'once',
  tracking_enabled: false,
  is_paused: false,
  worker_running: false,
  update_interval_s: 60,
  latest_fix: fix(),
  ...over,
});
const tracking = (over = {}) => status({ mode: 'continuous', tracking_enabled: true, worker_running: true, ...over });
const describe = (s) => describeLocation(s, NOW);

test('a fix without real coordinates gives no position', () => {
  assert.equal(usableFix(null), null);
  assert.equal(usableFix(fix({ latitude: null })), null);
  assert.equal(usableFix(fix({ longitude: Number.NaN })), null);
  assert.equal(usableFix(fix({ latitude: 91 })), null);
  assert.equal(usableFix(fix({ longitude: -181 })), null);
  assert.equal(usableFix(fix({ latitude: 0, longitude: 0 }))?.latitude, 0);
});

test('off never shows a position, even if one is stored', () => {
  const view = describe(status({ mode: 'off' }));
  assert.equal(view.kind, 'off');
  assert.equal(view.position, null);
});

test('tracking is claimed only with a running worker and a fresh fix', () => {
  const view = describe(tracking());
  assert.equal(view.kind, 'tracking');
  assert.equal(view.fresh, true);
  assert.equal(view.monitoring, true);
  assert.equal(view.label, 'Tracking · updated 2 min ago');
});

test('a stale fix during tracking says no fresh position and marks it not fresh', () => {
  const view = describe(tracking({ latest_fix: fix({ status: 'stale', is_stale: true }) }));
  assert.equal(view.kind, 'no_fresh_fix');
  assert.equal(view.fresh, false);
  assert.ok(view.position, 'the last position can still be shown, labelled');
  assert.match(view.label, /^No fresh position/);
});

test('a dead worker reads as stopped, not tracking', () => {
  const view = describe(tracking({ worker_running: false }));
  assert.equal(view.kind, 'stopped');
  assert.equal(view.monitoring, false);
  assert.equal(view.fresh, false);
});

test('paused tracking reads as paused and is not monitoring', () => {
  const view = describe(tracking({ is_paused: true }));
  assert.equal(view.kind, 'paused');
  assert.equal(view.monitoring, false);
  assert.equal(view.fresh, false);
});

test('denied permission shows no position, in any mode', () => {
  for (const s of [status(), tracking()]) {
    const view = describe({ ...s, latest_fix: fix({ status: 'denied', latitude: null, longitude: null }) });
    assert.equal(view.kind, 'denied');
    assert.equal(view.position, null);
  }
});

test('once distinguishes a current reading, an old one, none, and a failed one', () => {
  assert.equal(describe(status()).kind, 'current');
  assert.equal(describe(status({ latest_fix: fix({ is_stale: true, status: 'stale' }) })).kind, 'last_known');
  assert.equal(describe(status({ latest_fix: null })).kind, 'not_read');
  assert.equal(
    describe(status({ latest_fix: fix({ status: 'unavailable', latitude: null, longitude: null }) })).kind,
    'unavailable'
  );
});

test('a coarse fix is marked approximate', () => {
  assert.equal(describe(status({ latest_fix: fix({ accuracy_m: 20000 }) })).approximate, true);
  assert.equal(describe(status()).approximate, false);
});

test('unknown status claims nothing', () => {
  assert.equal(describe(null).position, null);
});

test('permission reads plainly', () => {
  assert.equal(permissionLabel(status()), 'Allowed');
  assert.equal(permissionLabel(status({ latest_fix: null })), 'Not checked yet');
  assert.equal(permissionLabel(status({ latest_fix: fix({ status: 'denied' }) })), 'Denied in Windows settings');
});

test('times read as elapsed', () => {
  assert.equal(ago('2026-10-31T11:59:40Z', NOW), 'just now');
  assert.equal(ago('2026-10-31T09:00:00Z', NOW), '3 h ago');
  assert.equal(ago(null, NOW), 'at an unknown time');
});
