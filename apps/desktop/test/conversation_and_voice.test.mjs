import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { VoiceProvider } from '../src/context/VoiceProvider.tsx';
import { AppProvider } from '../src/context/AppProvider.tsx';
import { AssistantView } from '../src/components/views/AssistantView.tsx';
import { SettingsView } from '../src/components/views/SettingsView.tsx';
import { TEST_PHRASES } from '../src/components/settings/VoiceLab.tsx';

const render = (view) =>
  renderToStaticMarkup(
    React.createElement(VoiceProvider, null, React.createElement(AppProvider, null, React.createElement(view)))
  );

test('Assistant view renders the composer, push-to-talk, and real prompt suggestions only', () => {
  const html = render(AssistantView);
  assert.ok(html.includes('aria-label="Start push-to-talk recording"'));
  assert.ok(html.includes('aria-label="Message"'));
  assert.ok(html.includes('What time is it?'));
  assert.ok(!/Simulate|Barge-In|mock/i.test(html), 'no simulated voice flows in production UI');
  assert.ok(!/Match: \d+%/.test(html), 'confidence is never labelled as a match/accuracy score');
});

test('Settings view shows wake word disabled, local-only recordings, and the voice lab', () => {
  const html = render(SettingsView);
  assert.ok(html.includes('Wake word'));
  assert.ok(html.includes('Disabled'));
  assert.ok(html.includes('Local only'));
  assert.ok(html.includes('Voice lab'));
  assert.ok(html.includes('Hey Wednesday, what time is it?'));
  assert.equal(TEST_PHRASES.length, 5);
  assert.ok(TEST_PHRASES.includes('Find the latest earthquakes.'));
  assert.ok(TEST_PHRASES.includes('Open my settings.'));
});

test('Settings view never reports the model as reachable before health is known', () => {
  const html = render(SettingsView);
  assert.ok(!html.includes('>Reachable<'), 'no optimistic status on first render');
});
