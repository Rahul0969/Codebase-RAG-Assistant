import { useState } from 'react';
import CodeBlock from './CodeBlock.jsx';
import { EmptyState, ErrorNotice, Spinner } from './Feedback.jsx';

export default function SearchPanel({ workspace }) {
  const { search, lastQuery, runSearch, repositoryReady, health, api } = workspace;
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const loading = search.status === 'loading';
  const canSearch = repositoryReady && health.state === 'online' && !loading && query.trim().length > 0;

  function submit(event) {
    event.preventDefault();
    if (canSearch) runSearch(query, topK);
  }

  return (
    <section className="card" aria-labelledby="search-title">
      <h2 id="search-title">Code search</h2>
      <p className="muted">Describe what you are looking for in plain language.</p>
      {!repositoryReady ? <p className="notice notice-warn" role="status">Index a repository first (Repository section).</p> : null}
      <form onSubmit={submit} className="stack">
        <label htmlFor="search-query">What are you looking for?</label>
        <div className="row">
          <input
            id="search-query"
            type="text"
            value={query}
            maxLength={4000}
            placeholder="function that validates user input"
            onChange={(event) => setQuery(event.target.value)}
          />
          <label htmlFor="search-topk" className="sr-only">Number of results</label>
          <select id="search-topk" value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
            {[3, 5, 8, 10].map((n) => <option key={n} value={n}>{n} results</option>)}
          </select>
          <button type="submit" className="btn btn-primary" disabled={!canSearch}>Search</button>
        </div>
      </form>

      {loading ? <Spinner label="Searching…" /> : null}
      <ErrorNotice error={search.error} baseUrl={api.baseUrl} />
      {search.status === 'success' && search.data.matches.length === 0 ? (
        <EmptyState title="No results">Nothing matched “{lastQuery}”. Try different words, or re-index if the code changed.</EmptyState>
      ) : null}
      {search.status === 'success' ? (
        <ol className="results">
          {search.data.matches.map((match) => (
            <li key={match.chunk_id} className="result-card">
              <div className="result-head">
                <code className="path">{match.file_path}</code>
                <span className="chip">{Math.round(match.similarity * 100)}% match</span>
              </div>
              <p className="meta">
                {match.symbol ? <span>{match.symbol} · </span> : null}
                <span>{match.language} · </span>
                <span>lines {match.start_line}–{match.end_line}</span>
              </p>
              <CodeBlock content={match.content} firstLine={match.start_line ?? 1} />
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
