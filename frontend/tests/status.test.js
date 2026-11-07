import test from 'node:test';
import assert from 'node:assert/strict';
import { connectionInfo, dashboardSteps, modelInfo } from '../src/utils/status.js';

const online = (ollama) => ({ state: 'online', data: { ollama }, error: null });

test('connectionInfo covers connecting, connected and disconnected', () => {
  assert.equal(connectionInfo({ state: 'checking' }).label, 'Connecting…');
  assert.equal(connectionInfo({ state: 'online' }).tone, 'ok');
  assert.equal(connectionInfo({ state: 'offline' }).tone, 'bad');
});

test('modelInfo reports unknown, Ollama down, model missing and ready', () => {
  assert.equal(modelInfo({ state: 'offline' }).label, 'Model: unknown');
  assert.equal(modelInfo(online({ reachable: false })).tone, 'bad');
  assert.equal(modelInfo(online({ reachable: true, model: 'qwen2.5:3b', model_available: false })).label, 'Model not installed');
  const ready = modelInfo(online({ reachable: true, model: 'qwen2.5:3b', model_available: true }));
  assert.deepEqual([ready.tone, ready.label], ['ok', 'Model: qwen2.5:3b']);
});

test('dashboardSteps marks real progress and exactly one current step', () => {
  const base = {
    health: { state: 'offline' }, repoPath: '', inspect: { status: 'idle' }, repositoryReady: false,
    asks: [], search: { status: 'idle' },
  };
  let steps = dashboardSteps(base);
  assert.deepEqual(steps.map((s) => s.done), [false, false, false, false]);
  assert.equal(steps.filter((s) => s.current).length, 1);
  assert.equal(steps[0].current, true);

  steps = dashboardSteps({ ...base, health: { state: 'online' }, repoPath: 'C:\\x', inspect: { status: 'success' } });
  assert.deepEqual(steps.map((s) => s.done), [true, true, false, false]);
  assert.equal(steps.find((s) => s.current).id, 'index');

  steps = dashboardSteps({ ...base, health: { state: 'online' }, inspect: { status: 'success' }, repositoryReady: true,
    asks: [{ status: 'done' }] });
  assert.equal(steps.every((s) => s.done), true);
  assert.equal(steps.some((s) => s.current), false);
});
