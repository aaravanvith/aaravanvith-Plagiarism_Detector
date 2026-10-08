import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const source = readFileSync(new URL('./src/api.js', import.meta.url), 'utf8');
let version = 0;
const loadApi = () => import('data:text/javascript;base64,' + Buffer.from(
  source.replace('import.meta.env.VITE_API_URL', '"https://example.test/"') + `\n// ${version++}`,
).toString('base64'));

test('waits for healthy JSON, shares readiness, and sends each upload once', async () => {
  const originalFetch = globalThis.fetch;
  const originalTimer = globalThis.setTimeout;
  const calls = [];
  let healthCalls = 0;
  globalThis.setTimeout = (callback) => originalTimer(callback, 0);
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/api/health')) {
      if (++healthCalls === 1) return new Response('<html>Starting</html>');
      return Response.json({ status: 'ok' });
    }
    return Response.json({ report_id: 1 });
  };
  try {
    const api = await loadApi();
    const file = new Blob(['Healthcare hospital patient research']);
    const results = await Promise.all([api.analyzeReport(file), api.analyzeReport(file)]);
    assert.equal(healthCalls, 2);
    assert.equal(calls.filter(([url]) => url.endsWith('/api/analyze')).length, 2);
    assert.ok(calls.every(([url]) => url.startsWith('https://example.test/api/')));
    assert.deepEqual(results, [{ report_id: 1 }, { report_id: 1 }]);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalTimer;
  }
});

test('network failure after readiness gives a useful error without retrying POST', async () => {
  const originalFetch = globalThis.fetch;
  let uploads = 0;
  globalThis.fetch = async (url) => {
    if (url.endsWith('/api/health')) return Response.json({ status: 'ok' });
    uploads++;
    throw new TypeError('Failed to fetch');
  };
  try {
    const api = await loadApi();
    await assert.rejects(api.analyzeReport(new Blob(['report'])), /Unable to reach the backend/);
    assert.equal(uploads, 1);
  } finally { globalThis.fetch = originalFetch; }
});
