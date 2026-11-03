import test from 'node:test';
import assert from 'node:assert/strict';
import { relativeTime } from '../src/utils/relativeTime.ts';

const NOW = 1_000_000_000_000;

test('past times read as elapsed, future times as "in …", and a missing time says so', () => {
  assert.equal(relativeTime(null, NOW), 'time unknown');
  assert.equal(relativeTime(NOW - 10_000, NOW), 'just now');
  assert.equal(relativeTime(NOW - 5 * 60_000, NOW), '5 min ago');
  assert.equal(relativeTime(NOW - 3 * 3_600_000, NOW), '3 h ago');
  assert.equal(relativeTime(NOW - 72 * 3_600_000, NOW), '3 d ago');
  assert.equal(relativeTime(NOW + 10 * 60_000, NOW), 'in 10 min');
  assert.equal(relativeTime(NOW + 5 * 3_600_000, NOW), 'in 5 h');
  assert.equal(relativeTime(NOW + 72 * 3_600_000, NOW), 'in 3 d');
});
