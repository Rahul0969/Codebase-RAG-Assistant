import { useState } from 'react';
import CodeBlock from './CodeBlock.jsx';
import { EmptyState, ErrorNotice, Spinner } from './Feedback.jsx';
import { facets, fileExt, filterMatches } from '../utils/search.js';

export default function SearchPanel({ workspace }) {
  const { search, lastQuery, runSearch, repositoryReady, health, api } = workspace;
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [filters, setFilters] = useState({ language: '', directory: '', extension: '' });
  const loading = search.status === 'loading';
  const allMatches = search.status === 'success' ? search.data.matches : [];
  const options = facets(allMatches);
  const shown = filterMatches(allMatches, filters);
  const setFilter = (key) => (event) => setFilters((f) => ({ ...f, [key]: event.target.value }));
  const canSearch = repositoryReady && health.state === 'online' && !loading && query.trim().length > 0;

  function submit(event) {
    event.preventDefault();
    if (canSearch) { setFilters({ language: '', directory: '', extension: '' }); runSearch(query, topK); }
  }

  return (
    <section className="card" aria-labelledby="search-title">
      <h2 id="search-title">Code search</h2>
      <p className="muted">Describe what you are looking for in plain language.</p>
      {!repositoryReady ? <p className="notice notice-warn" role="status">Index a repository first on the Repository page.</p> : null}
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
      {allMatches.length > 0 ? (
        <div className="filters" role="group" aria-label="Filter results">
          <label className="filter">Language<select value={filters.language} onChange={setFilter('language')}><option value="">All</option>{options.languages.map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
          <label className="filter">Directory<select value={filters.directory} onChange={setFilter('directory')}><option value="">All</option>{options.directories.map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
          <label className="filter">File type<select value={filters.extension} onChange={setFilter('extension')}><option value="">All</option>{options.extensions.map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
          <span className="muted filter-count">{shown.length} of {allMatches.length} results</span>
        </div>
      ) : null}
      {allMatches.length > 0 && shown.length === 0 ? <EmptyState title="No results match these filters">Clear a filter to see more results.</EmptyState> : null}
      {search.status === 'success' ? (
        <ol className="results">
          {shown.map((match) => (
            <li key={match.chunk_id} className="result-card">
              <div className="result-head">
                <code className="path">{match.file_path}</code>
                <span className="row"><span className="chip">{fileExt(match.file_path) || 'file'}</span><span className="relevance" title="Relevance"><i style={{ width: `${Math.max(4, Math.min(100, Math.round(match.similarity * 100)))}%` }} /></span><span className="chip chip-score">{Math.round(match.similarity * 100)}% match</span></span>
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
