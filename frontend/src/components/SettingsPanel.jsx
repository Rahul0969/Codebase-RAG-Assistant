import { useEffect, useState } from 'react';
import { isLoopbackHost } from '../services/api.js';
import { connectionInfo, modelInfo } from '../utils/status.js';
import BackendHelp from './BackendHelp.jsx';
import { StatusPill } from './Layout.jsx';

function Row({ label, children }) {
  return <div className="setting-row"><dt>{label}</dt><dd>{children}</dd></div>;
}

export default function SettingsPanel({ workspace }) {
  const { health, checkBackend, api, setRepoPath, repoPath, refreshModelRouting } = workspace;
  const data = health.data;
  const connection = connectionInfo(health);
  const model = modelInfo(health);
  const hosted = !isLoopbackHost(globalThis.location?.hostname ?? 'localhost');
  const [registry, setRegistry] = useState({ models: [], preferences: { mode: 'AUTO', model: '' } });
  const [mode, setMode] = useState('AUTO');
  const [selectedModel, setSelectedModel] = useState('');
  const [loadingModels, setLoadingModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [modelError, setModelError] = useState('');

  async function loadModels() {
    setLoadingModels(true); setModelError('');
    try {
      const result = await api.listModels();
      setRegistry(result);
      setMode(result.preferences.mode || 'AUTO');
      setSelectedModel(result.preferences.model || result.models[0]?.name || '');
    } catch (error) { setModelError(error.message || 'Could not load local Ollama models.'); }
    finally { setLoadingModels(false); }
  }
  useEffect(() => { loadModels(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveRouting() {
    setSaving(true); setNotice(''); setModelError('');
    try {
      const result = await api.saveModelPreferences(mode, mode === 'MANUAL' ? selectedModel : '');
      setRegistry((old) => ({ ...old, preferences: result.preferences }));
      await refreshModelRouting();
      setNotice(`Saved ${result.preferences.mode} routing preferences on this computer.`);
    } catch (error) { setModelError(error.message || 'Could not save model preferences.'); }
    finally { setSaving(false); }
  }

  return (
    <div className="stack-lg">
      <section className="card" aria-labelledby="settings-title">
        <h2 id="settings-title">Settings</h2>
        <p className="muted">Backend and repository access remain controlled by the local backend. Change model routing here; preferences are stored locally.</p>
        <dl className="settings">
          <Row label="Backend address"><code>{api.baseUrl}</code> <small className="muted">(VITE_API_BASE_URL)</small></Row>
          <Row label="Connection"><StatusPill tone={connection.tone}>{connection.label}</StatusPill></Row>
          <Row label="This page is">{hosted ? 'hosted online (it connects to your local backend)' : 'running on this computer'}</Row>
          {data ? <>
            <Row label="Backend version">{data.version}</Row>
            <Row label="Ollama"><StatusPill tone={model.tone}>{data.ollama.reachable ? 'Running' : 'Not running'}</StatusPill></Row>
            <Row label="Configured model">{data.ollama.model ?? 'not configured'}{data.ollama.model_available === false ? ' (not downloaded)' : ''}</Row>
            <Row label="Embedding model">{data.embedding.model} <small className="muted">{data.embedding.installed ? 'package installed; loads on first use' : 'package not installed'}</small></Row>
            <Row label="Vector database">ChromaDB {data.chromadb.installed ? '(installed)' : '(not installed)'}</Row>
            <Row label="Where data lives">On this computer, in <code>backend\data\chroma_db</code>. Nothing is uploaded.</Row>
          </> : null}
        </dl>
        <div className="row"><button type="button" className="btn" onClick={checkBackend}>Check connection</button><button type="button" className="btn btn-ghost" onClick={() => setRepoPath('')} disabled={!repoPath}>Forget saved folder path</button></div>
        <p className="muted">The folder path is remembered only in this browser (local storage). It is never sent anywhere except your own backend.</p>
      </section>

      <section className="card stack-md" aria-labelledby="model-routing-title">
        <div className="row row-between"><div><h2 id="model-routing-title">Intelligent model routing</h2><p className="muted">Choose automatic resource-aware selection or pin one installed local Ollama model.</p></div><button type="button" className="btn btn-ghost" onClick={loadModels} disabled={loadingModels}>{loadingModels ? 'Refreshing…' : 'Refresh models'}</button></div>
        <div className="choice-grid">
          <label className={`choice-card ${mode === 'AUTO' ? 'selected' : ''}`}><input type="radio" name="routing-mode" value="AUTO" checked={mode === 'AUTO'} onChange={() => setMode('AUTO')} /><span><strong>AUTO</strong><small>Classifies each request and selects a suitable installed model using available memory estimates.</small></span></label>
          <label className={`choice-card ${mode === 'MANUAL' ? 'selected' : ''}`}><input type="radio" name="routing-mode" value="MANUAL" checked={mode === 'MANUAL'} onChange={() => setMode('MANUAL')} /><span><strong>MANUAL</strong><small>Always use the selected installed local model.</small></span></label>
        </div>
        {mode === 'MANUAL' ? <label className="field"><span>Installed Ollama model</span><select className="input" value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} disabled={!registry.models.length}><option value="">Select a model</option>{registry.models.map((item) => <option key={item.name} value={item.name}>{item.name}{item.parameter_size ? ` · ${item.parameter_size}` : ''}</option>)}</select></label> : null}
        <div className="row row-between"><span className="muted">{registry.models.length} locally installed model(s) detected</span><button type="button" className="btn btn-primary" onClick={saveRouting} disabled={saving || loadingModels || (mode === 'MANUAL' && !selectedModel)}>{saving ? 'Saving…' : 'Save routing preferences'}</button></div>
        {notice ? <p className="success-text" role="status">{notice}</p> : null}
        {modelError ? <p className="error-text" role="alert">{modelError}</p> : null}
        {registry.models.length ? <div className="model-list"><strong>Available local models</strong>{registry.models.map((item) => <div className="model-row" key={item.name}><code>{item.name}</code><span className="muted">{item.parameter_size || item.family || 'Ollama model'}</span></div>)}</div> : <p className="muted">No models listed yet. Make sure Ollama is running, then refresh. For example, install a model with <code>ollama pull qwen2.5:1.5b</code>.</p>}
      </section>
      {health.state === 'offline' ? <BackendHelp baseUrl={api.baseUrl} /> : null}
    </div>
  );
}
