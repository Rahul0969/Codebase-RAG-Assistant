// Notifications are derived from real workspace state; nothing is stored or invented.
export function buildNotifications({ health, repoPath, repositoryReady }) {
  const items = [];
  if (health?.state === 'offline') items.push({ id: 'backend', tone: 'bad', title: 'Backend not reachable', body: 'Start the FastAPI backend (start-backend.bat).', target: 'settings' });
  const ollama = health?.data?.ollama;
  if (health?.state === 'online' && ollama && !ollama.reachable) items.push({ id: 'ollama', tone: 'warn', title: 'Ollama is not running', body: 'Questions need Ollama; search still works.', target: 'settings' });
  if (health?.state === 'online' && ollama?.reachable && ollama.model_available === false) items.push({ id: 'model', tone: 'warn', title: 'Model not installed', body: ollama.message || 'Pull the configured model.', target: 'settings' });
  if (health?.state === 'online' && !String(repoPath || '').trim()) items.push({ id: 'repo', tone: 'warn', title: 'No repository selected', body: 'Choose a repository to index.', target: 'repository' });
  else if (health?.state === 'online' && !repositoryReady) items.push({ id: 'index', tone: 'warn', title: 'Repository not indexed', body: 'Index it to enable search and questions.', target: 'repository' });
  return items;
}
