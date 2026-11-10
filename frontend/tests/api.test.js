import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, createApiClient, resolveBaseUrl, shouldDeclareLoopback } from '../src/services/api.js';

const HEALTH = { status: 'ok', version: '0.9.0', ollama: { reachable: true }, embedding: {}, chromadb: {} };

function fakeResponse(body, { status = 200, headers = {} } = {}) {
  const text = typeof body === 'string' ? body : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => headers[name.toLowerCase()] ?? null },
    text: async () => text,
  };
}

function client(fetchImpl, extra = {}) {
  return createApiClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl, pageHostname: '127.0.0.1', ...extra });
}

test('resolveBaseUrl normalizes and validates', () => {
  assert.equal(resolveBaseUrl('http://127.0.0.1:8000///'), 'http://127.0.0.1:8000');
  assert.equal(resolveBaseUrl(''), 'http://127.0.0.1:8000');
  assert.throws(() => resolveBaseUrl('not a url'), (e) => e.kind === 'config');
  assert.throws(() => resolveBaseUrl('ftp://localhost'), (e) => e.kind === 'config');
});

test('health request uses the configured base URL and omits credentials', async () => {
  let seen;
  const api = client(async (url, init) => {
    seen = { url, init };
    return fakeResponse(HEALTH);
  });
  const result = await api.health();
  assert.equal(result.status, 'ok');
  assert.equal(seen.url, 'http://127.0.0.1:8000/health');
  assert.equal(seen.init.credentials, 'omit');
  assert.equal(seen.init.targetAddressSpace, undefined);
});

test('POST sends JSON body with snake_case fields', async () => {
  let seen;
  const api = client(async (url, init) => {
    seen = { url, body: JSON.parse(init.body), type: init.headers['Content-Type'] };
    return fakeResponse({ repository_name: 'r', file_count: 0, files: [] });
  });
  await api.inspect('C:\\repo');
  assert.deepEqual(seen.body, { repository_path: 'C:\\repo' });
  assert.equal(seen.type, 'application/json');
  assert.equal(seen.url, 'http://127.0.0.1:8000/repository/inspect');
});

test('ask requests source text and passes top_k', async () => {
  let body;
  const answer = {
    answer: 'x', evidence_status: 'verified', validation_passed: true, citations: [],
    retrieved_chunks: [], model: 'qwen2.5:3b',
  };
  const api = client(async (_url, init) => {
    body = JSON.parse(init.body);
    return fakeResponse(answer);
  });
  const result = await api.ask('C:\\repo', 'Where?', { topK: 3 });
  assert.equal(body.include_source_text, true);
  assert.equal(body.top_k, 3);
  assert.equal(result.model, 'qwen2.5:3b');
});

test('HTTP error exposes detail string, status and error code header', async () => {
  const api = client(async () =>
    fakeResponse({ detail: 'No index exists for this repository.' }, { status: 400, headers: { 'x-error-code': 'not_indexed' } }));
  await assert.rejects(api.search('C:\\repo', 'q'), (e) => {
    assert.ok(e instanceof ApiError);
    return e.kind === 'http' && e.status === 400 && e.code === 'not_indexed' && /No index/.test(e.message);
  });
});

test('422 validation list is summarized', async () => {
  const detail = [{ loc: ['body', 'question'], msg: 'String should have at least 1 character' }];
  const api = client(async () => fakeResponse({ detail }, { status: 422 }));
  await assert.rejects(api.ask('C:\\repo', ''), (e) => e.status === 422 && /question/.test(e.message));
});

test('connection failure becomes a network error', async () => {
  const api = client(async () => {
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(api.health(), (e) => e.kind === 'network');
});

test('slow backend becomes a timeout error', async () => {
  const api = client(
    (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      }),
    { timeouts: { health: 20, inspect: 20, status: 20, index: 20, search: 20, ask: 20 } },
  );
  await assert.rejects(api.health(), (e) => e.kind === 'timeout');
});

test('unexpected or non-JSON replies are rejected as invalid_response', async () => {
  for (const body of ['<html>oops</html>', { status: 1 }, '[]']) {
    const api = client(async () => fakeResponse(body));
    await assert.rejects(api.health(), (e) => e.kind === 'invalid_response');
  }
});

test('non-JSON error body still gives a readable message', async () => {
  const api = client(async () => fakeResponse('Internal Server Error', { status: 500 }));
  await assert.rejects(api.health(), (e) => e.kind === 'http' && /HTTP 500/.test(e.message));
});

test('hosted pages declare the loopback address space; local pages do not', async () => {
  assert.equal(shouldDeclareLoopback('http://127.0.0.1:8000', 'my-app.vercel.app'), true);
  assert.equal(shouldDeclareLoopback('http://127.0.0.1:8000', 'localhost'), false);
  assert.equal(shouldDeclareLoopback('https://api.example.com', 'my-app.vercel.app'), false);
  let init;
  const api = createApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    pageHostname: 'my-app.vercel.app',
    fetchImpl: async (_url, i) => {
      init = i;
      return fakeResponse(HEALTH);
    },
  });
  await api.health();
  assert.equal(init.targetAddressSpace, 'loopback');
});

test('report generation sends repository, format and local AI option', async () => {
  let seen;
  const payload = {
    report_id: 'a'.repeat(32), repository_name: 'demo', generated_at: '2026-11-09T00:00:00+00:00',
    format: 'html', filename: 'report.html', mime_type: 'text/html', content: '<html></html>',
    summary_source: 'deterministic',
  };
  const api = client(async (url, init) => {
    seen = { url, body: JSON.parse(init.body) };
    return fakeResponse(payload);
  });
  const result = await api.generateReport('C:\\repo', 'html', false);
  assert.equal(seen.url, 'http://127.0.0.1:8000/api/reports/generate');
  assert.deepEqual(seen.body, { repository_path: 'C:\\repo', format: 'html', use_ai_summary: false });
  assert.equal(result.report_id, payload.report_id);
});

test('report history and report content endpoints validate their response shapes', async () => {
  const api = client(async (url) => {
    if (url.endsWith('/api/reports')) return fakeResponse({ reports: [] });
    return fakeResponse({ report_id: 'b'.repeat(32), filename: 'report.md', mime_type: 'text/markdown', content: '# Report' });
  });
  assert.deepEqual(await api.listReports(), { reports: [] });
  const report = await api.getReport('b'.repeat(32));
  assert.equal(report.content, '# Report');
});
