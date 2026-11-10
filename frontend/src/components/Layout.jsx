import { connectionInfo, modelInfo } from '../utils/status.js';
import { repositoryLabel } from '../utils/repo.js';

export const VIEWS = [
  { id: 'dashboard', label: 'Dashboard', icon: '◧' },
  { id: 'repository', label: 'Repository', icon: '▤' },
  { id: 'search', label: 'Code Search', icon: '⌕' },
  { id: 'ask', label: 'Ask Codebase', icon: '✦' },
  { id: 'reports', label: 'Reports', icon: '▧' },
  { id: 'impact', label: 'Change Impact', icon: '⌁' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
];

export function StatusPill({ tone, children }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="pill-dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export function Sidebar({ view, onNavigate, health, open, onClose }) {
  const connection = connectionInfo(health);
  return (
    <>
      {open ? <button type="button" className="scrim" aria-label="Close menu" onClick={onClose} /> : null}
      <aside className={open ? 'sidebar is-open' : 'sidebar'} id="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="logo" aria-hidden="true">{'</>'}</span>
          <span>
            <strong>Codebase RAG</strong>
            <small>Local code assistant</small>
          </span>
        </div>
        <nav>
          <ul>
            {VIEWS.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === view ? 'nav-item is-active' : 'nav-item'}
                  aria-current={item.id === view ? 'page' : undefined}
                  onClick={() => onNavigate(item.id)}
                >
                  <span aria-hidden="true" className="nav-icon">{item.icon}</span>
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-foot">
          <StatusPill tone={connection.tone}>{connection.label}</StatusPill>
          <small>Runs on your computer. Nothing is sent to hosted AI services.</small>
        </div>
      </aside>
    </>
  );
}

export function Header({ health, repoPath, menuOpen, onToggleMenu }) {
  const connection = connectionInfo(health);
  const model = modelInfo(health);
  const repo = repositoryLabel(repoPath);
  return (
    <header className="topbar">
      <button
        type="button"
        className="menu-button"
        aria-label="Open navigation menu"
        aria-expanded={menuOpen}
        aria-controls="sidebar"
        onClick={onToggleMenu}
      >
        ☰
      </button>
      <h1>Codebase RAG Assistant</h1>
      <div className="topbar-status">
        <span className="repo-chip" title={repoPath || 'No repository selected'}>
          {repo ? `Repository: ${repo}` : 'No repository selected'}
        </span>
        <StatusPill tone={connection.tone}>{connection.label}</StatusPill>
        <StatusPill tone={model.tone}>{model.label}</StatusPill>
      </div>
    </header>
  );
}
