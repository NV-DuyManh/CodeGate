import { PageHeader } from '../components/ui/PageHeader';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CodeGateAPI } from '../api/client';
import type { RepositoryDashboardItem } from '../types';
import { GitBranch, RefreshCw, Sparkles, FolderGit2 } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { formatPercentage, formatScore, formatDate } from '../lib/utils';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { DEMO_MODE } from '../demo/transport';

export function Repositories() {
  const { workspaceVersion } = useAuth();
  const [data, setData] = useState<RepositoryDashboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('name');

  const load = () => {
    setLoading(true);
    setError(null);
    CodeGateAPI.getRepositories()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspaceVersion]);
  const visible = DEMO_MODE ? data.filter(repo => repo.name.toLowerCase().includes(search.toLowerCase())).sort((a, b) => sort === 'quality' ? (b.average_quality ?? 0) - (a.average_quality ?? 0) : a.name.localeCompare(b.name)) : data;

  if (loading) {
    return (
      <div className="page-stack animate-pulse">
        <Skeleton className="w-full h-16 rounded-2xl" />
        <Skeleton className="w-full h-[400px] rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState onRetry={load} description={error} />
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Repositories"
        description="Connected source code repositories, health metrics, and automated review coverage."
        actions={
          <button className="btn-secondary" onClick={load}>
            <RefreshCw size={16} />Refresh
          </button>
        }
      />
      {DEMO_MODE && <div className="filter-card">
        <label className="search-field"><span className="sr-only">Search repositories</span><input type="search" placeholder="Search repositories…" value={search} onChange={event => setSearch(event.target.value)} /></label>
        <select aria-label="Sort repositories" value={sort} onChange={event => setSort(event.target.value)}><option value="name">Name A–Z</option><option value="quality">Highest quality</option></select>
        <span className="scope-note">{visible.length} sample repositories</span>
      </div>}

      {data.length === 0 ? (
        <div className="py-4">
          <EmptyState
            icon={GitBranch}
            image="/mascot/mascot-empty.jpg"
            title="No repositories connected"
            description="Repositories will appear here once CodeGate has analyzed pull requests from them."
          >
            <Link className="btn-primary" to="/integrations/github">
              <Sparkles size={16} /> Connect GitHub App
            </Link>
          </EmptyState>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="cg-table">
            <caption className="table-caption">{DEMO_MODE ? 'Sample repositories · Explore health and local testing settings.' : 'Loaded results; the API returns up to 20 records.'}</caption>
            <thead>
              <tr>
                <th>Repository</th>
                <th>Provider</th>
                <th>Access Status</th>
                <th>Open PRs</th>
                <th>Avg Quality</th>
                <th>Avg Risk</th>
                <th>Block Rate</th>
                <th>Test Pass Rate</th>
                <th>Last Synced</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((repo) => (
                <tr key={repo.repository_id}>
                  <td>
                    <Link to={`/repositories/${repo.repository_id}`} className="cell-link font-semibold text-[var(--cg-text)] flex items-center gap-2 hover:text-[var(--cg-primary)]">
                      <FolderGit2 size={16} className="text-indigo-500 shrink-0" />
                      <span>{repo.name}</span>
                    </Link>
                  </td>
                  <td>
                    <span className="text-xs font-semibold text-[var(--cg-text-secondary)] bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] px-2 py-0.5 rounded">
                      {repo.provider}
                    </span>
                  </td>
                  <td>
                    {repo.access_status === 'ACTIVE' ? (
                      <Badge variant="success">Active</Badge>
                    ) : repo.access_status === 'ACCESS_REMOVED' ? (
                      <Badge variant="destructive">Access Removed</Badge>
                    ) : (
                      <Badge variant="secondary">{repo.access_status || 'Unknown'}</Badge>
                    )}
                  </td>
                  <td>
                    <span className="font-bold text-[var(--cg-text)]">{repo.open_pr_count ?? 0}</span>
                  </td>
                  <td>
                    {repo.average_quality !== null ? (
                      <span className="font-bold" style={{ color: repo.average_quality >= 80 ? 'var(--cg-green)' : repo.average_quality >= 60 ? 'var(--cg-amber)' : 'var(--cg-red)' }}>
                        {formatScore(repo.average_quality)}
                      </span>
                    ) : (
                      <span className="cell-muted">N/A</span>
                    )}
                  </td>
                  <td>
                    {repo.average_risk !== null ? (
                      <span className="font-bold" style={{ color: repo.average_risk <= 30 ? 'var(--cg-green)' : repo.average_risk <= 70 ? 'var(--cg-amber)' : 'var(--cg-red)' }}>
                        {formatScore(repo.average_risk)}
                      </span>
                    ) : (
                      <span className="cell-muted">N/A</span>
                    )}
                  </td>
                  <td>
                    <span className="font-mono text-[var(--cg-text)]">
                      {repo.block_rate !== null ? formatPercentage(repo.block_rate) : 'N/A'}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono text-[var(--cg-text)]">
                      {repo.test_pass_rate !== null ? formatPercentage(repo.test_pass_rate) : 'N/A'}
                    </span>
                  </td>
                  <td className="cell-muted">
                    {repo.last_synced_at ? formatDate(repo.last_synced_at) : 'Never'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.length > 0 && visible.length === 0 && <p className="alert">No repositories match this search. Try a different name.</p>}
    </div>
  );
}
