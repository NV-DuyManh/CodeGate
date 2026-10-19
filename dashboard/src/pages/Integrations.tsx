import { Link, useOutletContext } from 'react-router-dom';
import { GitBranch, ArrowRight, MessageSquare, Terminal } from 'lucide-react';
import { useState, useEffect } from 'react';
import { CodeGateAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Badge } from '../components/ui/Badge';
import { DEMO_MODE } from '../demo/transport';

export function Integrations() {
  const { workspaceVersion } = useAuth();
  const system = useOutletContext<{ sysStatus: any; apiError: boolean } | undefined>();
  const [ghStatus, setGhStatus] = useState<string>('Checking...');

  useEffect(() => {
    if (system) {
      setGhStatus(
        system.apiError
          ? 'Unavailable'
          : !system.sysStatus
          ? 'Checking...'
          : system.sysStatus.github?.status === 'CONNECTED'
          ? 'Configured'
          : 'Not Configured'
      );
      return;
    }
    CodeGateAPI.getSystemStatus()
      .then((sys: any) => {
        setGhStatus(sys?.github?.status === 'CONNECTED' ? 'Configured' : 'Not Configured');
      })
      .catch(() => setGhStatus('Unavailable'));
  }, [workspaceVersion, system]);

  return (
    <div className="page-stack">
      <PageHeader
        title="Integrations"
        description="Connect your git providers, CI/CD runners, and notification channels to power automated reviews."
      />

      <div className="grid grid-cols-1 gap-4">
        {/* Active GitHub Integration */}
        <Link className="service-row group" to="/integrations/github">
          <div className="w-14 h-14 rounded-2xl bg-slate-900 text-white flex items-center justify-center flex-shrink-0 shadow-md group-hover:scale-105 transition-transform border border-slate-700">
            <GitBranch size={28} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-base font-bold text-[var(--cg-text)]">GitHub App</h2>
              <Badge variant={ghStatus === 'Configured' ? 'success' : 'default'}>
                {DEMO_MODE ? 'Sample preview' : ghStatus === 'Configured' ? 'Active' : 'Setup Required'}
              </Badge>
            </div>
            <p className="text-sm text-[var(--cg-text-secondary)]">Automated webhooks, repository sync, and pull request analysis bot.</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-[var(--cg-muted)]" role="status">
              {DEMO_MODE ? 'No live connection' : ghStatus}
            </span>
            <div className="w-8 h-8 rounded-full bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)] flex items-center justify-center text-[var(--cg-muted)] group-hover:text-indigo-500 transition-colors">
              <ArrowRight size={16} />
            </div>
          </div>
        </Link>

        {/* Coming Soon Preview Integrations */}
        <div className="service-row opacity-75">
          <div className="w-14 h-14 rounded-2xl bg-orange-500/10 text-orange-500 border border-orange-500/20 flex items-center justify-center flex-shrink-0">
            <Terminal size={26} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-base font-bold text-[var(--cg-text)]">GitLab CI & Webhooks</h2>
              <Badge variant="outline">Coming Soon</Badge>
            </div>
            <p className="text-sm text-[var(--cg-text-secondary)]">Merge request scanning and pipeline feedback for GitLab teams.</p>
          </div>
        </div>

        <div className="service-row opacity-75">
          <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 text-indigo-500 border border-indigo-500/20 flex items-center justify-center flex-shrink-0">
            <MessageSquare size={26} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-base font-bold text-[var(--cg-text)]">Discord & Slack Coach Bot</h2>
              <Badge variant="outline">Coming Soon</Badge>
            </div>
            <p className="text-sm text-[var(--cg-text-secondary)]">Daily review digests and student coaching notifications in your chat channels.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
