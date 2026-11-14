import { useRef, useState } from 'react';
import CodeBlock from './CodeBlock.jsx';
import EvidenceBadge from './EvidenceBadge.jsx';
import { ErrorNotice, Spinner } from './Feedback.jsx';
import ConfirmDialog from './ConfirmDialog.jsx';
import { findChunkForCitation, splitAnswer } from '../utils/evidence.js';

const EXAMPLES = [
  'Where is authentication implemented?',
  'How does the API handle errors?',
  'Which function validates user input?',
  'Where is the main application entry point?',
];

function Answer({ result, onOpen }) {
  const parts = splitAnswer(result.answer, result.citations);
  return (
    <p className="answer-text">
      {parts.map((part, index) =>
        part.type === 'text' ? (
          <span key={index}>{part.text}</span>
        ) : (
          <span key={index} className="cite-group">
            {part.items.map((item) => (
              <button
                key={item.text}
                type="button"
                className={item.valid ? 'cite cite-ok' : 'cite cite-bad'}
                title={item.valid ? 'Show the cited code' : 'This citation does not match the retrieved code'}
                onClick={() => onOpen(item)}
              >
                {item.text}{item.valid ? '' : ' ✕'}
              </button>
            ))}
          </span>
        ),
      )}
    </p>
  );
}

function SourceViewer({ citation, chunks }) {
  if (!citation) return null;
  const chunk = findChunkForCitation(citation, chunks);
  return (
    <div className="source-viewer" role="region" aria-label={`Source ${citation.text}`}>
      <p className="meta"><strong>{citation.text}</strong>{citation.valid ? '' : ' (not verified)'}</p>
      {chunk && chunk.content ? (
        <CodeBlock
          content={chunk.content}
          firstLine={chunk.context_start_line ?? chunk.start_line}
          highlightStart={citation.valid ? citation.start_line : null}
          highlightEnd={citation.valid ? citation.end_line : null}
        />
      ) : (
        <p className="muted">That code was not among the retrieved sources, so there is nothing to show.</p>
      )}
    </div>
  );
}

function ResponseActions({ text }) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); }
  }
  return (
    <div className="row response-actions">
      <button type="button" className="btn btn-ghost btn-small" onClick={copy}>{copied ? 'Copied' : 'Copy answer'}</button>
      <button type="button" className={vote === 'up' ? 'btn btn-ghost btn-small is-on' : 'btn btn-ghost btn-small'} aria-pressed={vote === 'up'} aria-label="Helpful" onClick={() => setVote(vote === 'up' ? '' : 'up')}>Helpful</button>
      <button type="button" className={vote === 'down' ? 'btn btn-ghost btn-small is-on' : 'btn btn-ghost btn-small'} aria-pressed={vote === 'down'} aria-label="Not helpful" onClick={() => setVote(vote === 'down' ? '' : 'down')}>Not helpful</button>
    </div>
  );
}

function Entry({ entry, baseUrl }) {
  const [open, setOpen] = useState(null);
  const result = entry.result;
  return (
    <article className="qa" id={`qa-${entry.id}`} aria-live="polite">
      <div className="question"><span className="who">You</span><p>{entry.question}</p></div>
      <div className="answer">
        <span className="who">Assistant</span>
        {entry.status === 'loading' ? <Spinner label="Generating answer… a local model can take a while on a small computer." /> : null}
        <ErrorNotice error={entry.error} baseUrl={baseUrl} />
        {result ? (
          <>
            <EvidenceBadge result={result} />
            <Answer result={result} onOpen={setOpen} />
            {result.unsupported_citations.length > 0 ? (
              <p className="field-error">
                Unverified citations: {result.unsupported_citations.map((c) => c.text).join(', ')}
              </p>
            ) : null}
            <SourceViewer citation={open} chunks={result.retrieved_chunks} />
            <ResponseActions text={result.answer} />
            <details className="retrieval">
              <summary>
                Retrieval: {result.used_chunk_count} of {result.retrieved_count} chunks used · model {result.model} · {result.routing?.mode || 'AUTO'}
              </summary>
              {result.routing?.reason ? <p className="muted">Routing: {result.routing.reason}</p> : null}
              {result.retrieved_chunks.length === 0 ? <p className="muted">No relevant code was retrieved.</p> : (
                <ul>
                  {result.retrieved_chunks.map((chunk) => (
                    <li key={chunk.source_id}>
                      <button type="button" className="linklike" onClick={() => setOpen({
                        text: `${chunk.file_path}:${chunk.context_start_line}-${chunk.context_end_line}`,
                        file_path: chunk.file_path, start_line: chunk.context_start_line, end_line: chunk.context_end_line,
                        valid: false, reason: 'browse', source_id: chunk.source_id,
                      })}>
                        {chunk.file_path}:{chunk.context_start_line}–{chunk.context_end_line}
                      </button>
                      {chunk.symbol ? <span> · {chunk.symbol}</span> : null}
                      {chunk.cited ? <span className="chip">cited</span> : null}
                    </li>
                  ))}
                </ul>
              )}
              {result.context_truncated ? <p className="muted">Some code was shortened to fit the model's context.</p> : null}
            </details>
          </>
        ) : null}
      </div>
    </article>
  );
}

export default function AskPanel({ workspace }) {
  const { asks, asking, askQuestion, clearAsks, repositoryReady, health, api } = workspace;
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(5);
  const inputRef = useRef(null);
  const [confirmNew, setConfirmNew] = useState(false);
  const ollama = health.data?.ollama;
  const canAsk = repositoryReady && health.state === 'online' && !asking && question.trim().length > 0;

  function submit(event) {
    event.preventDefault();
    if (!canAsk) return;
    askQuestion(question, topK);
    setQuestion('');
  }

  return (
    <div className="ask-layout">
    <aside className="card ask-side" aria-label="Conversation">
      <button type="button" className="btn btn-primary" onClick={() => (asks.length ? setConfirmNew(true) : inputRef.current?.focus())} disabled={asking}>+ New conversation</button>
      <p className="eyebrow">THIS CONVERSATION</p>
      {asks.length === 0 ? <p className="muted">No questions yet.</p> : (
        <ol className="ask-history">{asks.map((entry) => (
          <li key={entry.id}><a href={`#qa-${entry.id}`} onClick={(event) => { event.preventDefault(); document.getElementById(`qa-${entry.id}`)?.scrollIntoView?.({ block: 'start' }); }}>{entry.question}</a></li>
        ))}</ol>
      )}
    </aside>
    <section className="card ask-main" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask the codebase</h2>
      {!repositoryReady ? <p className="notice notice-warn" role="status">Index a repository first on the Repository page.</p> : null}
      {health.state === 'online' && ollama && !ollama.reachable ? (
        <div className="notice notice-warn" role="status">
          <strong>Ollama is not running</strong>
          <p>{ollama.message} Questions need Ollama; search still works.</p>
        </div>
      ) : null}
      {health.state === 'online' && ollama?.reachable && ollama.model_available === false ? (
        <div className="notice notice-warn" role="status">
          <strong>Model not installed</strong>
          <p>{ollama.message}</p>
        </div>
      ) : null}

      <div className="examples" aria-label="Example questions">
        {EXAMPLES.map((text) => (
          <button key={text} type="button" className="chip chip-button" onClick={() => { setQuestion(text); inputRef.current?.focus(); }}>
            {text}
          </button>
        ))}
      </div>

      <div className="thread">
        {asks.length === 0 ? <p className="muted">Answers appear here with the code they are based on.</p> : null}
        {asks.map((entry) => <Entry key={entry.id} entry={entry} baseUrl={api.baseUrl} />)}
      </div>

      <form onSubmit={submit} className="stack">
        <label htmlFor="ask-question">Your question</label>
        <div className="row">
          <input
            id="ask-question"
            ref={inputRef}
            type="text"
            value={question}
            maxLength={2000}
            placeholder="Where is user authentication implemented?"
            onChange={(event) => setQuestion(event.target.value)}
          />
          <label htmlFor="ask-topk" className="sr-only">Code chunks to retrieve</label>
          <select id="ask-topk" value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
            {[3, 5, 8].map((n) => <option key={n} value={n}>{n} chunks</option>)}
          </select>
          <button type="submit" className="btn btn-primary" disabled={!canAsk}>Ask</button>
        </div>
      </form>
      {asks.length > 0 ? (
        <button type="button" className="btn btn-ghost btn-small" onClick={() => setConfirmNew(true)} disabled={asking}>Clear conversation</button>
      ) : null}
      <ConfirmDialog open={confirmNew} title="Clear this conversation?" confirmLabel="Clear" onCancel={() => setConfirmNew(false)} onConfirm={() => { clearAsks(); setConfirmNew(false); inputRef.current?.focus(); }}>
        Your questions and answers on this screen will be removed. Indexed code is not affected.
      </ConfirmDialog>
    </section>
    </div>
  );
}
