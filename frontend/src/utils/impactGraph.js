// Builds a small layered graph (changed -> direct -> transitive) from a real impact result.
const MAX_PER_COLUMN = 8;
export function baseName(path) { return String(path).split(/[\\/]/).pop(); }

export function buildImpactGraph(result) {
  const list = (v) => (Array.isArray(v) ? v : []);
  const columns = [
    { key: 'changed', title: 'Changed', files: list(result?.changed_files) },
    { key: 'direct', title: 'Direct dependents', files: list(result?.direct_dependents) },
    { key: 'transitive', title: 'Transitive', files: list(result?.transitive_dependents) },
  ];
  const nodes = []; const index = new Map();
  columns.forEach((col, c) => {
    col.files.slice(0, MAX_PER_COLUMN).forEach((file, r) => {
      if (index.has(file)) return;
      const node = { id: file, label: baseName(file), column: c, row: r, kind: col.key };
      index.set(file, node); nodes.push(node);
    });
    col.hidden = Math.max(0, col.files.length - MAX_PER_COLUMN);
  });
  const edges = list(result?.dependency_edges)
    .filter((e) => index.has(e.importer) && index.has(e.dependency))
    .map((e) => ({ from: e.dependency, to: e.importer, inferred: e.confidence === 'inferred' }));
  return { columns, nodes, edges };
}

// Heuristic only: counts of confirmed dependents, cycles and missing test coverage.
export function riskAssessment(result) {
  const len = (v) => (Array.isArray(v) ? v.length : 0);
  const reach = len(result?.direct_dependents) + len(result?.transitive_dependents);
  const cycles = len(result?.cycles);
  const tests = len(result?.related_tests);
  let level = reach >= 15 || cycles > 0 ? 'high' : reach >= 5 ? 'medium' : 'low';
  const reasons = [`${reach} dependent file${reach === 1 ? '' : 's'} reached`];
  if (cycles) reasons.push('circular imports involve a changed file');
  if (!tests) { reasons.push('no importing test file found'); if (level === 'low' && reach > 0) level = 'medium'; }
  return { level, reasons };
}
