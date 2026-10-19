import { defaultTesting, demoWorkspaces, sampleMembers, workspaceFixtures } from './fixtures';

export const DEMO_MODE = import.meta.env.VITE_CODEGATE_DEMO === 'true';
const STORAGE_KEY = 'codegate-public-demo-v1';
type DemoState = {
  activeWorkspaceId: number;
  testing: Record<string, typeof defaultTesting>;
  members: Record<string, ReturnType<typeof sampleMembers>>;
  understood: Record<string, boolean>;
};
const initialState = (): DemoState => ({ activeWorkspaceId: 1, testing: {}, members: {}, understood: {} });

export function createDemoTransport(nativeFetch: typeof fetch, storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>) {
  let state = initialState();
  try {
    const saved = JSON.parse(storage.getItem(STORAGE_KEY) || 'null');
    if (saved && [1, 2].includes(saved.activeWorkspaceId) && saved.testing && saved.members && saved.understood) state = saved;
  } catch { /* An unavailable or old browser store starts a fresh sample session. */ }
  const save = () => { try { storage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* In-memory interactions still work with storage blocked. */ } };
  const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  const unavailable = () => response({ detail: 'Unavailable in this interactive demo. GitHub connections, invitations and analysis execution require a configured live backend.' }, 501);
  const missing = () => response({ detail: 'Sample record not found in this workspace.' }, 404);
  const configuredBase = import.meta.env.VITE_CODEGATE_API_URL;
  const apiBases = ['http://127.0.0.1:8000/api/v1', configuredBase].filter(Boolean).map(base => new URL(base!, window.location.origin));

  const demoFetch: typeof fetch = async (input, options) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request?.url || String(input), window.location.origin);
    const base = apiBases.find(candidate => candidate.origin === url.origin && (url.pathname === candidate.pathname || url.pathname.startsWith(candidate.pathname.replace(/\/$/, '') + '/')));
    if (!base) return nativeFetch(input, options);
    const signal = options?.signal || request?.signal;
    if (signal?.aborted) throw new DOMException('The request was aborted', 'AbortError');
    const path = url.pathname.slice(base.pathname.replace(/\/$/, '').length) || '/';
    const method = (options?.method || request?.method || 'GET').toUpperCase();
    const { repos, prs, overview, prDetail } = workspaceFixtures(state.activeWorkspaceId);
    const memberKey = String(state.activeWorkspaceId);
    const members = () => state.members[memberKey] || sampleMembers(state.activeWorkspaceId);
    const body = async () => {
      try { return JSON.parse(typeof options?.body === 'string' ? options.body : request ? await request.clone().text() : '{}'); }
      catch { return null; }
    };

    if (method === 'GET') {
      if (path === '/auth/me') return response({ id: 10, username: 'demo-viewer', display_name: 'Demo Viewer', avatar_url: null, active_workspace_id: state.activeWorkspaceId });
      if (path === '/workspaces') return response(demoWorkspaces);
      if (path === '/system/status') return response({ status: 'sample', database: { status: 'browser only' }, github: { status: 'not connected' }, data_mode: 'DEMO', version: 'sample-v1' });
      if (path === '/dashboard/overview') return response(overview);
      if (path === '/dashboard/repositories') return response(repos);
      if (path === '/dashboard/pull-requests') return response(prs);
      if (path === '/workspaces/active/members') return response({ members: members(), invitations: [] });
      if (path === '/integrations/github/connections') return response([{ id: state.activeWorkspaceId, account_login: state.activeWorkspaceId === 1 ? 'acme (sample)' : 'orbit (sample)', account_type: 'Sample organization', status: 'sample only', auth_type: 'DEMO', repository_selection: 'selected', installation_id: null, last_sync_status: 'SAMPLE', last_synced_at: null, last_sync_error: null }]);
      const prMatch = path.match(/^\/dashboard\/pull-requests\/(\d+)$/);
      if (prMatch) { const pr = prs.find(pr => pr.pull_request_id === Number(prMatch[1])); return pr ? response(prDetail(pr)) : missing(); }
      const repoMatch = path.match(/^\/dashboard\/repositories\/(\d+)$/);
      if (repoMatch) {
        const repo = repos.find(repo => repo.repository_id === Number(repoMatch[1]));
        if (!repo) return missing();
        const recent = prs.filter(pr => pr.repository === repo.name);
        const distribution = (field: 'quality_grade' | 'risk_level' | 'policy_decision') => recent.reduce<Record<string, number>>((result, pr) => { const key = String(pr[field]); result[key] = (result[key] || 0) + 1; return result; }, {});
        return response({ repository: repo, health: { ...repo, analyses_completed: repo.analysis_count }, policy_summary: { pass_count: repo.policy_pass_count, warning_count: repo.policy_warning_count, block_count: repo.policy_block_count, block_rate: repo.block_rate }, testing_summary: { test_pass_rate: repo.test_pass_rate }, coverage_summary: { average_changed_coverage: repo.average_changed_coverage }, finding_summary: { critical: repo.critical_findings, high: recent.reduce((sum, pr) => sum + pr.high_findings, 0) }, recent_prs: recent, quality_distribution: distribution('quality_grade'), risk_distribution: distribution('risk_level'), policy_distribution: distribution('policy_decision') });
      }
    }

    const activate = path.match(/^\/workspaces\/(\d+)\/activate$/);
    if (activate && method === 'POST') {
      const id = Number(activate[1]);
      if (!demoWorkspaces.some(workspace => workspace.id === id)) return missing();
      state.activeWorkspaceId = id; save(); return response({ active_workspace_id: id });
    }
    const testing = path.match(/^\/repositories\/(\d+)\/testing$/);
    if (testing && ['GET', 'PUT'].includes(method)) {
      if (!repos.some(repo => repo.repository_id === Number(testing[1]))) return missing();
      const key = `${state.activeWorkspaceId}:${testing[1]}`;
      if (method === 'PUT') {
        const config = await body();
        if (!config || typeof config !== 'object') return response({ detail: 'Invalid sample configuration.' }, 400);
        state.testing[key] = { ...defaultTesting, ...state.testing[key], ...config }; save();
      }
      return response(state.testing[key] || defaultTesting);
    }
    const member = path.match(/^\/workspaces\/active\/members\/(\d+)$/);
    if (member && ['PATCH', 'DELETE'].includes(method)) {
      const id = Number(member[1]);
      if (id === 10) return response({ detail: 'Keep the demo viewer as workspace admin.' }, 400);
      if (!members().some(member => member.user_id === id)) return missing();
      if (method === 'DELETE') state.members[memberKey] = members().filter(member => member.user_id !== id);
      else {
        const update = await body();
        if (!['ADMIN', 'MAINTAINER', 'REVIEWER', 'DEVELOPER'].includes(update?.role)) return response({ detail: 'Invalid sample role.' }, 400);
        state.members[memberKey] = members().map(member => member.user_id === id ? { ...member, role: update.role } : member);
      }
      save(); return response({ saved_in_browser: true });
    }
    if (path === '/auth/logout' && method === 'POST') return response({ signed_out: true });
    return unavailable();
  };
  return {
    fetch: demoFetch,
    reset() { state = initialState(); try { storage.removeItem(STORAGE_KEY); } catch { /* Reset also works in memory. */ } },
    getUnderstood(key: string) { return state.understood[key] || false; },
    setUnderstood(key: string, value: boolean) { state.understood[key] = value; save(); },
  };
}

export type DemoTransport = ReturnType<typeof createDemoTransport>;
export let activeDemo: DemoTransport | undefined;

export function installDemoTransport(enabled: boolean, target: { fetch: typeof fetch } = globalThis, storage: Storage = localStorage) {
  if (!enabled) return;
  activeDemo = createDemoTransport(target.fetch.bind(target), storage);
  target.fetch = activeDemo.fetch;
  return activeDemo;
}
