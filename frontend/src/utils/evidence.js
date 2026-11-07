// Helpers that turn the backend's evidence data into things the UI can show.

const STATUS = {
  verified: {
    tone: 'ok',
    label: 'Citations verified',
    explanation:
      'Every citation points to code that was really retrieved, and every statement has one. This shows where the answer comes from. It does not prove each statement is correct, so read the cited code.',
  },
  partially_verified: {
    tone: 'warn',
    label: 'Partly verified',
    explanation:
      'The citations are real, but some statements have no citation or mention names that do not appear in the retrieved code. Treat those parts with care.',
  },
  invalid_citations: {
    tone: 'bad',
    label: 'Citation check failed',
    explanation:
      'At least one citation does not match the code that was retrieved. Do not trust the answer until you have checked it yourself.',
  },
  no_citations: {
    tone: 'warn',
    label: 'No citations',
    explanation: 'The answer does not say which code it is based on, so it cannot be checked. Treat it as unverified.',
  },
  insufficient_evidence: {
    tone: 'neutral',
    label: 'Insufficient evidence',
    explanation:
      'The indexed code does not contain enough relevant information to answer. Try rephrasing, or check that the right repository is indexed.',
  },
};

export function describeEvidence(result) {
  const status = result?.evidence_status;
  const known = STATUS[status];
  if (!known) {
    return { tone: 'neutral', label: 'Unknown status', explanation: 'The backend sent an evidence status this page does not know.' };
  }
  // Never show success unless the backend says validation passed.
  if (known.tone === 'ok' && result.validation_passed !== true) {
    return { ...STATUS.no_citations };
  }
  return { ...known };
}

const BRACKET = /\[([^\[\]\r\n]{3,300})\]/g;
const ITEM = /^\s*([^\s:][^:\[\]]*?):\s*L?(\d{1,7})(?:\s*[-\u2013\u2014]\s*L?(\d{1,7}))?\s*$/;

function normalizePath(path) {
  let cleaned = path.trim().replace(/\\/g, '/');
  while (cleaned.startsWith('./')) cleaned = cleaned.slice(2);
  return cleaned;
}

function parseItems(inner) {
  const items = [];
  for (const part of inner.split(/[;,](?=\s*[^\d\s])/)) {
    const match = ITEM.exec(part);
    if (!match) continue;
    const path = normalizePath(match[1]);
    if (!/[/.]/.test(path)) continue;
    const start = Number(match[2]);
    const end = match[3] ? Number(match[3]) : start;
    items.push({ text: start === end ? `${path}:${start}` : `${path}:${start}-${end}`, file_path: path, start_line: start, end_line: end });
  }
  return items;
}

/**
 * Splits an answer into plain text and citation groups.
 * Each citation item is matched with the backend's validated citation when possible.
 */
export function splitAnswer(answer, citations = []) {
  const byText = new Map((citations ?? []).map((c) => [c.text, c]));
  const segments = [];
  let last = 0;
  const text = answer ?? '';
  for (const match of text.matchAll(BRACKET)) {
    const items = parseItems(match[1]);
    if (items.length === 0) continue;
    if (match.index > last) segments.push({ type: 'text', text: text.slice(last, match.index) });
    segments.push({
      type: 'citations',
      items: items.map((item) => byText.get(item.text) ?? { ...item, valid: false, reason: 'unchecked', source_id: null }),
    });
    last = match.index + match[0].length;
  }
  if (last < text.length) segments.push({ type: 'text', text: text.slice(last) });
  return segments;
}

/** Finds the retrieved chunk a citation refers to (or null). */
export function findChunkForCitation(citation, chunks = []) {
  if (!citation) return null;
  if (citation.source_id != null) {
    const byId = chunks.find((c) => c.source_id === citation.source_id);
    if (byId) return byId;
  }
  const path = normalizePath(citation.file_path ?? '');
  return (
    chunks.find(
      (c) =>
        normalizePath(c.file_path) === path &&
        citation.start_line <= (c.context_end_line ?? c.end_line) &&
        citation.end_line >= (c.context_start_line ?? c.start_line),
    ) ?? null
  );
}

/** Splits code into numbered lines; marks lines inside [highlightStart, highlightEnd]. */
export function numberedLines(content, firstLine, highlightStart = null, highlightEnd = null) {
  return String(content ?? '')
    .split(/\r?\n/)
    .map((text, index) => {
      const number = firstLine + index;
      return {
        number,
        text,
        highlighted: highlightStart != null && number >= highlightStart && number <= (highlightEnd ?? highlightStart),
      };
    });
}
