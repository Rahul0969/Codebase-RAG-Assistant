import { useEffect, useState } from 'react';
import { ErrorNotice, Spinner } from './Feedback.jsx';

function saveTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType || 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function ReportsPanel({ workspace }) {
  const { api, repoPath, health } = workspace;
  const [format, setFormat] = useState('md');
  const [useAi, setUseAi] = useState(true);
  const [status, setStatus] = useState('idle');
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState(null);
  const online = health.state === 'online';

  async function refreshHistory() {
    try {
      const result = await api.listReports();
      setHistory(result.reports);
      setHistoryError(null);
    } catch (problem) {
      setHistoryError(problem);
    }
  }

  useEffect(() => { if (online) refreshHistory(); }, [online]);

  async function generate() {
    if (!repoPath.trim()) {
      setError(new Error('Select a repository on the Repository page first.'));
      return;
    }
    setStatus('loading');
    setError(null);
    setReport(null);
    try {
      const result = await api.generateReport(repoPath.trim(), format, useAi);
      setReport(result);
      setStatus('done');
      await refreshHistory();
    } catch (problem) {
      setError(problem);
      setStatus('error');
    }
  }

  async function openPrevious(reportId) {
    setStatus('loading');
    setError(null);
    try {
      const result = await api.getReport(reportId);
      setReport(result);
      setStatus('done');
    } catch (problem) {
      setError(problem);
      setStatus('error');
    }
  }

  function downloadCurrent() {
    if (!report) return;
    const ext = report.filename?.split('.').pop() || format;
    const mime = report.mime_type || (ext === 'html' ? 'text/html;charset=utf-8' : ext === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8');
    saveTextFile(report.filename || `repository-report.${ext}`, report.content, mime);
  }

  return (
    <div className="stack-lg">
      <section className="hero">
        <h2>Repository Intelligence Reports</h2>
        <p>Generate a structured report from the files and code that the local backend can inspect. Ollama can optionally write the executive summary; factual counts and file references come from local inspection.</p>
      </section>
      <section className="card" aria-labelledby="report-create-title">
        <h2 id="report-create-title">Generate a report</h2>
        <p className="muted">Selected repository: <strong>{repoPath || 'No repository selected'}</strong></p>
        <label htmlFor="report-format">Report format</label>
        <select id="report-format" value={format} onChange={(event) => setFormat(event.target.value)}>
          <option value="md">Markdown (.md)</option>
          <option value="html">HTML (.html)</option>
          <option value="json">JSON (.json)</option>
        </select>
        <label className="checkbox-row" htmlFor="report-ai-summary">
          <input id="report-ai-summary" type="checkbox" checked={useAi} onChange={(event) => setUseAi(event.target.checked)} />
          Use local Ollama for the executive summary (falls back automatically if unavailable)
        </label>
        <div className="row">
          <button type="button" className="btn btn-primary" disabled={!online || status === 'loading' || !repoPath.trim()} onClick={generate}>Generate report</button>
          {!online ? <span className="muted">Connect to the local backend first.</span> : null}
        </div>
        {status === 'loading' ? <p><Spinner label="Inspecting files and preparing the report…" /></p> : null}
        <ErrorNotice error={error} baseUrl={api.baseUrl} />
        {report ? (
          <div className="result-block" aria-live="polite">
            <div className="row report-result-head">
              <div><h3>{report.repository_name || 'Repository report'}</h3><p className="muted">{report.filename} · {report.summary_source || 'Previously generated report'}</p></div>
              <button type="button" className="btn btn-primary" onClick={downloadCurrent}>Download report</button>
            </div>
            <label htmlFor="report-preview">Report preview</label>
            <textarea id="report-preview" className="report-preview" readOnly value={report.content} />
          </div>
        ) : null}
      </section>
      <section className="card" aria-labelledby="report-history-title">
        <div className="row report-result-head"><h2 id="report-history-title">Report history</h2><button type="button" className="btn btn-small" disabled={!online} onClick={refreshHistory}>Refresh</button></div>
        {historyError ? <ErrorNotice error={historyError} baseUrl={api.baseUrl} /> : null}
        {history.length ? (
          <ul className="report-history">{history.map((item) => (
            <li key={item.report_id}>
              <div><strong>{item.repository_name}</strong><small className="muted">{item.generated_at} · {item.format.toUpperCase()}</small></div>
              <button type="button" className="btn btn-small" onClick={() => openPrevious(item.report_id)}>Open</button>
            </li>
          ))}</ul>
        ) : <p className="muted">No reports generated yet.</p>}
      </section>
    </div>
  );
}
