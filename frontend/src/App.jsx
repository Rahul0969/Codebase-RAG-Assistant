import AskPanel from './components/AskPanel.jsx';
import RepositoryPanel from './components/RepositoryPanel.jsx';
import SearchPanel from './components/SearchPanel.jsx';
import { useWorkspace } from './hooks/useWorkspace.js';

export default function App() {
  const workspace = useWorkspace();
  const { health, checkBackend, api } = workspace;
  return (
    <main className="page">
      <h1>Codebase RAG Assistant</h1>
      <p className="status-line" role="status">
        Backend: {health.state === 'online' ? 'connected' : health.state === 'checking' ? 'connecting…' : 'not reachable'}
        {' '}({api.baseUrl}) <button type="button" className="btn btn-small" onClick={checkBackend}>Check again</button>
      </p>
      <RepositoryPanel workspace={workspace} />
      <SearchPanel workspace={workspace} />
      <AskPanel workspace={workspace} />
    </main>
  );
}
