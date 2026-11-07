import { useEffect, useState } from 'react';
import { ErrorNotice, Spinner } from './Feedback.jsx';
import { summarizeFiles } from '../utils/repo.js';

function Elapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return <span>{seconds}s elapsed</span>;
}

export default function RepositoryPanel({ workspace }) {
  const { repoPath, setRepoPath, pathError, inspect, inspectRepository, index, indexRepository, indexInfo, api, health } = workspace;
  const online = health.state === 'online';
  const inspecting = inspect.status === 'loading';
  const indexing = index.status === 'loading';
  const summary = inspect.data ? summarizeFiles(inspect.data.files) : [];

  return (
    <section className="card" aria-labelledby="repo-title">
      <h2 id="repo-title">Repository</h2>
      <p className="muted">
        A web page cannot browse your disk, so type the full path of a project folder on the computer that runs the backend.
      </p>
      <label htmlFor="repo-path">Folder path</label>
      <div className="row">
        <input
          id="repo-path"
          type="text"
          value={repoPath}
          placeholder="C:\Users\You\Desktop\my-project"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={pathError ? 'true' : 'false'}
          aria-describedby={pathError ? 'repo-path-error' : undefined}
          onChange={(event) => setRepoPath(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && online && !inspecting && !indexing) inspectRepository(); }}
        />
        <button type="button" className="btn" disabled={!online || inspecting || indexing} onClick={inspectRepository}>
          Inspect repository
        </button>
      </div>
      {pathError ? <p id="repo-path-error" className="field-error">{pathError}</p> : null}
      {!online ? <p className="muted">Connect to the backend first.</p> : null}

      {inspecting ? <Spinner label="Inspecting repository…" /> : null}
      <ErrorNotice error={inspect.error} baseUrl={api.baseUrl} />

      {inspect.data ? (
        <div className="result-block">
          <h3>{inspect.data.repository_name}</h3>
          {inspect.data.file_count === 0 ? (
            <div className="notice notice-warn" role="status">
              <strong>No supported source files found</strong>
              <p>This folder has no files the assistant can read (for example Python, JavaScript, TypeScript, Java, Go). Check that you chose the project folder.</p>
            </div>
          ) : (
            <>
              <p>
                <strong>{inspect.data.file_count}</strong> supported source files
                {inspect.data.truncated ? ' (scan stopped at the safety limit; large folders are only partly listed)' : ''}
              </p>
              <ul className="chips" aria-label="Files by language">
                {summary.map((item) => (
                  <li key={item.extension} className="chip">{item.language}: {item.count}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : null}

      <div className="result-block">
        <h3>Index</h3>
        {indexInfo?.indexed && indexInfo.chunk_count > 0 ? (
          <p>
            Indexed: <strong>{indexInfo.chunk_count}</strong> code chunks from <strong>{indexInfo.file_count}</strong> files.
            Re-index after you change code.
          </p>
        ) : (
          <p className="muted">Not indexed yet. Indexing reads the code and builds the local search index.</p>
        )}
        <button
          type="button"
          className="btn btn-primary"
          disabled={!online || indexing || inspecting || !repoPath.trim()}
          onClick={indexRepository}
        >
          {indexInfo?.indexed ? 'Re-index repository' : 'Index repository'}
        </button>
        {indexing ? (
          <p className="status-line">
            <Spinner label="Indexing… this can take several minutes the first time (the embedding model is downloaded once)." />
            <Elapsed />
          </p>
        ) : null}
        <ErrorNotice error={index.error} baseUrl={api.baseUrl} />
        {index.data ? (
          index.data.indexed_count === 0 ? (
            <div className="notice notice-warn" role="status">
              <strong>Nothing was indexed</strong>
              <p>No code could be turned into searchable chunks. {index.data.skipped_files?.length ? `${index.data.skipped_files.length} file(s) were skipped.` : 'Check that the folder contains supported source files.'}</p>
            </div>
          ) : (
            <div className="notice notice-ok" role="status">
              <strong>Index ready</strong>
              <p>
                {index.data.indexed_count} chunks from {index.data.file_count_scanned} files
                {index.data.removed_stale_count ? `, ${index.data.removed_stale_count} outdated chunks removed` : ''}.
                {index.data.skipped_files?.length ? ` ${index.data.skipped_files.length} file(s) were skipped.` : ''}
              </p>
            </div>
          )
        ) : null}
      </div>
    </section>
  );
}
