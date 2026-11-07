import { describeEvidence } from '../utils/evidence.js';

export default function EvidenceBadge({ result }) {
  const info = describeEvidence(result);
  const icon = { ok: '✓', warn: '!', bad: '✕', neutral: '–' }[info.tone];
  return (
    <div className={`evidence evidence-${info.tone}`}>
      <span className="evidence-label">
        <span aria-hidden="true" className="evidence-icon">{icon}</span> {info.label}
      </span>
      <p>{info.explanation}</p>
      {result?.evidence_summary ? <p className="muted">{result.evidence_summary}</p> : null}
    </div>
  );
}
