import test from 'node:test';
import assert from 'node:assert/strict';
import { describeMicError, isEmbeddedAppBrowser } from '../src/utils/micRecorder.ts';

const CHROME = 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36';
const PANE = 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Claude/4.4212.0 Chrome/152.0.7977.167 Safari/537.36 MSIX';

test('the built-in pane is told to use a real browser; a real browser gets permission steps', () => {
  assert.equal(isEmbeddedAppBrowser(PANE), true);
  assert.equal(isEmbeddedAppBrowser(CHROME), false);
  assert.match(describeMicError({ name: 'NotAllowedError' }, PANE), /Chrome or Edge/);
  const chrome = describeMicError({ name: 'NotAllowedError' }, CHROME);
  assert.match(chrome, /address bar/);
  assert.match(chrome, /Windows Settings/);
});

test('each capture failure gets its own next step', () => {
  assert.match(describeMicError({ name: 'NotFoundError' }, CHROME), /Choose another input/);
  assert.match(describeMicError({ name: 'OverconstrainedError' }, CHROME), /Choose another input/);
  assert.match(describeMicError({ name: 'NotReadableError' }, CHROME), /Another app/);
  assert.match(describeMicError(new Error('boom'), CHROME), /boom/);
});
