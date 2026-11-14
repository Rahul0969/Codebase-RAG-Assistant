import { useEffect, useMemo, useState } from 'react';
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

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'section';
}

function parseMarkdown(content) {
  const lines = String(content || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let paragraph = [];
  let code = [];
  let inCode = false;
  let codeLanguage = '';
  const flushParagraph = () => {
    if (paragraph.length) { blocks.push({ type: 'paragraph', text: paragraph.join(' ') }); paragraph = []; }
  };
  const flushCode = () => {
    blocks.push({ type: 'code', text: code.join('\n'), language: codeLanguage });
    code = []; codeLanguage = '';
  };
  for (const line of lines) {
    const fence = line.match(/^```\s*([\w+-]*)\s*$/);
    if (fence) {
      if (inCode) flushCode(); else { flushParagraph(); inCode = true; codeLanguage = fence[1]; }
      continue;
    }
    if (inCode) { code.push(line); continue; }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) { flushParagraph(); blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].replace(/\s+#+\s*$/, '') }); continue; }
    if (/^\s*[-*]\s+/.test(line)) { flushParagraph(); blocks.push({ type: 'list-item', text: line.replace(/^\s*[-*]\s+/, '') }); continue; }
    if (/^\s*\d+[.)]\s+/.test(line)) { flushParagraph(); blocks.push({ type: 'list-item', text: line.replace(/^\s*\d+[.)]\s+/, ''), ordered: true }); continue; }
    if (!line.trim()) { flushParagraph(); continue; }
    paragraph.push(line.trim());
  }
  flushParagraph();
  if (inCode) flushCode();
  return blocks;
}

function InlineText({ value }) {
  // Render source text as text nodes; report content is never interpreted as HTML.
  const parts = String(value).split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return <>{parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    return <span key={index}>{part}</span>;
  })}</>;
}

function ReportDocument({ content }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);
  const sections = useMemo(() => {
    const seen = new Map();
    return blocks.filter((block) => block.type === 'heading' && block.level <= 3).map((block) => {
      const base = slug(block.text);
      const count = seen.get(base) || 0;
      seen.set(base, count + 1);
      return { ...block, id: count ? `${base}-${count + 1}` : base };
    });
  }, [blocks]);
  let headingIndex = 0;
  return (
    <div className="report-reader-grid">
      <article className="report-document" aria-label="Generated report document">
        {blocks.length ? blocks.map((block, index) => {
          if (block.type === 'heading') {
            const section = block.level <= 3 ? sections[headingIndex++] : null;
            const Tag = `h${Math.min(block.level + 1, 5)}`;
            return <Tag className="report-doc-heading" id={section?.id} key={index}><InlineText value={block.text} /></Tag>;
          }
          if (block.type === 'code') return <pre className="report-code" key={index}><div className="report-code-toolbar"><span>{block.language || 'CODE'}</span><span>Source excerpt</span></div><code>{block.text}</code></pre>;
          if (block.type === 'list-item') return <div className="report-list-item" key={index}><span className="report-list-dot" /> <InlineText value={block.text} /></div>;
          return <p className="report-doc-paragraph" key={index}><InlineText value={block.text} /></p>;
        }) : <p className="muted">Generate a report to view repository documentation here.</p>}
      </article>
      <aside className="report-toc" aria-label="On this page">
        <p className="report-toc-title">ON THIS PAGE</p>
        {sections.length ? sections.map((section) => <a key={section.id} href={`#${section.id}`} className={`report-toc-link level-${section.level}`}>{section.text}</a>) : <span className="muted">Sections appear here</span>}
      </aside>
    </div>
  );
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
  const [showGenerator, setShowGenerator] = useState(false);
  const online = health.state === 'online';

  async function refreshHistory() {
    try { const result = await api.listReports(); setHistory(result.reports); setHistoryError(null); }
    catch (problem) { setHistoryError(problem); }
  }
  useEffect(() => { if (online) refreshHistory(); }, [online]);

  async function generate() {
    if (!repoPath.trim()) { setError(new Error('Select a repository on the Repository page first.')); return; }
    setStatus('loading'); setError(null); setReport(null);
    try {
      const result = await api.generateReport(repoPath.trim(), format, useAi);
      setReport(result); setStatus('done'); setShowGenerator(false); await refreshHistory();
    } catch (problem) { setError(problem); setStatus('error'); }
  }
  async function openPrevious(reportId) {
    setStatus('loading'); setError(null);
    try { const result = await api.getReport(reportId); setReport(result); setStatus('done'); }
    catch (problem) { setError(problem); setStatus('error'); }
  }
  function downloadCurrent() {
    if (!report) return;
    const ext = report.filename?.split('.').pop() || format;
    const mime = report.mime_type || (ext === 'html' ? 'text/html;charset=utf-8' : ext === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8');
    saveTextFile(report.filename || `repository-report.${ext}`, report.content, mime);
  }

  return (
    <div className="report-workspace">
      <div className="report-page-heading">
        <div><p className="report-eyebrow">KNOWLEDGE BASE / DOCUMENTATION</p><h2>System Architecture &amp; Documentation</h2><p className="report-subtitle">Explore the architecture, components, data flow and operational details of the selected codebase.</p></div>
        <div className="report-heading-actions"><span className="report-generated">{report ? 'Report ready' : 'Repository intelligence'}</span><button type="button" className="btn btn-primary report-regenerate" disabled={!online || status === 'loading' || !repoPath.trim()} onClick={() => setShowGenerator((value) => !value)}>{report ? '↻ Regenerate' : '+ Generate report'}</button></div>
      </div>
      {!online ? <div className="report-inline-notice">Connect to the local backend to generate or open reports.</div> : null}
      <ErrorNotice error={error} baseUrl={api.baseUrl} />
      {status === 'loading' ? <div className="report-loading"><Spinner label="Inspecting repository and preparing documentation…" /></div> : null}
      {showGenerator || !report ? (
        <section className="report-generator card" aria-labelledby="report-create-title">
          <div className="report-generator-heading"><div><span className="report-section-kicker">REPORT BUILDER</span><h3 id="report-create-title">Generate repository documentation</h3><p className="muted">Evidence-backed details are collected locally from the selected repository.</p></div><span className="report-private">⌑ Local processing</span></div>
          <div className="report-generator-controls"><div className="report-control"><label htmlFor="report-format">Output format</label><select id="report-format" value={format} onChange={(event) => setFormat(event.target.value)}><option value="md">Markdown (.md)</option><option value="html">HTML (.html)</option><option value="json">JSON (.json)</option></select></div><label className="report-ai-toggle" htmlFor="report-ai-summary"><input id="report-ai-summary" type="checkbox" checked={useAi} onChange={(event) => setUseAi(event.target.checked)} /><span><strong>Local AI executive summary</strong><small>Use Ollama when available; deterministic summary is used as fallback.</small></span></label></div>
          <div className="report-generator-footer"><span className="muted">Workspace: <strong>{repoPath || 'No repository selected'}</strong></span><button type="button" className="btn btn-primary" disabled={!online || status === 'loading' || !repoPath.trim()} onClick={generate}>Generate documentation <span aria-hidden="true">→</span></button></div>
        </section>
      ) : null}
      {report ? (
        <>
          <div className="report-document-toolbar"><div><span className="report-file-icon">▤</span><div><strong>{report.repository_name || 'Repository documentation'}</strong><small>{report.filename || 'Generated report'} · {report.summary_source || 'Local repository analysis'}</small></div></div><div className="row"><button type="button" className="btn btn-small" onClick={() => setShowGenerator(true)}>Report settings</button><button type="button" className="btn btn-small btn-primary" onClick={downloadCurrent}>↓ Download</button></div></div>
          <ReportDocument content={report.content} />
        </>
      ) : null}
      <section className="report-history-section">
        <div className="report-history-heading"><div><span className="report-section-kicker">YOUR WORKSPACE</span><h3>Recent reports</h3></div><button type="button" className="btn btn-small" disabled={!online} onClick={refreshHistory}>↻ Refresh</button></div>
        {historyError ? <ErrorNotice error={historyError} baseUrl={api.baseUrl} /> : null}
        {history.length ? <ul className="report-history report-history-modern">{history.map((item) => <li key={item.report_id}><div className="report-history-file">▤</div><div className="report-history-meta"><strong>{item.repository_name}</strong><small>{item.generated_at} · {item.format.toUpperCase()}</small></div><button type="button" className="btn btn-small" onClick={() => openPrevious(item.report_id)}>Open report →</button></li>)}</ul> : <div className="report-empty-history"><span>▤</span><strong>No reports generated yet</strong><p>Generate your first repository report to build a searchable documentation history.</p></div>}
      </section>
    </div>
  );
}
