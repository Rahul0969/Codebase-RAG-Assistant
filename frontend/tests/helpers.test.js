import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/services/api.js';
import { describeError } from '../src/services/errors.js';
import { describeEvidence, findChunkForCitation, numberedLines, splitAnswer } from '../src/utils/evidence.js';
import { checkPathInput, initialOperation, operationReducer, repositoryLabel, summarizeFiles } from '../src/utils/repo.js';

test('describeEvidence never shows success for failed or unvalidated answers', () => {
  assert.equal(describeEvidence({ evidence_status: 'verified', validation_passed: true }).tone, 'ok');
  assert.notEqual(describeEvidence({ evidence_status: 'verified', validation_passed: false }).tone, 'ok');
  assert.equal(describeEvidence({ evidence_status: 'invalid_citations', validation_passed: false }).tone, 'bad');
  assert.equal(describeEvidence({ evidence_status: 'insufficient_evidence' }).tone, 'neutral');
  assert.equal(describeEvidence({ evidence_status: 'partially_verified', validation_passed: true }).tone, 'warn');
  assert.equal(describeEvidence({ evidence_status: 'something_new' }).label, 'Unknown status');
});

test('splitAnswer makes citation groups and matches validated citations', () => {
  const citations = [
    { text: 'src/auth.py:15-32', file_path: 'src/auth.py', start_line: 15, end_line: 32, valid: true, reason: 'ok', source_id: 1 },
  ];
  const parts = splitAnswer('Checks the login [src/auth.py:15-32] then [src/x.py:1-2, src/auth.py:20] done [1].', citations);
  assert.deepEqual(parts.map((p) => p.type), ['text', 'citations', 'text', 'citations', 'text']);
  assert.equal(parts[1].items[0].valid, true);
  assert.equal(parts[3].items.length, 2);
  assert.equal(parts[3].items[0].valid, false); // not in the validated list
  assert.equal(parts[4].text, ' done [1].');
});

test('splitAnswer handles plain text, empty input and Windows separators', () => {
  assert.deepEqual(splitAnswer('Just text.', []), [{ type: 'text', text: 'Just text.' }]);
  assert.deepEqual(splitAnswer('', []), []);
  const parts = splitAnswer('See [src\\token.py:L8-L24].', []);
  assert.equal(parts[1].items[0].text, 'src/token.py:8-24');
});

test('findChunkForCitation uses source_id first, then path and overlap', () => {
  const chunks = [
    { source_id: 1, file_path: 'a.py', start_line: 1, end_line: 10, context_start_line: 1, context_end_line: 10 },
    { source_id: 2, file_path: 'b.py', start_line: 5, end_line: 9, context_start_line: 5, context_end_line: 9 },
  ];
  assert.equal(findChunkForCitation({ source_id: 2, file_path: 'a.py', start_line: 1, end_line: 2 }, chunks).source_id, 2);
  assert.equal(findChunkForCitation({ source_id: null, file_path: './b.py', start_line: 6, end_line: 7 }, chunks).source_id, 2);
  assert.equal(findChunkForCitation({ source_id: null, file_path: 'b.py', start_line: 50, end_line: 60 }, chunks), null);
  assert.equal(findChunkForCitation(null, chunks), null);
});

test('numberedLines numbers from the first line and highlights the cited range', () => {
  const lines = numberedLines('a\nb\r\nc', 10, 11, 11);
  assert.deepEqual(lines.map((l) => [l.number, l.text, l.highlighted]), [[10, 'a', false], [11, 'b', true], [12, 'c', false]]);
});

test('describeError gives friendly messages by kind and code', () => {
  const net = describeError(new ApiError({ kind: 'network', message: 'x' }), { baseUrl: 'http://127.0.0.1:8000' });
  assert.match(net.title, /Cannot reach the local backend/);
  assert.match(net.message, /127\.0\.0\.1:8000/);
  const cases = {
    not_indexed: /not indexed/, ollama_unavailable: /Ollama is not running/,
    model_not_found: /not installed/, llm_timeout: /too long/, repository_path_invalid: /cannot be used/,
  };
  for (const [code, pattern] of Object.entries(cases)) {
    const out = describeError(new ApiError({ kind: 'http', status: 400, code, message: 'server says' }));
    assert.match(out.title, pattern);
    assert.equal(out.message, 'server says');
  }
  assert.match(describeError(new ApiError({ kind: 'timeout', message: 'slow' })).title, /too long/);
  assert.match(describeError(new ApiError({ kind: 'invalid_response', message: 'bad' })).title, /Unexpected reply/);
  assert.match(describeError(new Error('boom')).title, /unexpected/i);
  assert.doesNotMatch(JSON.stringify(describeError(new Error('secret stack'))), /secret stack/);
});

test('summarizeFiles counts languages; empty input gives an empty list', () => {
  const files = [{ extension: '.py' }, { extension: '.py' }, { extension: '.js' }, { extension: '.zzz' }];
  assert.deepEqual(summarizeFiles(files).map((s) => [s.extension, s.language, s.count]),
    [['.py', 'Python', 2], ['.js', 'JavaScript', 1], ['.zzz', '.zzz', 1]]);
  assert.deepEqual(summarizeFiles([]), []);
});

test('path input checks', () => {
  assert.match(checkPathInput(''), /Enter/);
  assert.match(checkPathInput('my-project'), /full path/);
  assert.equal(checkPathInput('C:\\Users\\Me\\project'), null);
  assert.equal(checkPathInput('D:/code/app'), null);
  assert.equal(checkPathInput('/home/me/app'), null);
  assert.equal(repositoryLabel('C:\\Users\\Me\\project\\'), 'project');
});

test('operationReducer models loading, success, error and reset', () => {
  let state = operationReducer(initialOperation, { type: 'start' });
  assert.equal(state.status, 'loading');
  state = operationReducer(state, { type: 'success', data: { n: 1 } });
  assert.deepEqual([state.status, state.data.n], ['success', 1]);
  state = operationReducer(state, { type: 'error', error: 'bad' });
  assert.deepEqual([state.status, state.error, state.data], ['error', 'bad', null]);
  assert.equal(operationReducer(state, { type: 'reset' }).status, 'idle');
  assert.equal(operationReducer(state, { type: 'nope' }), state);
});
