import { describeError } from '../services/errors.js';

export function Spinner({ label }) {
  return (
    <span className="spinner-wrap" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

export function ErrorNotice({ error, baseUrl }) {
  if (!error) return null;
  const info = describeError(error, { baseUrl });
  return (
    <div className="notice notice-bad" role="alert">
      <strong>{info.title}</strong>
      {info.message ? <p>{info.message}</p> : null}
      {info.hint ? <p className="hint">{info.hint}</p> : null}
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
    </div>
  );
}
