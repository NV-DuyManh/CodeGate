import { PageHeader } from '../components/ui/PageHeader';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { formatDate } from '../lib/utils';
import { useEffect, useState } from 'react';
import { CodeGateAPI } from '../api/client';
import { RefreshCw, ExternalLink, Plus, Trash2, GitBranch } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { DEMO_MODE } from '../demo/transport';

export function GitHubIntegration() {
  const { workspaceVersion, user } = useAuth();
  const [connections, setConnections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    CodeGateAPI.getGitHubConnections()
      .then(setConnections)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspaceVersion]);

  const handleConnect = async () => {
    try {
      setInstalling(true);
      setError(null);
      const res = await CodeGateAPI.installGitHubApp();
      window.location.href = res.install_url;
    } catch (err: any) {
      setError(err.message || 'Failed to start GitHub installation');
      setInstalling(false);
    }
  };

  const handleDisconnect = async (id: number) => {
    if (!confirm('Are you sure you want to disconnect this installation? Repository history will be preserved.')) return;
    try {
      await CodeGateAPI.disconnectGitHubConnection(id);
      load();
    } catch (err: any) {
      alert('Failed to disconnect: ' + err.message);
    }
  };

  const handleSync = async (id: number) => {
    try {
      setSyncingId(id);
      setError(null);
      setSyncResult(null);
      const res = await CodeGateAPI.syncGitHubConnection(id);
      setSyncResult(`Sync complete: Discovered ${res.discovered}, Created ${res.created}, Updated ${res.updated}, Removed Access ${res.removed_access}.`);
      load();
    } catch (err: any) {
      setError(`Sync failed: ${err.message}`);
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        title="GitHub Integration"
        description="Connect your GitHub organization or personal repositories for automated review triggers."
        actions={
          <div className="flex items-center gap-2">
            <button className="btn-secondary" onClick={load} disabled={loading}>
              <RefreshCw size={16} className={loading ? 'spin' : ''} />Refresh
            </button>
            <button
              className="btn-primary"
              onClick={handleConnect}
              disabled={DEMO_MODE || installing || !user?.active_workspace_id}
              title={DEMO_MODE ? 'A live backend is required to connect GitHub.' : undefined}
            >
              <Plus size={16} />{installing ? 'Connecting...' : 'Connect GitHub'}
            </button>
          </div>
        }
      />
      {DEMO_MODE && <p className="alert">Sample integration preview. A live backend is required to install, sync or manage GitHub connections. No GitHub account is connected.</p>}

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
          <button className="btn-secondary ml-auto text-xs py-1 px-3" onClick={load}>Retry</button>
        </div>
      )}

      {!DEMO_MODE && window.location.search.includes('github=connected') && (
        <p className="alert alert--success" role="status">
          GitHub installation connected successfully! Initial repository sync is running in the background.
        </p>
      )}

      {syncResult && (
        <p className="alert alert--success" role="status">
          {syncResult}
        </p>
      )}

      <section>
        <div className="section-heading">
          <div className="flex items-center gap-2">
            <h2>Installed accounts</h2>
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
              {connections.length}
            </span>
          </div>
          <span className="muted">{connections.length} connections</span>
        </div>

        {loading ? (
          <Skeleton className="h-48 w-full rounded-2xl animate-pulse" />
        ) : connections.length === 0 ? (
          !error && (
            <EmptyState
              icon={GitBranch}
              image="/mascot/mascot-empty.jpg"
              title="No GitHub connections found for this workspace"
              description="Use Connect GitHub to install the app and select repositories."
            >
              <button
                className="btn-primary"
                onClick={handleConnect}
                disabled={DEMO_MODE || installing || !user?.active_workspace_id}
              >
                <Plus size={16} />Connect GitHub
              </button>
            </EmptyState>
          )
        ) : (
          <div className="table-wrapper">
            <table className="cg-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Repository access</th>
                  <th>Status</th>
                  <th>Last sync</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connections.map(c => (
                  <tr key={c.id}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center font-bold text-slate-800 text-xs">
                          {c.account_login?.charAt(0)?.toUpperCase() || 'G'}
                        </div>
                        <div>
                          <strong>{c.account_login}</strong>
                          <p className="cell-muted">{c.account_type}</p>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="text-xs font-medium text-slate-700 bg-slate-100 px-2.5 py-1 rounded-md">
                        {c.repository_selection === 'all' ? 'All repositories' : 'Selected repositories'}
                      </span>
                    </td>
                    <td>
                      <Badge variant={c.status === 'active' ? 'success' : c.status === 'disconnected' ? 'default' : 'warning'}>
                        {c.status}
                      </Badge>
                    </td>
                    <td>
                      <Badge variant={c.last_sync_status === 'SUCCESS' ? 'success' : c.last_sync_status === 'FAILED' ? 'danger' : c.last_sync_status === 'RUNNING' ? 'info' : 'default'}>
                        {c.last_sync_status || 'Not run'}
                      </Badge>
                      {c.last_synced_at && <p className="cell-muted mt-1">{formatDate(c.last_synced_at)}</p>}
                      {c.last_sync_error && <p className="text-danger mt-1 max-w-xs break-words">{c.last_sync_error}</p>}
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          className="btn-secondary text-xs py-1.5 px-3"
                          onClick={() => handleSync(c.id)}
                          disabled={DEMO_MODE || syncingId === c.id}
                        >
                          <RefreshCw size={13} className={syncingId === c.id ? 'spin' : ''} />
                          {syncingId === c.id ? 'Syncing...' : 'Sync now'}
                        </button>
                        {DEMO_MODE ? <span className="cell-muted text-xs">Manage repositories requires live GitHub</span> : <a
                          className="btn-link text-xs flex items-center gap-1"
                          href={`https://github.com/settings/installations/${c.installation_id}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Manage repositories<ExternalLink size={13} />
                        </a>}
                        <button
                          className="btn-danger text-xs py-1.5 px-3"
                          onClick={() => handleDisconnect(c.id)}
                          disabled={DEMO_MODE || c.status === 'disconnected'}
                        >
                          <Trash2 size={13} />Disconnect
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
