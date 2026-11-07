import { useState } from 'react';
import { numberedLines } from '../utils/evidence.js';

const COLLAPSED_LINES = 24;

/** Plain code listing with real line numbers; optionally highlights a cited range. */
export default function CodeBlock({ content, firstLine = 1, highlightStart = null, highlightEnd = null, collapsible = true }) {
  const [expanded, setExpanded] = useState(false);
  const lines = numberedLines(content, firstLine, highlightStart, highlightEnd);
  const shown = collapsible && !expanded ? lines.slice(0, COLLAPSED_LINES) : lines;
  const hidden = lines.length - shown.length;
  return (
    <div className="code">
      <pre tabIndex={0}>
        <code>
          {shown.map((line) => (
            <span key={line.number} className={line.highlighted ? 'code-line is-cited' : 'code-line'}>
              <span className="code-no" aria-hidden="true">{line.number}</span>
              <span className="code-text">{line.text || ' '}</span>
            </span>
          ))}
        </code>
      </pre>
      {collapsible && lines.length > COLLAPSED_LINES ? (
        <button type="button" className="btn btn-ghost btn-small" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Show less' : `Show ${hidden} more lines`}
        </button>
      ) : null}
    </div>
  );
}
