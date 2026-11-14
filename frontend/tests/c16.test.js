import test from 'node:test';
import assert from 'node:assert/strict';
import { facets, fileExt, filterMatches, topDirectory } from '../src/utils/search.js';
import { buildImpactGraph, riskAssessment } from '../src/utils/impactGraph.js';
import { buildNotifications } from '../src/utils/notifications.js';

const matches = [
  { file_path: 'backend/app/main.py', language: 'python' },
  { file_path: 'frontend/src/App.jsx', language: 'javascript' },
  { file_path: 'README.md', language: 'markdown' },
];
test('file helpers', () => { assert.equal(fileExt('a/B.PY'), '.py'); assert.equal(fileExt('Makefile'), ''); assert.equal(topDirectory('README.md'), '(root)'); assert.equal(topDirectory('x\\y.py'), 'x'); });
test('facets and filters', () => {
  assert.deepEqual(facets(matches).extensions, ['.jsx', '.md', '.py']);
  assert.equal(filterMatches(matches, { language: 'python' }).length, 1);
  assert.equal(filterMatches(matches, { directory: 'frontend', extension: '.jsx' }).length, 1);
  assert.equal(filterMatches(matches, { directory: 'frontend', extension: '.py' }).length, 0);
  assert.equal(filterMatches(matches, {}).length, 3);
});
const result = { changed_files: ['a.py'], direct_dependents: ['b.py'], transitive_dependents: ['c.py'], related_tests: [], cycles: [],
  dependency_edges: [{ importer: 'b.py', dependency: 'a.py' }, { importer: 'c.py', dependency: 'b.py', confidence: 'inferred' }, { importer: 'z.py', dependency: 'a.py' }] };
test('impact graph keeps only displayed, directed edges', () => {
  const g = buildImpactGraph(result);
  assert.equal(g.nodes.length, 3);
  assert.deepEqual(g.edges.map((e) => [e.from, e.to, e.inferred]), [['a.py', 'b.py', false], ['b.py', 'c.py', true]]);
});
test('graph caps columns', () => {
  const many = { changed_files: ['a'], direct_dependents: Array.from({ length: 12 }, (_, i) => `d${i}`) };
  const g = buildImpactGraph(many); assert.equal(g.columns[1].hidden, 4); assert.equal(g.nodes.filter((n) => n.kind === 'direct').length, 8);
});
test('risk levels', () => {
  assert.equal(riskAssessment({ direct_dependents: [], transitive_dependents: [], related_tests: ['t'] }).level, 'low');
  assert.equal(riskAssessment({ direct_dependents: ['b'], transitive_dependents: [], related_tests: [] }).level, 'medium');
  assert.equal(riskAssessment({ direct_dependents: [], transitive_dependents: [], cycles: [{}], related_tests: ['t'] }).level, 'high');
  assert.equal(riskAssessment({ direct_dependents: Array(15).fill('x'), transitive_dependents: [], related_tests: ['t'] }).level, 'high');
  assert.equal(riskAssessment(null).level, 'low');
});
test('notifications reflect real state', () => {
  assert.equal(buildNotifications({ health: { state: 'offline' }, repoPath: '', repositoryReady: false })[0].id, 'backend');
  const ok = { state: 'online', data: { ollama: { reachable: true, model_available: true } } };
  assert.equal(buildNotifications({ health: ok, repoPath: '/r', repositoryReady: true }).length, 0);
  assert.equal(buildNotifications({ health: ok, repoPath: '/r', repositoryReady: false })[0].id, 'index');
  assert.equal(buildNotifications({ health: ok, repoPath: '', repositoryReady: false })[0].id, 'repo');
  assert.equal(buildNotifications({ health: { state: 'online', data: { ollama: { reachable: false } } }, repoPath: '/r', repositoryReady: true })[0].id, 'ollama');
});
