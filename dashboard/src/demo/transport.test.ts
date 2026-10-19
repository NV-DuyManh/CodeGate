import { beforeEach, describe, expect, it } from 'vitest';
import { createDemoTransport, installDemoTransport } from './transport';

const base = 'http://127.0.0.1:8000/api/v1';
const unavailableNetwork: typeof fetch = async () => new Response('native network', { status: 418 });
const json = async (fetcher: typeof fetch, path: string, method = 'GET', body?: unknown) => {
  const response = await fetcher(base + path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
  expect(response.ok, path).toBe(true);
  return response.json();
};

describe('public demo transport', () => {
  beforeEach(() => localStorage.clear());

  it('provides coherent detail evidence for every visible repository and pull request', async () => {
    const { fetch: demoFetch } = createDemoTransport(unavailableNetwork, localStorage);
    expect((await json(demoFetch, '/auth/me')).username).toBe('demo-viewer');
    const repos = await json(demoFetch, '/dashboard/repositories');
    const prs = await json(demoFetch, '/dashboard/pull-requests');
    expect(repos.length).toBeGreaterThanOrEqual(2);
    expect(prs.length).toBeGreaterThan(5);
    const overview = await json(demoFetch, '/dashboard/overview');
    expect(overview.pull_requests_total).toBe(prs.length);
    expect(overview.policy_pass_count + overview.policy_warning_count + overview.policy_block_count).toBe(prs.length);
    expect(overview.policy_trend.every((point: { pass_count: number; warning_count: number; block_count: number }) => point.pass_count + point.warning_count + point.block_count === 1)).toBe(true);
    for (const repo of repos) {
      const detail = await json(demoFetch, `/dashboard/repositories/${repo.repository_id}`);
      expect(detail.repository.name).toBe(repo.name);
      expect(detail.recent_prs.every((pr: { repository: string }) => pr.repository === repo.name)).toBe(true);
    }
    for (const pr of prs) {
      const detail = await json(demoFetch, `/dashboard/pull-requests/${pr.pull_request_id}`);
      expect(detail.pr.title).toBe(pr.title);
      expect(detail.quality.overall_score).toBe(pr.quality_score);
      expect(detail.policy.decision).toBe(pr.policy_decision);
      expect(detail.tests.passed + detail.tests.failed).toBe(detail.tests.total);
      expect(detail.reviewer_recommendation.length).toBeGreaterThan(0);
      expect(detail.findings.filter((finding: { severity: string }) => finding.severity === 'HIGH')).toHaveLength(pr.high_findings);
      const weighted = (components: { score: number; weight: number }[]) => components.reduce((sum, component) => sum + component.score * component.weight, 0);
      expect(weighted(detail.quality.components)).toBeCloseTo(detail.quality.overall_score);
      expect(weighted(detail.risk.components)).toBeCloseTo(detail.risk.overall_risk);
    }
    expect((await json(demoFetch, '/dashboard/pull-requests/101')).findings.length).toBeGreaterThan(0);
  });

  it('switches tenant data, rejects cross-tenant IDs and preserves the active workspace on reload', async () => {
    const demo = createDemoTransport(unavailableNetwork, localStorage);
    await json(demo.fetch, '/workspaces/2/activate', 'POST');
    const repos = await json(demo.fetch, '/dashboard/repositories');
    expect(repos[0].name).toBe('orbit/mobile-app');
    expect((await demo.fetch(base + '/dashboard/pull-requests/101')).status).toBe(404);
    expect((await demo.fetch(base + '/repositories/1/testing', { method: 'PUT', body: '{}' })).status).toBe(404);
    const restored = createDemoTransport(unavailableNetwork, localStorage);
    expect((await json(restored.fetch, '/auth/me')).active_workspace_id).toBe(2);
  });

  it('persists local testing settings and member edits, then restores the sample with reset', async () => {
    const demo = createDemoTransport(unavailableNetwork, localStorage);
    await json(demo.fetch, '/repositories/1/testing', 'PUT', { test_command: 'pytest -q local-demo', enabled: false });
    await json(demo.fetch, '/workspaces/active/members/12', 'PATCH', { role: 'MAINTAINER' });
    const restored = createDemoTransport(unavailableNetwork, localStorage);
    expect((await json(restored.fetch, '/repositories/1/testing')).test_command).toBe('pytest -q local-demo');
    expect((await json(restored.fetch, '/workspaces/active/members')).members.find((m: { user_id: number }) => m.user_id === 12).role).toBe('MAINTAINER');
    restored.reset();
    expect((await json(restored.fetch, '/repositories/1/testing')).test_command).toBe('pytest --cov=app');
    expect((await json(restored.fetch, '/workspaces/active/members')).members.find((m: { user_id: number }) => m.user_id === 12).role).toBe('REVIEWER');
  });

  it('blocks real execution, OAuth, invites and unknown API paths without claiming success', async () => {
    const demo = createDemoTransport(unavailableNetwork, localStorage);
    for (const path of ['/analyses/501/retry', '/integrations/github/install', '/integrations/github/connections/1/sync', '/auth/github/login', '/workspaces/active/invitations', '/not-implemented']) {
      const res = await demo.fetch(base + path, { method: 'POST' });
      expect(res.status).toBe(501);
      expect((await res.json()).detail).toMatch(/demo/i);
    }
    expect((await demo.fetch('https://example.org/api/v1/auth/me')).status).toBe(418);
    expect((await demo.fetch('http://127.0.0.1:8000/api/v10/auth/me')).status).toBe(418);
  });

  it('leaves live-mode fetch untouched and handles corrupt local storage', async () => {
    const target = { fetch: unavailableNetwork };
    installDemoTransport(false, target, localStorage);
    expect(await (await target.fetch(base + '/auth/me')).text()).toBe('native network');
    localStorage.setItem('codegate-public-demo-v1', '{broken');
    installDemoTransport(true, target, localStorage);
    expect((await json(target.fetch, '/auth/me')).active_workspace_id).toBe(1);
  });
});
