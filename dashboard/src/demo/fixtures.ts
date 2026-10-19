import type { PRDashboardItem, PullRequestDashboardDetail, RepositoryDashboardItem } from '../types';

export const demoWorkspaces = [
  { id: 1, name: 'Acme Engineering', slug: 'acme-demo', role: 'ADMIN' },
  { id: 2, name: 'Orbit Labs', slug: 'orbit-demo', role: 'ADMIN' },
];

const titles = [
  'Harden payment webhook signature validation', 'Cache product search results',
  'Add accessible checkout form', 'Extract order validation service',
  'Improve API timeout handling', 'Add inventory regression tests',
  'Simplify account settings navigation', 'Add structured request logging',
  'Fix pagination boundary on catalog', 'Upgrade session cookie defaults',
  'Document release checklist', 'Cover concurrent cart updates',
];

export function workspaceFixtures(workspaceId: number) {
  const orbit = workspaceId === 2;
  const names = orbit ? ['orbit/mobile-app', 'orbit/design-system'] : ['acme/payments-api', 'acme/storefront', 'acme/platform'];
  const ids = orbit ? [21, 22] : [1, 2, 3];
  const prs: PRDashboardItem[] = (orbit ? titles.slice(0, 7) : titles).map((title, index) => {
    const variant = index % 6;
    const quality = [61, 76, 94, 89, 92, 87][variant];
    const risk = [79, 48, 16, 23, 19, 27][variant];
    const decision = variant === 0 ? 'BLOCK' : variant === 1 ? 'WARNING' : 'PASS';
    return {
      pull_request_id: (orbit ? 201 : 101) + index,
      repository: names[index % names.length], number: (orbit ? 81 : 241) + index,
      title: orbit && index === 0 ? 'Protect offline sync from duplicate writes' : title,
      author: ['maya-chen', 'alex-rivera', 'sam-patel'][index % 3],
      state: index > 8 ? 'MERGED' : 'OPEN', latest_analysis_id: (orbit ? 601 : 501) + index,
      analysis_status: 'COMPLETED', quality_score: quality, quality_grade: quality >= 90 ? 'A' : quality >= 80 ? 'B' : 'C',
      risk_score: risk, risk_level: risk >= 70 ? 'HIGH' : risk >= 40 ? 'MEDIUM' : 'LOW',
      policy_decision: decision, test_outcome: variant === 0 ? 'FAILED' : 'PASSED',
      changed_line_coverage: variant === 0 ? 58 : variant === 1 ? 74 : 91 + index % 8,
      critical_findings: variant === 0 ? 1 : 0, high_findings: variant <= 1 ? 1 : 0,
      updated_at: `2026-10-${String(18 - index).padStart(2, '0')}T10:30:00Z`,
    };
  });
  const average = (values: number[]) => values.reduce((sum, n) => sum + n, 0) / values.length;
  const count = (field: keyof PRDashboardItem, value: unknown, list = prs) => list.filter(pr => pr[field] === value).length;
  const distribution = (field: keyof PRDashboardItem) => prs.reduce<Record<string, number>>((result, pr) => {
    const key = String(pr[field]); result[key] = (result[key] || 0) + 1; return result;
  }, {});
  const trend = (field: 'quality_score' | 'risk_score' | 'changed_line_coverage') => [...prs].reverse().map(pr => ({ date: pr.updated_at.slice(0, 10), value: pr[field] }));
  const repos: RepositoryDashboardItem[] = names.map((name, index) => {
    const related = prs.filter(pr => pr.repository === name);
    return {
      repository_id: ids[index], name, provider: 'github', active: true,
      open_pr_count: count('state', 'OPEN', related), analysis_count: related.length,
      average_quality: average(related.map(pr => pr.quality_score!)), average_risk: average(related.map(pr => pr.risk_score!)),
      policy_pass_count: count('policy_decision', 'PASS', related), policy_warning_count: count('policy_decision', 'WARNING', related),
      policy_block_count: count('policy_decision', 'BLOCK', related), block_rate: count('policy_decision', 'BLOCK', related) / related.length * 100,
      test_pass_rate: count('test_outcome', 'PASSED', related) / related.length * 100,
      average_changed_coverage: average(related.map(pr => pr.changed_line_coverage!)),
      critical_findings: related.reduce((sum, pr) => sum + pr.critical_findings, 0),
      access_status: 'ACTIVE', last_analysis_at: related[0].updated_at, last_synced_at: '2026-10-18T09:00:00Z',
    };
  });
  const pass = count('policy_decision', 'PASS');
  const warning = count('policy_decision', 'WARNING');
  const block = count('policy_decision', 'BLOCK');
  const failed = count('test_outcome', 'FAILED');
  const overview = {
    repositories_total: repos.length, pull_requests_total: prs.length, open_pull_requests: count('state', 'OPEN'),
    analyses_total: prs.length, analyses_completed: prs.length, analyses_failed: 0,
    average_quality_score: average(prs.map(pr => pr.quality_score!)), average_risk_score: average(prs.map(pr => pr.risk_score!)),
    policy_pass_count: pass, policy_warning_count: warning, policy_block_count: block,
    policy_pass_rate: pass / prs.length * 100, policy_warning_rate: warning / prs.length * 100, policy_block_rate: block / prs.length * 100,
    tests_passed_runs: prs.length - failed, tests_failed_runs: failed, test_pass_rate: (prs.length - failed) / prs.length * 100,
    average_line_coverage: 89.2, average_changed_line_coverage: average(prs.map(pr => pr.changed_line_coverage!)),
    critical_findings: prs.reduce((sum, pr) => sum + pr.critical_findings, 0),
    high_findings: prs.reduce((sum, pr) => sum + pr.high_findings, 0), high_security_findings: 0,
    reviewer_recommendations_generated: prs.length * 2,
    quality_trend: trend('quality_score'), risk_trend: trend('risk_score'), changed_coverage_trend: trend('changed_line_coverage'),
    policy_trend: [...prs].reverse().map(pr => ({ date: pr.updated_at.slice(0, 10), pass_count: Number(pr.policy_decision === 'PASS'), warning_count: Number(pr.policy_decision === 'WARNING'), block_count: Number(pr.policy_decision === 'BLOCK') })),
    quality_grade_distribution: distribution('quality_grade'), risk_level_distribution: distribution('risk_level'), policy_decision_distribution: distribution('policy_decision'),
  };

  function prDetail(pr: PRDashboardItem): PullRequestDashboardDetail {
    const blocked = pr.policy_decision === 'BLOCK';
    const warning = pr.policy_decision === 'WARNING';
    return {
      pr: { id: pr.pull_request_id, number: pr.number, title: pr.title, author: pr.author, state: pr.state, repository: pr.repository, head_branch: `feature/sample-${pr.number}`, head_sha: 'd3e0f54a18b92ec7' },
      analysis: { analysis_id: pr.latest_analysis_id, status: 'COMPLETED', created_at: pr.updated_at, completed_at: pr.updated_at, data_source: 'SAMPLE' },
      quality: { overall_score: pr.quality_score, grade: pr.quality_grade, is_complete: true, components: [
        { category: 'Correctness', score: (pr.quality_score! - 88 * 0.3 - pr.changed_line_coverage! * 0.3) / 0.4, weight: 0.4 }, { category: 'Maintainability', score: 88, weight: 0.3 }, { category: 'Test coverage', score: pr.changed_line_coverage, weight: 0.3 },
      ] },
      risk: { overall_risk: pr.risk_score, risk_level: pr.risk_level, is_complete: true, components: [
        { category: 'Security', score: (pr.risk_score! * 0.7 - (100 - pr.changed_line_coverage!) * 0.2) / 0.5, weight: 0.5 }, { category: 'Change impact', score: pr.risk_score, weight: 0.3 }, { category: 'Test gaps', score: 100 - pr.changed_line_coverage!, weight: 0.2 },
      ] },
      policy: { decision: pr.policy_decision, policy_revision: 3, engine_version: 'sample-v1', passed_rules: blocked ? 3 : 5, warning_rules: warning ? 1 : 0, blocked_rules: blocked ? 2 : 0,
        reasons: blocked ? ['Critical security finding requires review.', 'Changed-code coverage is below the sample 80% threshold.'] : warning ? ['Changed-code coverage is below the sample 80% threshold.'] : ['All sample quality, risk and coverage thresholds passed.'] },
      tests: { total: 48, passed: blocked ? 46 : 48, failed: blocked ? 2 : 0, errors: 0, skipped: 0, test_outcome: pr.test_outcome },
      coverage: { line_coverage: 89.2, changed_line_coverage: pr.changed_line_coverage },
      findings: blocked || warning ? [
        { id: pr.pull_request_id * 10, source: 'Sample review', severity: blocked ? 'CRITICAL' : 'HIGH', category: blocked ? 'security' : 'performance',
          title: blocked ? 'Validate the signature before processing the payload' : 'Bound the cache lifetime for product queries',
          description: blocked ? 'This illustrative webhook handler accepts a payload before checking its signature. An untrusted request could create an order.' : 'A cache entry without a lifetime can serve stale inventory after a stock update.',
          recommendation: blocked ? 'Verify an HMAC signature with a constant-time comparison, then parse the trusted payload. Add negative signature tests.' : 'Use a short TTL and invalidate entries when product inventory changes. Add an expiry regression test.',
          file_path: blocked ? 'app/webhooks/payments.py' : 'app/catalog/cache.py', line_number: 42, end_line: 48 },
        ...(blocked ? [{ id: pr.pull_request_id * 10 + 1, source: 'Sample coverage', severity: 'HIGH', category: 'testing', title: 'Add coverage for the failure path', description: 'The sample changed lines include an error branch without a regression test.', recommendation: 'Test malformed input and assert the expected failure response.', file_path: 'tests/test_payments.py', line_number: 27 }] : []),
      ] : [],
      reviewer_recommendation: [
        { reviewer_username: 'maya-chen', match_score: 96, reasons: ['Payment security expertise', 'CODEOWNERS match (sample)'] },
        { reviewer_username: 'sam-patel', match_score: 88, reasons: ['Recent test contributions (sample)'] },
      ],
    };
  }
  return { repos, prs, overview, prDetail };
}

export const defaultTesting = {
  enabled: true, coverage_enabled: true, network_enabled: false, executor_type: 'DOCKER',
  docker_image: 'python:3.12-slim', install_command: 'pip install -r requirements.txt', test_command: 'pytest --cov=app',
};

export function sampleMembers(workspaceId: number) {
  return [
    { user_id: 10, github_login: 'demo-viewer', display_name: 'Demo Viewer', avatar_url: null, role: 'ADMIN', joined_at: '2026-09-01T09:00:00Z' },
    { user_id: workspaceId === 1 ? 12 : 22, github_login: workspaceId === 1 ? 'maya-chen' : 'alex-rivera', display_name: workspaceId === 1 ? 'Maya Chen' : 'Alex Rivera', avatar_url: null, role: 'REVIEWER', joined_at: '2026-09-12T09:00:00Z' },
    { user_id: workspaceId === 1 ? 13 : 23, github_login: 'sam-patel', display_name: 'Sam Patel', avatar_url: null, role: 'DEVELOPER', joined_at: '2026-10-02T09:00:00Z' },
  ];
}
