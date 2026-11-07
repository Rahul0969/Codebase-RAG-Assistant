import { dashboardSteps, connectionInfo, modelInfo } from '../utils/status.js';
import { repositoryLabel } from '../utils/repo.js';
import BackendHelp from './BackendHelp.jsx';
import { Spinner, ErrorNotice } from './Feedback.jsx';
import { StatusPill } from './Layout.jsx';

export default function Dashboard({ workspace, onNavigate }) {
  const { health, checkBackend, api, repoPath, indexInfo, repositoryReady } = workspace;
  const steps = dashboardSteps(workspace);
  const connection = connectionInfo(health);
  const model = modelInfo(health);

  return (
    <div className="stack-lg">
      <section className="hero">
        <h2>Understand any codebase, privately</h2>
        <p>
          Ask questions about your code in plain language. Everything runs on your computer: the search index, the language model and your files.
          Answers show the exact code they are based on.
        </p>
      </section>

      {health.state === 'checking' ? <Spinner label="Connecting to the local backend…" /> : null}
      {health.state === 'offline' ? (
        <>
          <BackendHelp baseUrl={api.baseUrl} />
          <button type="button" className="btn" onClick={checkBackend}>Check again</button>
        </>
      ) : null}

      <div className="grid">
        <article className="card stat">
          <h3>Backend</h3>
          <StatusPill tone={connection.tone}>{connection.label}</StatusPill>
          <p className="muted">{health.data ? `Version ${health.data.version}` : api.baseUrl}</p>
        </article>
        <article className="card stat">
          <h3>Language model</h3>
          <StatusPill tone={model.tone}>{model.label}</StatusPill>
          {health.state === 'online' && health.data.ollama.message ? <p className="muted">{health.data.ollama.message}</p> : null}
        </article>
        <article className="card stat">
          <h3>Repository</h3>
          <p><strong>{repositoryLabel(repoPath) || 'None selected'}</strong></p>
          <p className="muted">
            {repositoryReady
              ? `Indexed: ${indexInfo.chunk_count} chunks from ${indexInfo.file_count} files`
              : repoPath.trim() ? 'Not indexed (or not checked yet)' : 'Choose a folder on the Repository page'}
          </p>
        </article>
      </div>

      <section className="card" aria-labelledby="steps-title">
        <h3 id="steps-title">Getting started</h3>
        <ol className="steps">
          {steps.map((step) => (
            <li key={step.id} className={step.done ? 'step is-done' : step.current ? 'step is-current' : 'step'}>
              <span className="step-mark" aria-hidden="true">{step.done ? '✓' : ''}</span>
              <div>
                <strong>{step.title}</strong>
                <p className="muted">{step.detail}</p>
              </div>
              {!step.done && step.current ? (
                <button type="button" className="btn btn-primary btn-small" onClick={() => onNavigate(step.view)}>{step.action}</button>
              ) : null}
            </li>
          ))}
        </ol>
      </section>
      <ErrorNotice error={workspace.index.error} baseUrl={api.baseUrl} />
    </div>
  );
}
