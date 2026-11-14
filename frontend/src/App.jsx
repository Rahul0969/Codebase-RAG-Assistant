import { useEffect, useState } from 'react';
import AskPanel from './components/AskPanel.jsx';
import Dashboard from './components/Dashboard.jsx';
import { TopNav } from './components/Layout.jsx';
import RepositoryPanel from './components/RepositoryPanel.jsx';
import ReportsPanel from './components/ReportsPanel.jsx';
import ImpactPanel from './components/ImpactPanel.jsx';
import SearchPanel from './components/SearchPanel.jsx';
import SettingsPanel from './components/SettingsPanel.jsx';
import { useWorkspace } from './hooks/useWorkspace.js';

export default function App() {
  const workspace = useWorkspace();
  const [view, setView] = useState('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);

  function navigate(next) {
    setView(next);
    setMenuOpen(false);
    window.scrollTo?.(0, 0);
  }

  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); navigate('search'); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') setMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <div className="app">
      <TopNav
        view={view}
        health={workspace.health}
        modelRouting={workspace.modelRouting}
        lastUsedModel={workspace.lastUsedModel}
        repoPath={workspace.repoPath}
        repositoryReady={workspace.repositoryReady}
        menuOpen={menuOpen}
        onToggleMenu={() => setMenuOpen((open) => !open)}
        onNavigate={navigate}
      />
      <div className="main">
        <main className="content" id="content">
          {view === 'dashboard' ? <Dashboard workspace={workspace} onNavigate={navigate} /> : null}
          {/* These pages stay mounted (just hidden) so typed text and results survive navigation. */}
          <div hidden={view !== 'repository'}><RepositoryPanel workspace={workspace} /></div>
          <div hidden={view !== 'search'}><SearchPanel workspace={workspace} /></div>
          <div hidden={view !== 'ask'}><AskPanel workspace={workspace} /></div>
          <div hidden={view !== 'reports'}><ReportsPanel workspace={workspace} /></div>
          <div hidden={view !== 'impact'}><ImpactPanel workspace={workspace} /></div>
          {view === 'settings' ? <SettingsPanel workspace={workspace} /> : null}
        </main>
      </div>
    </div>
  );
}
