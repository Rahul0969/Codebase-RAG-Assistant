import { isLoopbackHost } from '../services/api.js';
import { connectionInfo, modelInfo } from '../utils/status.js';
import BackendHelp from './BackendHelp.jsx';
import { StatusPill } from './Layout.jsx';

function Row({ label, children }) {
  return (
    <div className="setting-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function SettingsPanel({ workspace }) {
  const { health, checkBackend, api, setRepoPath, repoPath } = workspace;
  const data = health.data;
  const connection = connectionInfo(health);
  const model = modelInfo(health);
  const hosted = !isLoopbackHost(globalThis.location?.hostname ?? 'localhost');

  return (
    <div className="stack-lg">
      <section className="card" aria-labelledby="settings-title">
        <h2 id="settings-title">Settings</h2>
        <p className="muted">
          These values are read-only here on purpose: a web page should not be able to change what your backend may access. Edit
          {' '}<code>backend\.env</code> or <code>frontend\.env.local</code> and restart to change them.
        </p>
        <dl className="settings">
          <Row label="Backend address"><code>{api.baseUrl}</code> <small className="muted">(VITE_API_BASE_URL)</small></Row>
          <Row label="Connection"><StatusPill tone={connection.tone}>{connection.label}</StatusPill></Row>
          <Row label="This page is">{hosted ? 'hosted online (it connects to your local backend)' : 'running on this computer'}</Row>
          {data ? (
            <>
              <Row label="Backend version">{data.version}</Row>
              <Row label="Ollama"><StatusPill tone={model.tone}>{data.ollama.reachable ? 'Running' : 'Not running'}</StatusPill></Row>
              <Row label="Language model">{data.ollama.model ?? 'not configured'}{data.ollama.model_available === false ? ' (not downloaded)' : ''}</Row>
              <Row label="Embedding model">
                {data.embedding.model}{' '}
                <small className="muted">{data.embedding.installed ? 'package installed; loads on first use' : 'package not installed'}</small>
              </Row>
              <Row label="Vector database">ChromaDB {data.chromadb.installed ? '(installed)' : '(not installed)'}</Row>
              <Row label="Where data lives">On this computer, in <code>backend\data\chroma_db</code>. Nothing is uploaded.</Row>
            </>
          ) : null}
        </dl>
        <div className="row">
          <button type="button" className="btn" onClick={checkBackend}>Check connection</button>
          <button type="button" className="btn btn-ghost" onClick={() => setRepoPath('')} disabled={!repoPath}>
            Forget saved folder path
          </button>
        </div>
        <p className="muted">The folder path is remembered only in this browser (local storage). It is not a secret and is never sent anywhere except your own backend.</p>
      </section>
      {health.state === 'offline' ? <BackendHelp baseUrl={api.baseUrl} /> : null}
    </div>
  );
}
