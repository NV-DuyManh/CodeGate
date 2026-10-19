import { NavLink, Outlet } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { CodeGateAPI } from '../api/client';
import {
  LayoutDashboard, GitBranch, GitPullRequest, ChartNoAxesCombined,
  LogOut, ChevronDown, Users, Menu, X, Plug, Check,
} from 'lucide-react';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { DEMO_MODE } from '../demo/transport';
import { DemoBanner } from '../demo/DemoBanner';

export function AppLayout() {
  const { user, workspaces, activeWorkspace, setActiveWorkspace, logout } = useAuth();
  const [sysStatus, setSysStatus] = useState<any>(null);
  const [apiError, setApiError] = useState(false);
  const [showWorkspaceMenu, setShowWorkspaceMenu] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const header = useRef<HTMLElement>(null);

  useEffect(() => {
    CodeGateAPI.getSystemStatus()
      .then(data => { setSysStatus(data); setApiError(false); })
      .catch(() => setApiError(true));
  }, []);

  useEffect(() => {
    const dismiss = (event: PointerEvent) => {
      if (!header.current?.contains(event.target as Node)) {
        setShowWorkspaceMenu(false);
        setShowUserMenu(false);
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowWorkspaceMenu(false);
        setShowUserMenu(false);
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', escape);
    };
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const focusables = sidebar.current?.querySelectorAll<HTMLElement>('a, button');
    focusables?.[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !focusables?.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { document.removeEventListener('keydown', trap); menuButton.current?.focus(); };
  }, [mobileMenuOpen]);

  const navItems = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Repositories', href: '/repositories', icon: GitBranch },
    { name: 'Pull Requests', href: '/pull-requests', icon: GitPullRequest },
    { name: 'Analytics', href: '/analytics', icon: ChartNoAxesCombined },
    { name: 'Workspace Members', href: '/settings/members', icon: Users },
    { name: 'Integrations', href: '/integrations', icon: Plug },
  ];
  const apiStatusStr = apiError ? 'OFFLINE' : (sysStatus?.status === 'healthy' ? 'READY' : (sysStatus?.status || 'READY'));
  const dbStatusStr = apiError ? 'UNKNOWN' : (sysStatus?.database?.status?.toUpperCase() || 'CONNECTED');
  const ghStatusStr = apiError ? 'UNKNOWN' : (sysStatus?.github?.status?.toUpperCase() || 'NOT_CONFIGURED');
  const getStatusColor = (status: string) => {
    if (status === 'READY' || status === 'CONNECTED') return '#10b981';
    if (status === 'OFFLINE' || status === 'DISCONNECTED') return '#ef4444';
    if (status === 'UNKNOWN') return '#94a3b8';
    return '#d97706';
  };
  const isDemo = sysStatus?.data_mode === 'DEMO';
  const isLive = sysStatus?.github?.status?.toUpperCase() === 'CONNECTED' && !isDemo;

  return (
    <div className={`app-layout${DEMO_MODE ? ' app-layout--demo' : ''}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      {mobileMenuOpen && <div className="sidebar-backdrop" onClick={() => setMobileMenuOpen(false)} />}
      <aside ref={sidebar} id="app-navigation" aria-label="Main navigation" className={`sidebar ${mobileMenuOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__brand">
          <img src="/mascot/mascot-logo.png" alt="CodeGate Mascot" className="brand-mascot" />
          <div className="flex flex-col">
            <span className="leading-tight flex items-center gap-1.5">
              CodeGate
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/25 text-indigo-300">Beta</span>
            </span>
            <span className="text-[11px] font-normal text-slate-400">Code Reviews & Coaching</span>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <ThemeToggle className="sm:hidden" />
            <button className="mobile-toggle icon-button text-slate-400 hover:text-white" aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)}><X size={20} /></button>
          </div>
        </div>
        <nav className="sidebar__nav" aria-label="Workspace">
          {navItems.map((item, index) => (
            <div key={item.href}>
              {index === 4 && <p className="sidebar__section">Settings & Workspace</p>}
              <NavLink to={item.href} className="sidebar__link" onClick={() => setMobileMenuOpen(false)}>
                <item.icon size={18} strokeWidth={2} />{item.name}
              </NavLink>
            </div>
          ))}
        </nav>
        <div className="sidebar__status" aria-live="polite">
          <div className="flex items-center justify-between mb-2">
            <p className="sidebar__status-title mb-0">{DEMO_MODE ? 'Demo environment' : 'System Monitor'}</p>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </div>
          <div className="sidebar__status-row">
            <div className="flex items-center gap-2">
              <span className="sidebar__status-dot" style={{ background: getStatusColor(apiStatusStr) }} />
              <span className="capitalize text-slate-200">API {apiStatusStr.toLowerCase()}</span>
            </div>
          </div>
          <div className="sidebar__status-row">
            <div className="flex items-center gap-2">
              <span className="sidebar__status-dot" style={{ background: getStatusColor(dbStatusStr) }} />
              <span className="capitalize text-slate-200">DB {dbStatusStr.toLowerCase()}</span>
            </div>
          </div>
          <div className="sidebar__status-row">
            <div className="flex items-center gap-2">
              <span className="sidebar__status-dot" style={{ background: getStatusColor(ghStatusStr) }} />
              <span className="capitalize text-slate-200">GitHub {ghStatusStr.toLowerCase().replaceAll('_', ' ')}</span>
            </div>
          </div>
        </div>
      </aside>
      <div className="app-body" inert={mobileMenuOpen || undefined}>
        <header ref={header} className="topbar">
          <div className="topbar__group">
            <button ref={menuButton} className="mobile-toggle icon-button" aria-label="Open navigation" aria-expanded={mobileMenuOpen} aria-controls="app-navigation" onClick={() => setMobileMenuOpen(true)}><Menu size={20} /></button>
            <div className="relative">
              <button className="workspace-trigger" aria-expanded={showWorkspaceMenu} aria-controls="workspace-menu" onClick={() => { setShowWorkspaceMenu(!showWorkspaceMenu); setShowUserMenu(false); }}>
                <span className="text-xs uppercase font-bold tracking-wider text-[var(--cg-primary)] bg-[var(--cg-primary-light)] px-2 py-0.5 rounded">Workspace</span>
                <span className="font-semibold text-[var(--cg-text)]">{activeWorkspace?.name || 'Select Workspace'}</span><ChevronDown size={14} className="text-[var(--cg-muted)]" />
              </button>
              {showWorkspaceMenu && <div id="workspace-menu" className="dropdown" aria-label="Workspaces">
                <div className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-[var(--cg-muted)]">Available Workspaces</div>
                {workspaces.map(workspace => <button key={workspace.id} aria-pressed={activeWorkspace?.id === workspace.id}
                  onClick={() => { setActiveWorkspace(workspace.id); setShowWorkspaceMenu(false); }}>
                  <span className="flex-1 truncate">{workspace.name}</span>{activeWorkspace?.id === workspace.id && <Check size={16} className="text-[var(--cg-primary)]" />}
                </button>)}
              </div>}
            </div>
          </div>
          <div className="topbar__group">
            <div className="topbar__data-mode">
              {isDemo && <Badge variant="warning">DEMO MODE</Badge>}
              {isLive && <Badge variant="success">LIVE GITHUB</Badge>}
            </div>
            <ThemeToggle />
            <div className="relative">
              <button className="flex items-center gap-2.5 py-1.5 px-2 rounded-xl hover:bg-[var(--cg-surface-soft)] transition-colors" aria-label="Account menu" aria-expanded={showUserMenu} aria-controls="account-menu" onClick={() => { setShowUserMenu(!showUserMenu); setShowWorkspaceMenu(false); }}>
                {user?.avatar_url ? <img src={user.avatar_url} alt="" className="avatar" /> : <span className="avatar">{user?.username?.charAt(0).toUpperCase() || 'U'}</span>}
                <span className="topbar__user-name font-semibold text-[var(--cg-text)] text-[13.5px]">{user?.display_name || user?.username || 'User'}</span>
                <ChevronDown size={14} className="text-[var(--cg-muted)]" />
              </button>
              {showUserMenu && <div id="account-menu" className="dropdown dropdown--right">
                <div className="px-3 py-2 border-b border-[var(--cg-border-soft)]">
                  <p className="font-semibold text-[var(--cg-text)] text-sm">{user?.display_name || user?.username}</p>
                  <p className="text-xs text-[var(--cg-muted)]">@{user?.username}</p>
                </div>
                <button onClick={() => logout()} className="text-rose-500 hover:bg-rose-500/10 hover:text-rose-400 mt-1"><LogOut size={16} />Sign out</button>
              </div>}
            </div>
          </div>
        </header>
        {DEMO_MODE && <DemoBanner />}
        <main id="main-content" tabIndex={-1} className="content"><Outlet context={{ sysStatus, apiError }} /></main>
      </div>
    </div>
  );
}
