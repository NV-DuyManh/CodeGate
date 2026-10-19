import { PageHeader } from '../components/ui/PageHeader';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CodeGateAPI } from '../api/client';
import type { PRDashboardItem } from '../types';
import { GitPullRequest, RefreshCw, Search } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { formatPercentage, formatDate } from '../lib/utils';
import { Badge } from '../components/ui/Badge';
import { useAuth } from '../contexts/AuthContext';
import { DEMO_MODE } from '../demo/transport';

export function PullRequests() {
  const { workspaceVersion } = useAuth();
  const [data, setData] = useState<PRDashboardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [policyFilter, setPolicyFilter] = useState('ALL');
  const [stateFilter, setStateFilter] = useState('ALL');
  const [repositoryFilter, setRepositoryFilter] = useState('ALL');
  const [page, setPage] = useState(1);

  const load = () => {
    setPage(1);
    setRepositoryFilter('ALL');
    setLoading(true);
    setError(null);
    CodeGateAPI.getPullRequests()
      .then((prs) => setData(prs))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspaceVersion]);

  const filtered = data.filter((pr) => {
    if (policyFilter !== 'ALL' && pr.policy_decision !== policyFilter) return false;
    if (stateFilter !== 'ALL' && pr.state !== stateFilter) return false;
    if (repositoryFilter !== 'ALL' && pr.repository !== repositoryFilter) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return pr.title.toLowerCase().includes(s) ||
           pr.author.toLowerCase().includes(s) ||
           pr.repository.toLowerCase().includes(s);
  });
  const pages = Math.max(1, Math.ceil(filtered.length / 5));
  const visible = DEMO_MODE ? filtered.slice((page - 1) * 5, page * 5) : filtered;

  if (loading) {
    return (
      <div className="page-stack animate-pulse">
        <Skeleton className="w-full h-16 rounded-2xl" />
        <Skeleton className="w-full h-[64px] rounded-2xl" />
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
        title="Pull Requests"
        description="Review queue, automated scans, and student lesson insights."
        actions={
          <button className="btn-secondary" onClick={load}>
            <RefreshCw size={16} />Refresh
          </button>
        }
      />

      <div className="filter-card">
        <label className="search-field">
          <span className="sr-only">Search pull requests</span>
          <Search size={16} />
          <input
            type="search"
            placeholder="Search title, author, repository…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
          />
        </label>
        {DEMO_MODE && <>
          <select aria-label="Policy filter" value={policyFilter} onChange={event => { setPolicyFilter(event.target.value); setPage(1); }}>
            <option value="ALL">All policies</option><option value="PASS">Pass</option><option value="WARNING">Warning</option><option value="BLOCK">Block</option>
          </select>
          <select aria-label="State filter" value={stateFilter} onChange={event => { setStateFilter(event.target.value); setPage(1); }}>
            <option value="ALL">All states</option><option value="OPEN">Open</option><option value="MERGED">Merged</option>
          </select>
          <select aria-label="Repository filter" value={repositoryFilter} onChange={event => { setRepositoryFilter(event.target.value); setPage(1); }}>
            <option value="ALL">All repositories</option>{[...new Set(data.map(pr => pr.repository))].map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </>}
        <span className="scope-note font-medium text-slate-500">
          {filtered.length} of {data.length} loaded pull requests
        </span>
      </div>

      {/* TABLE or EMPTY STATE */}
      {filtered.length === 0 ? (
        <div className="py-4">
          <EmptyState
            icon={GitPullRequest}
            image={data.length === 0 ? "/mascot/mascot-empty.jpg" : undefined}
            title={data.length === 0 ? "No pull requests yet" : "No results found"}
            description={
              data.length === 0
                ? "Pull requests will appear here after CodeGate receives a GitHub webhook or an analysis is created."
                : "Try adjusting your search terms."
            }
          />
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="cg-table">
            <caption className="table-caption">{DEMO_MODE ? 'Sample pull requests · Select a row to explore review evidence.' : 'Loaded results; the API returns up to 20 records.'}</caption>
            <thead>
              <tr>
                <th>Pull Request</th>
                <th>Repository</th>
                <th>Author</th>
                <th>Quality</th>
                <th>Risk</th>
                <th>Policy</th>
                <th>Tests</th>
                <th>Coverage</th>
                <th>Findings</th>
                <th>Analysis</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((pr) => (
                <tr key={pr.pull_request_id}>
                  <td>
                    <Link to={`/pull-requests/${pr.pull_request_id}`} className="cell-link font-semibold text-[var(--cg-text)] hover:text-[var(--cg-primary)]">
                      {pr.title}
                    </Link>
                    <div className="cell-muted" style={{ marginTop: '2px' }}>
                      <span className="font-bold text-indigo-500">#{pr.number}</span> · {pr.state}
                    </div>
                  </td>
                  <td className="font-medium text-[var(--cg-text-secondary)]">{pr.repository}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] text-[var(--cg-text)] text-xs font-bold flex items-center justify-center">
                        {pr.author?.charAt(0)?.toUpperCase() || '?'}
                      </span>
                      <span className="text-[var(--cg-text)]">{pr.author}</span>
                    </div>
                  </td>
                  <td>
                    {pr.quality_score != null ? (
                      <div className="flex items-center gap-2">
                        <Badge variant={pr.quality_grade === 'A' ? 'success' : pr.quality_grade === 'B' ? 'success' : pr.quality_grade === 'C' ? 'warning' : 'danger'}>
                          {pr.quality_grade}
                        </Badge>
                        <span className="cell-muted font-bold">{pr.quality_score.toFixed(0)}</span>
                      </div>
                    ) : (
                      <span className="cell-muted">N/A</span>
                    )}
                  </td>
                  <td>
                    {pr.risk_level ? (
                      <Badge variant={pr.risk_level === 'LOW' ? 'success' : pr.risk_level === 'MEDIUM' ? 'warning' : 'danger'}>
                        {pr.risk_level}
                      </Badge>
                    ) : (
                      <span className="cell-muted">N/A</span>
                    )}
                  </td>
                  <td>
                    <Badge variant={pr.policy_decision === 'PASS' ? 'success' : pr.policy_decision === 'WARNING' ? 'warning' : pr.policy_decision === 'BLOCK' ? 'danger' : 'default'}>
                      {pr.policy_decision || 'Not evaluated'}
                    </Badge>
                  </td>
                  <td>
                    {pr.test_outcome ? (
                      <Badge variant={pr.test_outcome === 'PASSED' ? 'success' : pr.test_outcome === 'FAILED' ? 'danger' : 'default'}>
                        {pr.test_outcome}
                      </Badge>
                    ) : (
                      <span className="cell-muted">N/A</span>
                    )}
                  </td>
                  <td>
                    <span className="font-mono font-medium">
                      {pr.changed_line_coverage != null ? formatPercentage(pr.changed_line_coverage) : 'N/A'}
                    </span>
                  </td>
                  <td>
                    {(pr.critical_findings + pr.high_findings) > 0 ? (
                      <Badge variant="danger">
                        {pr.critical_findings + pr.high_findings}
                      </Badge>
                    ) : (
                      <span className="cell-muted">0</span>
                    )}
                  </td>
                  <td>
                    <Badge variant={pr.analysis_status === 'COMPLETED' ? 'success' : pr.analysis_status === 'FAILED' ? 'danger' : ['RUNNING', 'QUEUED'].includes(pr.analysis_status || '') ? 'info' : 'default'}>
                      {pr.analysis_status || 'Not run'}
                    </Badge>
                  </td>
                  <td className="cell-muted">
                    {pr.updated_at ? formatDate(pr.updated_at) : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {DEMO_MODE && filtered.length > 0 && <nav className="pagination-controls" aria-label="Pull request pages">
        <span>Showing {(page - 1) * 5 + 1}–{Math.min(page * 5, filtered.length)} of {filtered.length} sample pull requests</span>
        <div className="flex gap-3 items-center"><button className="btn-secondary" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(current => current - 1)}>Previous</button><span>Page {page} of {pages}</span><button className="btn-secondary" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(current => current + 1)}>Next</button></div>
      </nav>}
    </div>
  );
}
