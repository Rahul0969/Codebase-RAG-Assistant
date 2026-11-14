import { buildImpactGraph, riskAssessment } from '../utils/impactGraph.js';

const COL_X = [30, 270, 510]; const ROW_H = 38; const W = 700; const NODE_W = 170;
const KIND_CLASS = { changed: 'g-changed', direct: 'g-direct', transitive: 'g-trans' };

export function RiskCard({ result }) {
  const risk = riskAssessment(result);
  return (
    <section className={`card risk risk-${risk.level}`} aria-label="Risk assessment">
      <p className="eyebrow">RISK ASSESSMENT</p>
      <div className={`risk-level risk-text-${risk.level}`}>{risk.level.toUpperCase()}</div>
      <ul>{risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <p className="muted">Heuristic based on confirmed imports only; it is not a guarantee.</p>
    </section>
  );
}

export default function ImpactGraph({ result }) {
  const { columns, nodes, edges } = buildImpactGraph(result);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const rows = Math.max(1, ...columns.map((c) => Math.min(c.files.length, 8) + (c.hidden ? 1 : 0)));
  const height = 44 + rows * ROW_H;
  const pos = (n) => ({ x: COL_X[n.column], y: 40 + n.row * ROW_H });
  return (
    <section className="card" aria-label="Dependency graph">
      <h3>Dependency graph</h3>
      <p className="muted">Arrows point from a changed file to the files that import it.</p>
      <div className="graph-scroll">
        <svg viewBox={`0 0 ${W} ${height}`} width="100%" style={{ minWidth: 560 }} role="img" aria-label="Layered dependency graph of changed files and their dependents">
          <defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="#4c8dff" /></marker></defs>
          {columns.map((c, i) => <text key={c.key} x={COL_X[i]} y={20} className="g-title">{c.title} ({c.files.length})</text>)}
          {edges.map((e, i) => {
            const a = pos(byId.get(e.from)); const b = pos(byId.get(e.to));
            return <path key={i} d={`M${a.x + NODE_W} ${a.y + 13} C ${a.x + NODE_W + 40} ${a.y + 13}, ${b.x - 40} ${b.y + 13}, ${b.x} ${b.y + 13}`} className={e.inferred ? 'g-edge g-inferred' : 'g-edge'} markerEnd="url(#arrow)" />;
          })}
          {nodes.map((n) => { const p = pos(n); return (
            <g key={n.id} transform={`translate(${p.x} ${p.y})`}><title>{n.id}</title>
              <rect width={NODE_W} height={26} rx={7} className={`g-node ${KIND_CLASS[n.kind]}`} />
              <text x={10} y={17} className="g-label">{n.label.length > 22 ? `${n.label.slice(0, 21)}…` : n.label}</text>
            </g>); })}
          {columns.map((c, i) => c.hidden ? <text key={`h${i}`} x={COL_X[i]} y={40 + Math.min(c.files.length, 8) * ROW_H + 17} className="g-title">+{c.hidden} more (see lists below)</text> : null)}
        </svg>
      </div>
    </section>
  );
}
