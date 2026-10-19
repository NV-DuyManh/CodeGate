import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { GitBranch, Shield, Sparkles, BookOpen } from 'lucide-react';
import { AuthShell } from '../components/ui/AuthShell';
import { Skeleton } from '../components/ui/Skeleton';
import { DEMO_MODE } from '../demo/transport';

export function Login() {
  const { authenticated, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!DEMO_MODE && !loading && authenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [authenticated, loading, navigate]);

  const handleLogin = () => {
    if (DEMO_MODE) { navigate('/dashboard'); return; }
    window.location.href = 'http://127.0.0.1:8000/api/v1/auth/github/login';
  };

  if (loading) {
    return (
      <div className="auth-page">
        <Skeleton className="h-32 w-full max-w-md rounded-2xl" />
      </div>
    );
  }

  return (
    <AuthShell
      title="Welcome to CodeGate"
      description={DEMO_MODE ? 'Explore a sample engineering workspace. No account required.' : 'Sign in to your engineering workspace.'}
      badgeText={DEMO_MODE ? 'Interactive demo · Sample data' : 'Next-Gen Automated Code Review'}
    >
      <div className="flex flex-col gap-4">
        <button
          onClick={handleLogin}
          className="btn-primary w-full py-3 text-[15px] shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/35"
        >
          <GitBranch size={19} strokeWidth={2.2} />
          {DEMO_MODE ? 'Explore demo' : 'Continue with GitHub'}
        </button>

        <p className="text-center text-xs text-slate-500 font-medium">
          {DEMO_MODE ? 'Sample data only. Changes stay in this browser.' : 'Authentication is handled by GitHub.'}
        </p>

        <div className="border-t border-[var(--cg-border-soft)] pt-4 mt-2 grid grid-cols-3 gap-2 text-center">
          <div className="p-2 rounded-xl bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)]">
            <Sparkles size={16} className="mx-auto text-indigo-500 mb-1" />
            <div className="text-[11px] font-bold text-[var(--cg-text)]">Smart PRs</div>
            <div className="text-[10px] text-[var(--cg-muted)]">Automated AI scan</div>
          </div>
          <div className="p-2 rounded-xl bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)]">
            <BookOpen size={16} className="mx-auto text-purple-500 mb-1" />
            <div className="text-[11px] font-bold text-[var(--cg-text)]">Lessons</div>
            <div className="text-[10px] text-[var(--cg-muted)]">Best practice tips</div>
          </div>
          <div className="p-2 rounded-xl bg-[var(--cg-surface-soft)] border border-[var(--cg-border-soft)]">
            <Shield size={16} className="mx-auto text-emerald-500 mb-1" />
            <div className="text-[11px] font-bold text-[var(--cg-text)]">Policy Gate</div>
            <div className="text-[10px] text-[var(--cg-muted)]">Block bad commits</div>
          </div>
        </div>
      </div>
    </AuthShell>
  );
}
