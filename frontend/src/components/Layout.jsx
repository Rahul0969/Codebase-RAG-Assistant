import { useEffect, useRef, useState } from 'react';
import { connectionInfo, modelInfo } from '../utils/status.js';
import { repositoryLabel } from '../utils/repo.js';
import NotificationPanel from './NotificationPanel.jsx';
import { buildNotifications } from '../utils/notifications.js';

// Primary tabs follow the redesign: Dashboard, Search, Ask, Impact, Reports.
export const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'search', label: 'Search' },
  { id: 'ask', label: 'Ask' },
  { id: 'impact', label: 'Impact' },
  { id: 'reports', label: 'Reports' },
];

export function StatusPill({ tone, children }) {
  return <span className={`pill pill-${tone}`}><span className="pill-dot" aria-hidden="true" />{children}</span>;
}

function AccountMenu({ view, onNavigate }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') setOpen(false); };
    const onClick = (event) => { if (ref.current && !ref.current.contains(event.target)) setOpen(false); };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onClick); };
  }, [open]);
  const go = (id) => { setOpen(false); onNavigate(id); };
  return (
    <div className="account" ref={ref}>
      <button type="button" className="avatar" aria-haspopup="menu" aria-expanded={open} aria-label="Workspace menu" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden="true">◎</span>
      </button>
      {open ? (
        <div className="menu" role="menu">
          <button type="button" role="menuitem" className={view === 'repository' ? 'menu-item is-active' : 'menu-item'} onClick={() => go('repository')}>Repository</button>
          <button type="button" role="menuitem" className={view === 'settings' ? 'menu-item is-active' : 'menu-item'} onClick={() => go('settings')}>Settings</button>
        </div>
      ) : null}
    </div>
  );
}

export function TopNav({ view, onNavigate, health, modelRouting, lastUsedModel, repoPath, repositoryReady, menuOpen, onToggleMenu }) {
  const connection = connectionInfo(health);
  const model = modelInfo(health, modelRouting, lastUsedModel);
  const repo = repositoryLabel(repoPath);
  return (
    <header className="topnav">
      <button type="button" className="menu-button" aria-label="Toggle navigation menu" aria-expanded={menuOpen} aria-controls="primary-nav" onClick={onToggleMenu}>☰</button>
      <button type="button" className="brand" onClick={() => onNavigate('dashboard')} aria-label="Codebase RAG Assistant home">
        <span className="logo" aria-hidden="true">CR</span>
        <strong>Codebase RAG</strong>
      </button>
      <button type="button" className="repo-select" onClick={() => onNavigate('repository')} title={repoPath || 'No repository selected'}>
        <span aria-hidden="true">▣</span><span className="repo-select-name">{repo || 'No repository selected'}</span><span aria-hidden="true">›</span>
      </button>
      <nav className={menuOpen ? 'primary-nav is-open' : 'primary-nav'} id="primary-nav" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <button key={item.id} type="button" className={item.id === view ? 'tab is-active' : 'tab'} aria-current={item.id === view ? 'page' : undefined} onClick={() => onNavigate(item.id)}>{item.label}</button>
        ))}
        <button type="button" className={view === 'repository' ? 'tab is-active' : 'tab'} onClick={() => onNavigate('repository')}>Repository</button>
      </nav>
      <div className="sidebar-bottom"><button type="button" className={view === 'settings' ? 'tab is-active' : 'tab'} onClick={() => onNavigate('settings')}>Settings</button><span className="sidebar-note">Local-first · Private</span></div>
      <div className="topnav-right">
        <StatusPill tone={connection.tone}>{connection.label}</StatusPill>
        <StatusPill tone={model.tone}>{model.label}</StatusPill>
        <button type="button" className="global-search" onClick={() => onNavigate('search')} aria-label="Search code (Ctrl K)"><span aria-hidden="true">⌕</span><span>Search</span><kbd>Ctrl K</kbd></button>
        <NotificationPanel items={buildNotifications({ health, repoPath, repositoryReady })} onNavigate={onNavigate} />
        <AccountMenu view={view} onNavigate={onNavigate} />
      </div>
    </header>
  );
}
