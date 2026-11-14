import { useEffect, useRef, useState } from 'react';

export default function NotificationPanel({ items, onNavigate }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') setOpen(false); };
    const onClick = (event) => { if (ref.current && !ref.current.contains(event.target)) setOpen(false); };
    window.addEventListener('keydown', onKey); window.addEventListener('mousedown', onClick);
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onClick); };
  }, [open]);
  return (
    <div className="account" ref={ref}>
      <button type="button" className="avatar bell" aria-haspopup="true" aria-expanded={open} aria-label={`Notifications (${items.length})`} onClick={() => setOpen((v) => !v)}>
        <span aria-hidden="true">◉</span>{items.length ? <i className="bell-dot" aria-hidden="true" /> : null}
      </button>
      {open ? (
        <div className="menu notif-panel" role="region" aria-label="Notifications">
          {items.length === 0 ? <p className="muted notif-empty">All systems ready. Nothing needs attention.</p> : items.map((item) => (
            <button key={item.id} type="button" className="notif" onClick={() => { setOpen(false); onNavigate(item.target); }}>
              <span className={`pill-dot dot-${item.tone}`} aria-hidden="true" />
              <span><strong>{item.title}</strong><small>{item.body}</small></span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
