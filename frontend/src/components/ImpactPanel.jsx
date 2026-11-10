import { useState } from 'react';
import { ErrorNotice, Spinner } from './Feedback.jsx';

const MAX_EDGES_SHOWN = 200;
const REASONS = {
  not_found: 'no matching file',
  ambiguous_match: 'several files match',
  beyond_repository_root: 'points outside the repository',
  unsupported_file_type: 'target file type is not scanned',
};

function FileList({ title, hint, files, emptyText, tone }) {
  return (
    <section className={`card impact-list${tone ? ` impact-${tone}` : ''}`} aria-label={title}>
      <h3>{title} <span className="muted">({files.length})</span></h3>
      {hint ? <p className="muted">{hint}</p> : null}
      {files.length
        ? <ul>{files.map((file) => <li key={file}><code>{file}</code></li>)}</ul>
        : <p className="muted">{emptyText}</p>}
    </section>
  );
}

export default function ImpactPanel({ workspace }) {
  const { api, repoPath, health } = workspace;
  const [changedPath, setChangedPath] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function analyze(event) {
    event.preventDefault();
    if (loading) return;
    const paths = [...new Set(changedPath.split(/\r?\n/).map((item) => item.trim()).filter(Boolean))];
    if (!paths.length) {
      setError(new Error('Enter at least one repository-relative file path.'));
      return;
    }
    if (paths.length > 20) {
      setError(new Error('Analyze up to 20 changed files at a time.'));
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.analyzeImpact(repoPath.trim(), paths));
    } catch (problem) {
      setError(problem);
    } finally {
      setLoading(false);
    }
  }

  const offline = health.state !== 'online';
  const blocker = !repoPath.trim() ? 'Select a repository first.' : offline ? 'The backend is not reachable.' : '';
  const list = (value) => (Array.isArray(value) ? value : []);
  const edges = list(result?.dependency_edges);
  const cycles = list(result?.cycles);
  const unresolved = list(result?.unresolved_local_references);
  const skipped = list(result?.skipped_files);
  const aliases = list(result?.unmapped_aliases);
  const possible = list(result?.possible_dependents);
  const likelyTests = list(result?.likely_related_tests);

  return (
    <div className="stack-lg">
      <section className="hero">
        <h2>Code Change Impact Analysis</h2>
        <p>Enter changed file paths to see which files import them, directly or through other files, and which tests cover them. Analysis is static and local; repository code is never executed.</p>
      </section>
      <section className="card">
        <h2>Analyze changed files</h2>
        <p className="muted">Selected repository: <strong>{repoPath || 'No repository selected'}</strong></p>
        <form onSubmit={analyze} className="stack-md" aria-busy={loading}>
          <label htmlFor="impact-files">Changed file paths (one per line, relative to the repository; / or \ both work)</label>
          <textarea id="impact-files" className="impact-input" rows={4} value={changedPath}
            onChange={(event) => setChangedPath(event.target.value)}
            aria-describedby="impact-help"
            placeholder={'src/services/api.js\nbackend/app/config.py'} />
          <div className="row">
            <button className="btn btn-primary" type="submit" disabled={loading || Boolean(blocker)}>
              {loading ? 'Analyzing…' : 'Analyze impact'}
            </button>
            <span id="impact-help" className="muted">{blocker || 'Maximum 20 files per analysis'}</span>
          </div>
        </form>
        {loading ? <p><Spinner label="Building local dependency graph…" /></p> : null}
        <ErrorNotice error={error} baseUrl={api.baseUrl} />
      </section>

      {result ? (
        <div className="stack-md" aria-live="polite">
          <section className="card">
            <h2>Impact overview</h2>
            <p className="muted">{result.repository_name} · {result.files_scanned} of {result.files_discovered ?? result.files_scanned} files analysed</p>
            <div className="stats-grid">
              <div className="stat"><strong>{result.direct_dependents.length}</strong><span>Direct dependents</span></div>
              <div className="stat"><strong>{result.transitive_dependents.length}</strong><span>Transitive dependents</span></div>
              <div className="stat"><strong>{result.related_tests.length}</strong><span>Tests that import it</span></div>
              <div className="stat"><strong>{possible.length}</strong><span>Possible (unconfirmed)</span></div>
            </div>
            <p><strong>Changed:</strong> {result.changed_files.map((file) => <code key={file}>{file} </code>)}</p>
            {result.truncated ? <p className="notice" role="status">Results may be incomplete: a safety limit was reached. See the limitations below.</p> : null}
            {cycles.length ? (
              <div className="notice" role="status">
                <strong>Circular imports involve your changed files.</strong>
                <ul>{cycles.map((cycle, index) => (
                  <li key={index}>{cycle.size} files: {cycle.files.map((file) => <code key={file}>{file} </code>)}{cycle.size > cycle.files.length ? '…' : ''}</li>
                ))}</ul>
              </div>
            ) : null}
          </section>

          <FileList title="Direct dependents" tone="confirmed" hint="Confirmed: these files import a changed file."
            files={result.direct_dependents} emptyText="No file imports the changed files directly." />
          <FileList title="Transitive dependents" tone="confirmed" hint="Confirmed: reached through a chain of imports."
            files={result.transitive_dependents} emptyText="No transitive dependents were found." />
          <FileList title="Tests that import the change" tone="confirmed" hint="Confirmed through imports."
            files={result.related_tests} emptyText="No test file was found importing the changed files." />
          {possible.length ? (
            <FileList title="Possible dependents (unconfirmed)" tone="guess"
              hint="Found only through guesses such as source-root matching, alias folders or wildcard imports. Verify before relying on them."
              files={possible} emptyText="" />
          ) : null}
          {likelyTests.length ? (
            <FileList title="Likely tests (by file name only)" tone="guess"
              hint="Matched by naming convention; no import was found."
              files={likelyTests} emptyText="" />
          ) : null}

          <section className="card">
            <h3>Dependency relationships <span className="muted">({result.dependency_edge_count ?? edges.length})</span></h3>
            {edges.length ? (
              <ul className="impact-edges">
                {edges.slice(0, MAX_EDGES_SHOWN).map((edge, index) => (
                  <li key={`${edge.importer}-${edge.dependency}-${index}`}>
                    <code>{edge.importer}</code> → <code>{edge.dependency}</code>
                    {edge.confidence === 'inferred' ? <span className="badge-guess"> inferred</span> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="muted">No dependency edges were found for the affected files.</p>}
            {edges.length > MAX_EDGES_SHOWN ? <p className="muted">Showing the first {MAX_EDGES_SHOWN} relationships.</p> : null}
          </section>

          <section className="card">
            <h3>Analysis limitations</h3>
            <ul>{list(result.limitations).map((item) => <li key={item}>{item}</li>)}</ul>
            {unresolved.length ? (
              <details>
                <summary>Local references not found ({result.unresolved_reference_count ?? unresolved.length})</summary>
                <ul>{unresolved.map((item, index) => (
                  <li key={`${item.file_path}-${item.reference}-${index}`}>
                    <code>{item.file_path}</code>: <code>{item.reference}</code>
                    {item.reason ? <span className="muted"> ({REASONS[item.reason] || item.reason})</span> : null}
                  </li>
                ))}</ul>
              </details>
            ) : null}
            {aliases.length ? (
              <details>
                <summary>Alias imports not analysed ({aliases.length})</summary>
                <ul>{aliases.map((item) => <li key={item}><code>{item}</code></li>)}</ul>
              </details>
            ) : null}
            {skipped.length ? (
              <details>
                <summary>Files skipped ({result.skipped_file_count ?? skipped.length})</summary>
                <ul>{skipped.map((item, index) => <li key={`${item.path}-${index}`}><code>{item.path}</code> <span className="muted">({String(item.reason).replace(/_/g, ' ')})</span></li>)}</ul>
              </details>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
