// Pure helpers that decide what status text and tone the layout shows.

export function connectionInfo(health) {
  if (health.state === 'online') return { tone: 'ok', label: 'Backend connected' };
  if (health.state === 'offline') return { tone: 'bad', label: 'Backend disconnected' };
  return { tone: 'neutral', label: 'Connecting…' };
}

export function modelInfo(health, modelRouting = null, lastUsedModel = '') {
  if (health.state !== 'online') return { tone: 'neutral', label: 'Model: unknown', name: 'Unknown', mode: '—' };
  const ollama = health.data?.ollama;
  if (!ollama?.reachable) return { tone: 'bad', label: 'Ollama not running', name: 'Unavailable', mode: '—' };
  const preferences = modelRouting?.preferences;
  if (preferences?.mode === 'MANUAL' && preferences.model) {
    return { tone: 'ok', label: `Model: ${preferences.model}`, name: preferences.model, mode: 'MANUAL' };
  }
  if (preferences?.mode === 'AUTO') {
    const name = lastUsedModel ? `AUTO · ${lastUsedModel}` : 'AUTO routing';
    return { tone: 'ok', label: `Model: ${name}`, name, mode: 'AUTO' };
  }
  if (ollama.model_available === false) return { tone: 'warn', label: 'Model not installed', name: 'Not installed', mode: '—' };
  return { tone: 'ok', label: `Model: ${ollama.model}`, name: ollama.model, mode: '—' };
}

/** Steps of the first-run checklist, each with a real "done" state. */
export function dashboardSteps({ health, repoPath, inspect, repositoryReady, asks, search }) {
  const online = health.state === 'online';
  const steps = [
    { id: 'backend', title: 'Start the local backend', done: online,
      detail: online ? 'Connected.' : 'Run start.bat on this computer, then use "Check again".', view: 'settings', action: 'Open settings' },
    { id: 'repository', title: 'Choose and inspect a repository', done: inspect.status === 'success',
      detail: repoPath.trim() ? 'Folder chosen. Inspect it to see its files.' : 'Type the full path of a project folder.', view: 'repository', action: 'Open repository' },
    { id: 'index', title: 'Index the repository', done: repositoryReady,
      detail: repositoryReady ? 'The local search index is ready.' : 'Builds the local search index (first run downloads a small model).', view: 'repository', action: 'Open repository' },
    { id: 'use', title: 'Search the code or ask a question', done: asks.some((a) => a.status === 'done') || search.status === 'success',
      detail: repositoryReady ? 'Ready: search for code or ask in plain language.' : 'Available after indexing.', view: 'ask', action: 'Ask the codebase' },
  ];
  const current = steps.find((s) => !s.done)?.id ?? null;
  return steps.map((s) => ({ ...s, current: s.id === current }));
}
