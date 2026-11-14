import { dashboardSteps, connectionInfo, modelInfo } from '../utils/status.js';
import { repositoryLabel, summarizeFiles } from '../utils/repo.js';
import BackendHelp from './BackendHelp.jsx';
import { Spinner, ErrorNotice } from './Feedback.jsx';
import { StatusPill } from './Layout.jsx';

function Metric({ label, value, note, icon, accent }) {
  return <article className={`metric-card metric-${accent}`}><div className="metric-top"><span>{label}</span><span className="metric-icon" aria-hidden="true">{icon}</span></div><strong>{value}</strong><small>{note}</small></article>;
}

export default function Dashboard({ workspace, onNavigate }) {
  const { health, checkBackend, api, repoPath, indexInfo, repositoryReady, inspect, index, search, asks } = workspace;
  const steps = dashboardSteps(workspace);
  const connection = connectionInfo(health);
  const model = modelInfo(health, workspace.modelRouting, workspace.lastUsedModel);
  const languageSummary = summarizeFiles(inspect.data?.files || []);
  const languages = languageSummary.slice(0, 5);
  const totalLanguageFiles = languageSummary.reduce((sum, item) => sum + item.count, 0);
  const indexedFiles = indexInfo?.file_count ?? inspect.data?.file_count ?? null;
  const chunks = indexInfo?.chunk_count ?? null;
  const recent = [
    index.status === 'success' ? { icon: '▦', title: 'Repository index updated', detail: `${chunks ?? index.data?.chunk_count ?? 'Local'} chunks indexed`, tone: 'blue' } : null,
    inspect.status === 'success' ? { icon: '⌕', title: 'Repository inspection completed', detail: `${inspect.data?.file_count ?? 0} files discovered`, tone: 'cyan' } : null,
    search.status === 'success' ? { icon: '⌘', title: 'Code search completed', detail: `${search.data?.matches?.length ?? 0} matching code sections`, tone: 'purple' } : null,
    asks.some((item) => item.status === 'done') ? { icon: '✳', title: 'AI question answered', detail: 'Evidence-backed response available', tone: 'green' } : null,
  ].filter(Boolean);

  return (
    <div className="dashboard stack-lg">
      <section className="dashboard-heading">
        <div><p className="eyebrow">CODE INTELLIGENCE WORKSPACE</p><h2>Understand your codebase<span>.</span></h2><p>Search deeper. Ask smarter questions. See how everything connects.</p></div>
        <div className="heading-status"><span className="status-orbit" /><span>LOCAL AI WORKSPACE</span></div>
      </section>

      {health.state === 'checking' ? <Spinner label="Connecting to the local backend…" /> : null}
      {health.state === 'offline' ? <><BackendHelp baseUrl={api.baseUrl} /><button type="button" className="btn" onClick={checkBackend}>Check connection again</button></> : null}

      <section className="metrics-grid" aria-label="Repository metrics">
        <Metric label="SOURCE FILES" value={indexedFiles == null ? '—' : indexedFiles.toLocaleString()} note={inspect.data ? 'Discovered in repository' : 'Inspect a repository to begin'} icon="▤" accent="blue" />
        <Metric label="INDEXED CHUNKS" value={chunks == null ? '—' : chunks.toLocaleString()} note={repositoryReady ? 'Available for semantic search' : 'Build the local search index'} icon="▦" accent="cyan" />
        <Metric label="LANGUAGES FOUND" value={inspect.data ? languageSummary.length.toString().padStart(2, '0') : '—'} note={inspect.data ? 'File types detected' : 'Awaiting repository scan'} icon="⌘" accent="violet" />
        <Metric label="AI MODEL" value={health.state !== 'online' ? '—' : health.data?.ollama?.reachable ? (model.name || 'Ready') : 'Setup'} note={model.mode === 'AUTO' ? 'Automatic local model routing' : model.mode === 'MANUAL' ? 'Manually selected local model' : model.label} icon="✳" accent="green" />
      </section>

      <section className="dashboard-main-grid">
        <article className="panel repository-overview">
          <div className="panel-heading"><div><p className="eyebrow">YOUR WORKSPACE</p><h3>Repository overview</h3></div><StatusPill tone={repositoryReady ? 'ok' : 'warn'}>{repositoryReady ? 'Indexed' : 'Not indexed'}</StatusPill></div>
          <div className="repo-summary"><div className="repo-symbol">⌘</div><div className="repo-summary-copy"><strong>{repositoryLabel(repoPath) || 'No repository selected'}</strong><small>{repoPath || 'Choose a local project folder to begin exploring'}</small></div><button type="button" className="text-action" onClick={() => onNavigate('repository')}>{repoPath ? 'Manage repository' : 'Connect repository'} <span>↗</span></button></div>
          <div className="overview-divider" />
          <div className="overview-bottom">
            <div className="index-status"><span className="index-ring"><span>{repositoryReady ? '✓' : '＋'}</span></span><div><strong>{repositoryReady ? 'Index is ready' : 'Ready when you are'}</strong><small>{repositoryReady ? `${chunks?.toLocaleString() ?? 'Your'} code chunks are searchable` : 'Inspect and index a repository to unlock AI features'}</small></div></div>
            <div className="overview-actions"><button type="button" className="btn btn-primary" onClick={() => onNavigate('repository')}>{repositoryReady ? 'View repository' : 'Get started'} <span>→</span></button><button type="button" className="btn btn-quiet" onClick={() => onNavigate('settings')}>System settings</button></div>
          </div>
        </article>

        <article className="panel language-panel">
          <div className="panel-heading"><div><p className="eyebrow">CODE COMPOSITION</p><h3>Languages detected</h3></div><span className="panel-icon">◉</span></div>
          {languages.length ? <div className="language-list">{languages.map((item, index) => <div className="language-row" key={item.extension}><div className="language-label"><span className={`language-dot language-${index % 5}`} /><strong>{item.language}</strong><small>{item.count}</small></div><div className="language-track"><span className={`language-fill language-fill-${index % 5}`} style={{ width: `${Math.max(2, totalLanguageFiles ? item.count / totalLanguageFiles * 100 : 0)}%` }} /></div></div>)}</div> : <div className="panel-empty"><span>◌</span><p>Language insights appear after repository inspection.</p><button type="button" className="text-action" onClick={() => onNavigate('repository')}>Inspect repository →</button></div>}
        </article>
      </section>

      <section className="dashboard-lower-grid">
        <article className="panel quick-panel"><div className="panel-heading"><div><p className="eyebrow">JUMP BACK IN</p><h3>Quick actions</h3></div><span className="panel-icon">⌁</span></div><div className="quick-actions">
          <button type="button" className="quick-action" onClick={() => onNavigate('search')}><span className="quick-icon quick-blue">⌕</span><span><strong>Search code</strong><small>Find logic by meaning</small></span><b>↗</b></button>
          <button type="button" className="quick-action" onClick={() => onNavigate('ask')}><span className="quick-icon quick-violet">✳</span><span><strong>Ask the codebase</strong><small>Get answers with evidence</small></span><b>↗</b></button>
          <button type="button" className="quick-action" onClick={() => onNavigate('reports')}><span className="quick-icon quick-cyan">▧</span><span><strong>Generate report</strong><small>Explore repository health</small></span><b>↗</b></button>
          <button type="button" className="quick-action" onClick={() => onNavigate('impact')}><span className="quick-icon quick-green">⌁</span><span><strong>Analyze changes</strong><small>Trace affected files</small></span><b>↗</b></button>
        </div></article>

        <article className="panel activity-panel"><div className="panel-heading"><div><p className="eyebrow">WORKSPACE SIGNAL</p><h3>Recent activity</h3></div><span className="live-indicator"><i /> LIVE STATUS</span></div>
          {recent.length ? <ul className="activity-list">{recent.map((item) => <li key={item.title}><span className={`activity-icon activity-${item.tone}`}>{item.icon}</span><span><strong>{item.title}</strong><small>{item.detail}</small></span><b>Done</b></li>)}</ul> : <div className="panel-empty activity-empty"><span>◷</span><p>Your recent repository operations will appear here.</p></div>}
          <div className="activity-footer"><span>Backend</span><StatusPill tone={connection.tone}>{connection.label}</StatusPill><span>Model</span><StatusPill tone={model.tone}>{model.label}</StatusPill></div>
        </article>
      </section>

      <section className="getting-started panel"><div className="panel-heading"><div><p className="eyebrow">FIRST-RUN CHECKLIST</p><h3>Set up your workspace</h3></div><span className="muted">{steps.filter((step) => step.done).length} / {steps.length} complete</span></div><ol className="steps">{steps.map((step) => <li key={step.id} className={step.done ? 'step is-done' : step.current ? 'step is-current' : 'step'}><span className="step-mark" aria-hidden="true">{step.done ? '✓' : ''}</span><div><strong>{step.title}</strong><p className="muted">{step.detail}</p></div>{!step.done && step.current ? <button type="button" className="btn btn-primary btn-small" onClick={() => onNavigate(step.view)}>{step.action} →</button> : null}</li>)}</ol></section>
      <ErrorNotice error={workspace.index.error} baseUrl={api.baseUrl} />
      <footer className="dashboard-footer"><span>CODEBASE RAG ASSISTANT</span><span>LOCAL-FIRST · PRIVATE · EVIDENCE-BASED</span><span>Built for developers <b>✳</b></span></footer>
    </div>
  );
}
