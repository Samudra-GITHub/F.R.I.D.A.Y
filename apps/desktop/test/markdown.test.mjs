import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Markdown } from '../src/components/ui/Markdown.tsx';

const render = (text) => renderToStaticMarkup(React.createElement(Markdown, { text }));

test('model text cannot inject HTML or script', () => {
  const html = render('<script>alert(1)</script> <img src=x onerror=alert(1)> **bold**');
  assert.ok(!html.includes('<script'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(html.includes('<strong>bold</strong>'));
});

test('only http(s) links become anchors', () => {
  const html = render('[ok](https://usgs.gov) [bad](javascript:alert(1)) [file](file:///C:/x)');
  assert.ok(html.includes('href="https://usgs.gov"'));
  assert.ok(!html.includes('href="javascript'), 'javascript: URLs are never linked');
  assert.ok(!html.includes('href="file'));
  assert.ok(html.includes('rel="noopener noreferrer"'));
});

test('fenced code renders as a copyable block and lists render as lists', () => {
  const html = render('Steps:\n\n1. one\n2. two\n\n```python\nprint("hi")\n```');
  assert.ok(html.includes('<ol'));
  assert.ok(html.includes('aria-label="Copy code"'));
  assert.ok(html.includes('print(&quot;hi&quot;)'));
});
