import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { CodeGateAPI } from '../api/client';
import type { PullRequestDashboardDetail } from '../types';
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  CheckCircle,
  FileCheck,
  Users,
  RefreshCw,
  GraduationCap,
  Sparkles,
  CheckCircle2,
  Code2,
  FileCode,
  ArrowLeft,
  List,
  LayoutGrid,
} from 'lucide-react';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { Badge } from '../components/ui/Badge';
import { formatPercentage, formatScore, formatDate } from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import { activeDemo, DEMO_MODE } from '../demo/transport';

export function PullRequestDetail() {
  const { workspaceVersion, activeWorkspace } = useAuth();
  const { pullRequestId } = useParams<{ pullRequestId: string }>();
  const [data, setData] = useState<PullRequestDashboardDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [understoodFindings, setUnderstoodFindings] = useState<Record<number, boolean>>({});
  const requestGeneration = useRef(0);

  const load = useCallback(() => {
    if (!pullRequestId) return;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError(null);
    CodeGateAPI.getPullRequestDetail(parseInt(pullRequestId, 10))
      .then(detail => { if (generation === requestGeneration.current) setData(detail); })
      .catch(err => { if (generation === requestGeneration.current) setError(err.message); })
      .finally(() => { if (generation === requestGeneration.current) setLoading(false); });
  }, [pullRequestId]);

  useEffect(() => {
    load();
    return () => { requestGeneration.current += 1; };
  }, [load, workspaceVersion]);

  const toggleUnderstood = (idx: number) => {
    const key = `${activeWorkspace?.id}:${pullRequestId}:${idx}`;
    const current = DEMO_MODE ? activeDemo?.getUnderstood(key) : understoodFindings[idx];
    if (DEMO_MODE) activeDemo?.setUnderstood(key, !current);
    setUnderstoodFindings(prev => ({ ...prev, [idx]: !current }));
  };

  if (loading) {
    return (
      <div className="page-stack animate-pulse">
        <Skeleton className="w-full h-20 rounded-2xl" />
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => <Skeleton key={i} className="w-full h-32 rounded-2xl" />)}
        </div>
        <Skeleton className="w-full h-64 rounded-2xl" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8">
        <ErrorState 
          title="Unable to load pull request" 
          description={error || 'Pull request not found'} 
          onRetry={load} 
        />
      </div>
    );
  }

  const { pr, analysis, quality, risk, policy, tests, coverage, findings, reviewer_recommendation: reviewers } = data;
  const policyDecision = policy?.decision?.toUpperCase() || 'UNKNOWN';
  const decisionVariant = policyDecision === 'BLOCK' ? 'block' : policyDecision === 'WARNING' ? 'warning' : policyDecision === 'PASS' ? 'pass' : 'unknown';

  const handleRetry = async () => {
    if (!analysis?.analysis_id) return;
    setRetrying(true);
    try {
      await CodeGateAPI.retryAnalysis(analysis.analysis_id);
      load();
    } catch (err: any) {
      alert(err.message || 'Failed to retry analysis');
    } finally {
      setRetrying(false);
    }
  };

  const isTerminal = analysis?.status === 'FAILED' || analysis?.status === 'SKIPPED' || analysis?.status === 'COMPLETED';

  // Educational lesson mapper based on finding category
  const getConceptDetails = (category: string, _severity?: string) => {
    const cat = (category || '').toLowerCase();
    if (cat.includes('security') || cat.includes('auth')) {
      return {
        concept: 'Security & Defensive Coding',
        lesson: 'Security issues expose software to unauthorized access or data leaks. In professional software engineering, always validate inputs, never expose sensitive tokens, and follow the principle of least privilege.',
      };
    }
    if (cat.includes('perf') || cat.includes('speed')) {
      return {
        concept: 'Performance & Optimization',
        lesson: 'Inefficient loops, unindexed queries, or unnecessary re-renders degrade user experience. Write algorithmic code that scales well under heavy data loads.',
      };
    }
    if (cat.includes('test') || cat.includes('coverage')) {
      return {
        concept: 'Test Verification & Quality',
        lesson: 'Code without automated tests is prone to silent regressions. High test coverage ensures your new features do not break existing business logic.',
      };
    }
    if (cat.includes('style') || cat.includes('convention') || cat.includes('lint')) {
      return {
        concept: 'Code Readability & Clean Architecture',
        lesson: 'Code is read 10x more often than it is written. Following clean naming conventions and modular functions makes it easier for teammates to review and maintain.',
      };
    }
    return {
      concept: 'Bug Prevention & Reliability',
      lesson: 'Edge cases such as null/undefined values, unexpected type conversions, or unhandled promise rejections can cause unexpected crashes in runtime.',
    };
  };

  return (
    <div className="page-stack">
      {/* Back Link Breadcrumb */}
      <div className="flex items-center gap-2 text-xs font-semibold text-[var(--cg-muted)]">
        <Link to="/pull-requests" className="hover:text-indigo-500 flex items-center gap-1">
          <ArrowLeft size={14} /> Pull Requests
        </Link>
        <span>/</span>
        <span className="text-[var(--cg-text)] font-bold">{pr.repository}</span>
        <span>/</span>
        <span>#{pr.number}</span>
      </div>

      {/* Hero Header */}
      <div className="page-hero">
        <div className="page-hero__content">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-[var(--cg-surface-soft)] text-[var(--cg-text)] border border-[var(--cg-border-soft)]">
              PR #{pr.number}
            </span>
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
              {pr.repository}
            </span>
            {analysis && (
              <Badge variant={
                analysis.status === 'COMPLETED' ? 'success' :
                analysis.status === 'FAILED' ? 'danger' :
                analysis.status === 'RUNNING' ? 'info' :
                analysis.status === 'QUEUED' ? 'info' : 'default'
              }>
                {analysis.status}
              </Badge>
            )}
          </div>

          <h1 className="page-hero__title">#{pr.number} — {pr.title}</h1>

          <p className="page-hero__desc">
            <span>By <strong>@{pr.author}</strong></span>
            <span>·</span>
            <span>State: <strong className="capitalize">{pr.state}</strong></span>
            {pr.head_branch && (
              <>
                <span>·</span>
                <span className="inline-flex items-center gap-1 font-mono text-xs bg-[var(--cg-surface-soft)] text-[var(--cg-text-secondary)] border border-[var(--cg-border-soft)] px-2 py-0.5 rounded">
                  <Code2 size={12} /> {pr.head_branch} {pr.head_sha ? `(${pr.head_sha.substring(0, 7)})` : ''}
                </span>
              </>
            )}
          </p>
        </div>

        <div className="page-hero__actions">
          {analysis && isTerminal && (
            <button className="btn-secondary" onClick={handleRetry} disabled={DEMO_MODE || retrying} title={DEMO_MODE ? 'Analysis execution requires a configured live backend.' : undefined}>
              <RefreshCw size={15} strokeWidth={2} className={retrying ? "spin" : ""} /> 
              {retrying ? 'Retrying...' : 'Retry Analysis'}
            </button>
          )}
        </div>
      </div>

      {DEMO_MODE && <p className="alert">Illustrative analysis evidence. Retry Analysis requires a configured live backend. Coaching progress is saved in this browser.</p>}

      {/* Meta Timestamps */}
      <div className="pr-meta-bar">
        <span>Analysis ID: <strong className="text-[var(--cg-text)]">{analysis?.analysis_id ? '#' + analysis.analysis_id : 'Not run'}</strong></span>
        <span>•</span>
        {analysis?.created_at && <span>Started: {formatDate(analysis.created_at)}</span>}
        {analysis?.completed_at && (
          <>
            <span>•</span>
            <span>Completed: {formatDate(analysis.completed_at)}</span>
          </>
        )}
      </div>

      {/* Incomplete Evidence Alert */}
      {(quality?.is_complete === false || risk?.is_complete === false) && (
        <div className="alert alert--error">
          <ShieldAlert size={20} />
          <div>
            <strong>Incomplete evidence recorded</strong>
            {quality?.is_complete === false && (
              <p className="mt-1">Quality: missing {Array.isArray(quality.missing_dimensions) ? quality.missing_dimensions.join(', ') : 'dimensions not specified'}</p>
            )}
            {risk?.is_complete === false && (
              <p className="mt-1">Risk: missing {Array.isArray(risk.missing_dimensions) ? risk.missing_dimensions.join(', ') : 'dimensions not specified'}</p>
            )}
          </div>
        </div>
      )}

      {/* 5 KPI STATUS CARDS */}
      <div className="dashboard-grid dashboard-grid--5">
        {/* Quality Card */}
        <div className="stat-card stat-card--green">
          <div className="stat-card__icon"><ShieldCheck size={26} strokeWidth={1.8} /></div>
          <div className="stat-card__body">
            <div className="stat-card__label">Quality</div>
            <div className="stat-card__value">{formatScore(quality?.overall_score)}</div>
            <div className="stat-card__note">
              {quality?.grade ? (
                <Badge variant={quality.grade === 'A' || quality.grade === 'B' ? 'success' : quality.grade === 'C' ? 'warning' : 'danger'}>
                  Grade {quality.grade}
                </Badge>
              ) : 'N/A'}
            </div>
          </div>
        </div>

        {/* Risk Card */}
        <div className="stat-card stat-card--amber">
          <div className="stat-card__icon"><ShieldAlert size={26} strokeWidth={1.8} /></div>
          <div className="stat-card__body">
            <div className="stat-card__label">Risk</div>
            <div className="stat-card__value">{formatScore(risk?.overall_risk)}</div>
            <div className="stat-card__note">
              {risk?.risk_level ? (
                <Badge variant={risk.risk_level === 'LOW' ? 'success' : risk.risk_level === 'MEDIUM' ? 'warning' : 'danger'}>
                  {risk.risk_level} Risk
                </Badge>
              ) : 'N/A'}
            </div>
          </div>
        </div>

        {/* Policy Decision Card */}
        <div className={`stat-card stat-card--${decisionVariant === 'block' ? 'red' : decisionVariant === 'warning' ? 'amber' : 'indigo'}`}>
          <div className="stat-card__icon">
            {policyDecision === 'BLOCK' ? <ShieldX size={26} strokeWidth={1.8} /> :
             policyDecision === 'WARNING' ? <ShieldAlert size={26} strokeWidth={1.8} /> :
             <ShieldCheck size={26} strokeWidth={1.8} />}
          </div>
          <div className="stat-card__body">
            <div className="stat-card__label">Policy</div>
            <div className="stat-card__value" style={{ fontSize: '24px' }}>{policyDecision}</div>
            <div className="stat-card__note">
              {policyDecision === 'PASS' ? 'Ready to merge' : policyDecision === 'WARNING' ? 'Review warnings' : 'Merge blocked'}
            </div>
          </div>
        </div>

        {/* Tests Card */}
        <div className="stat-card stat-card--blue">
          <div className="stat-card__icon"><CheckCircle size={26} strokeWidth={1.8} /></div>
          <div className="stat-card__body">
            <div className="stat-card__label">Tests</div>
            <div className="stat-card__value" style={{ fontSize: '24px' }}>
              {tests ? `${tests.passed ?? 'N/A'}/${tests.total ?? 'N/A'}` : '—'}
            </div>
            <div className="stat-card__note">
              {tests ? (tests.total === 0 ? 'No tests recorded' : tests.test_outcome || 'Outcome unavailable') : 'Not run / unavailable'}
            </div>
          </div>
        </div>

        {/* Changed Coverage Card */}
        <div className="stat-card stat-card--indigo">
          <div className="stat-card__icon"><FileCheck size={26} strokeWidth={1.8} /></div>
          <div className="stat-card__body">
            <div className="stat-card__label">Changed Coverage</div>
            <div className="stat-card__value" style={{ fontSize: '24px' }}>
              {formatPercentage(coverage?.changed_line_coverage)}
            </div>
            <div className="stat-card__note">New code coverage</div>
          </div>
        </div>
      </div>

      {/* POLICY EVIDENCE */}
      {policy && (
        <div className={`decision-panel decision-panel--${decisionVariant}`}>
          <div className="decision-panel__title">
            {policyDecision === 'BLOCK' ? <ShieldX size={20} /> :
             policyDecision === 'WARNING' ? <ShieldAlert size={20} /> :
             <ShieldCheck size={20} />}
            Policy evidence
          </div>
          <p className="muted mb-3">Revision {policy.policy_revision ?? 'N/A'} · Engine {policy.engine_version ?? 'N/A'}</p>
          <div className="flex flex-wrap gap-2 mb-3 font-semibold text-xs">
            <span className="policy-badge policy-badge--pass">{policy.passed_rules ?? 0} passed rules</span>
            <span className="policy-badge policy-badge--warning">{policy.warning_rules ?? 0} warnings</span>
            <span className="policy-badge policy-badge--block">{policy.blocked_rules ?? 0} blocked rules</span>
          </div>
          <ul className="decision-panel__reasons">
            {policy.reasons?.map((reason: string, idx: number) => (
              <li key={idx} className="decision-panel__reason">
                <span className="decision-panel__dot" />
                {reason}
              </li>
            ))}
            {(!policy.reasons || policy.reasons.length === 0) && (
              <li className="decision-panel__reason">
                <span className="decision-panel__dot" />
                No specific reasons provided.
              </li>
            )}
          </ul>
        </div>
      )}

      {/* INTERACTIVE LESSONS & FINDINGS HUB (Mascot Coaching Experience) */}
      <div className="dashboard-panel">
        <div className="dashboard-panel__head flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-xl">
              🎓
            </div>
            <div>
              <div className="dashboard-panel__title flex items-center gap-2">
                Anteater Code Lessons & Findings
                {findings && findings.length > 0 && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-400">
                    {findings.length} Lessons
                  </span>
                )}
              </div>
              <div className="dashboard-panel__meta">
                Interactive learning & coaching feedback derived from automated security, quality, and AI reviews
              </div>
            </div>
          </div>

          <div className="chart-view-toggle">
            <button
              onClick={() => setViewMode('cards')}
              className={`chart-view-btn ${viewMode === 'cards' ? 'chart-view-btn--active' : ''}`}
            >
              <LayoutGrid size={14} /> Lesson Cards
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`chart-view-btn ${viewMode === 'table' ? 'chart-view-btn--active' : ''}`}
            >
              <List size={14} /> Summary Table
            </button>
          </div>
        </div>

        <div className="dashboard-panel__body">
          {findings && findings.length > 0 ? (
            viewMode === 'cards' ? (
              <div className="grid grid-cols-1 gap-4">
                {findings.map((f: any, idx: number) => {
                  const details = getConceptDetails(f.category, f.severity);
                  const isUnderstood = DEMO_MODE ? !!activeDemo?.getUnderstood(`${activeWorkspace?.id}:${pullRequestId}:${idx}`) : !!understoodFindings[idx];

                  return (
                    <div
                      key={idx}
                      className={`lesson-card ${isUnderstood ? 'border-emerald-500/40 bg-emerald-500/5' : ''}`}
                    >
                      <div className="lesson-card__head">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="lesson-card__concept">
                            <GraduationCap size={14} />
                            Lesson #{idx + 1}: {details.concept}
                          </span>
                          <Badge
                            variant={
                              f.severity === 'CRITICAL' || f.severity === 'HIGH'
                                ? 'danger'
                                : f.severity === 'MEDIUM'
                                ? 'warning'
                                : 'default'
                            }
                          >
                            {f.severity}
                          </Badge>
                          {f.rule_id && (
                            <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-[var(--cg-surface-soft)] text-[var(--cg-text-secondary)] border border-[var(--cg-border-soft)]">
                              {f.rule_id}
                            </span>
                          )}
                          <span className="text-xs text-[var(--cg-muted)] font-medium">Category: {f.category}</span>
                          {f.source && (
                            <span className="text-[11px] text-[var(--cg-muted)] uppercase tracking-wider font-semibold">
                              · {f.source}
                            </span>
                          )}
                        </div>

                        <button
                          onClick={() => toggleUnderstood(idx)}
                          className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all ${
                            isUnderstood
                              ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                              : 'bg-[var(--cg-surface-soft)] hover:bg-[var(--cg-border)] text-[var(--cg-text)] border border-[var(--cg-border)]'
                          }`}
                        >
                          <CheckCircle2 size={14} className={isUnderstood ? 'text-emerald-500' : 'text-[var(--cg-muted)]'} />
                          {isUnderstood ? 'Learned & Understood' : 'Mark as Understood'}
                        </button>
                      </div>

                      <h3 className="lesson-card__title">{f.title}</h3>

                      {/* Real Finding Description */}
                      {f.description ? (
                        <div className="lesson-card__explanation">
                          <strong>Issue Details:</strong> {f.description}
                        </div>
                      ) : null}

                      {/* Pedagogical Anteater Lesson */}
                      <div className="lesson-card__coaching">
                        <GraduationCap size={16} className="text-indigo-500 shrink-0 mt-0.5" />
                        <div>
                          <strong>Anteater Coach Lesson:</strong> {details.lesson}
                        </div>
                      </div>

                      {/* Code File & Location Pill */}
                      {f.file_path && (
                        <div className="lesson-card__file">
                          <FileCode size={14} className="text-indigo-500 shrink-0" />
                          <span className="font-semibold text-[var(--cg-text)]">{f.file_path}</span>
                          {f.line_number && (
                            <span className="text-indigo-500 font-bold">
                              :Line {f.line_number}{f.end_line && f.end_line !== f.line_number ? `-${f.end_line}` : ''}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Real Engine Recommendation / Suggested Fix */}
                      {f.recommendation ? (
                        <div className="lesson-card__recommendation">
                          <div className="lesson-card__rec-title">
                            <Sparkles size={13} className="text-indigo-400" /> Recommended Actionable Fix:
                          </div>
                          <div className="lesson-card__rec-body">
                            {f.recommendation}
                          </div>
                        </div>
                      ) : (
                        <div className="lesson-card__tip">
                          <Sparkles size={13} className="text-amber-500 shrink-0" />
                          <span>Review the flagged logic in <code>{f.file_path || 'the source code'}</code> against the {details.concept.toLowerCase()} checklist.</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="table-wrapper" style={{ boxShadow: 'none' }}>
                <table className="cg-table">
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Title</th>
                      <th>Category</th>
                      <th>File</th>
                      <th>Line</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f: any, idx: number) => (
                      <tr key={idx}>
                        <td>
                          <Badge variant={f.severity === 'CRITICAL' || f.severity === 'HIGH' ? 'danger' : f.severity === 'MEDIUM' ? 'warning' : 'default'}>
                            {f.severity}
                          </Badge>
                        </td>
                        <td className="cell-primary font-medium">{f.title}</td>
                        <td className="text-[var(--cg-text-secondary)]">{f.category}</td>
                        <td className="cell-muted font-mono text-xs">{f.file_path || 'general-repository'}</td>
                        <td className="cell-muted">{f.line_number ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : (
            <div className="text-center py-10 px-4">
              <img
                src="/mascot/mascot-celebrate.jpg"
                alt="Flawless Quality"
                className="w-28 h-28 mx-auto rounded-2xl shadow-md object-cover mb-4"
              />
              <h3 className="font-bold text-lg text-[var(--cg-text)]">
                {!analysis ? 'Analysis not run.' : analysis.status !== 'COMPLETED' ? 'Findings unavailable until analysis completes.' : '100% Clean! Zero Findings Recorded.'}
              </h3>
              <p className="text-sm text-[var(--cg-muted)] max-w-md mx-auto mt-1">
                {!analysis ? 'Trigger an analysis to examine this PR.' : analysis.status !== 'COMPLETED' ? 'Analysis is currently processing.' : 'Great job! This pull request meets all quality and security standards without any detected issues.'}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* QUALITY & RISK BREAKDOWN */}
      <div className="dashboard-grid dashboard-grid--bottom">
        <div className="dashboard-panel">
          <div className="dashboard-panel__head">
            <div className="dashboard-panel__title">Quality Breakdown</div>
          </div>
          <div className="dashboard-panel__body">
            {quality?.components?.map((comp: any) => (
              <div key={comp.category} className="breakdown-row">
                <div className="breakdown-row__label">{comp.category}</div>
                <div className="breakdown-row__score" style={{
                  color: comp.score == null ? 'var(--cg-muted)' : comp.score >= 80 ? 'var(--cg-green)' : comp.score >= 60 ? 'var(--cg-amber)' : 'var(--cg-red)'
                }}>{comp.score == null ? '—' : formatScore(comp.score)}</div>
                <div className="breakdown-row__bar">
                  <div className="progress-bar">
                    <div
                      className={`progress-bar__fill ${comp.score >= 80 ? 'progress-bar__fill--green' : comp.score >= 60 ? 'progress-bar__fill--amber' : 'progress-bar__fill--red'}`}
                      style={{ width: comp.score == null ? '0%' : `${Math.min(comp.score, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="breakdown-row__weight">{comp.weight ? `×${comp.weight.toFixed(1)}` : '—'}</div>
              </div>
            ))}
            {(!quality?.components || quality.components.length === 0) && (
              <div style={{ textAlign: 'center', color: 'var(--cg-muted)', padding: '24px', fontSize: '13px' }}>
                No quality breakdown available.
              </div>
            )}
          </div>
        </div>

        <div className="dashboard-panel">
          <div className="dashboard-panel__head">
            <div className="dashboard-panel__title">Risk Breakdown</div>
          </div>
          <div className="dashboard-panel__body">
            {risk?.components?.map((comp: any) => (
              <div key={comp.category} className="breakdown-row">
                <div className="breakdown-row__label">{comp.category}</div>
                <div className="breakdown-row__score" style={{
                  color: comp.score == null ? 'var(--cg-muted)' : comp.score >= 75 ? 'var(--cg-red)' : comp.score >= 50 ? 'var(--cg-amber)' : 'var(--cg-green)'
                }}>{comp.score == null ? '—' : formatScore(comp.score)}</div>
                <div className="breakdown-row__bar">
                  <div className="progress-bar">
                    <div
                      className={`progress-bar__fill ${comp.score >= 75 ? 'progress-bar__fill--red' : comp.score >= 50 ? 'progress-bar__fill--amber' : 'progress-bar__fill--green'}`}
                      style={{ width: comp.score == null ? '0%' : `${Math.min(comp.score, 100)}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
            {(!risk?.components || risk.components.length === 0) && (
              <div style={{ textAlign: 'center', color: 'var(--cg-muted)', padding: '24px', fontSize: '13px' }}>
                No risk components analyzed.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* TEST & COVERAGE */}
      <div className="dashboard-grid dashboard-grid--bottom">
        <div className="dashboard-panel">
          <div className="dashboard-panel__head">
            <div className="dashboard-panel__title">Test Results</div>
          </div>
          <div className="dashboard-panel__body">
            {tests ? (
              <div className="evidence-grid">
                <div className="metric-block"><div className="metric-block__label">Total</div><div className="metric-block__value">{tests.total ?? 'N/A'}</div></div>
                <div className="metric-block metric-block--green"><div className="metric-block__label">Passed</div><div className="metric-block__value text-emerald-600">{tests.passed ?? 'N/A'}</div></div>
                <div className="metric-block metric-block--red"><div className="metric-block__label">Failed</div><div className="metric-block__value text-rose-600">{tests.failed ?? 'N/A'}</div></div>
                <div className="metric-block"><div className="metric-block__label">Errors</div><div className="metric-block__value">{tests.errors ?? 'N/A'}</div></div>
                <div className="metric-block"><div className="metric-block__label">Skipped</div><div className="metric-block__value">{tests.skipped ?? 'N/A'}</div></div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--cg-muted)', padding: '24px', fontSize: '13px' }}>
                No test data available.
              </div>
            )}
          </div>
        </div>

        <div className="dashboard-panel">
          <div className="dashboard-panel__head">
            <div className="dashboard-panel__title">Coverage</div>
          </div>
          <div className="dashboard-panel__body">
            {coverage ? (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-slate-500">Overall Line Coverage</div>
                    <div className="text-2xl font-bold text-slate-800 font-mono mt-1">
                      {formatPercentage(coverage.line_coverage)}
                    </div>
                  </div>
                  <div className="w-24">
                    <div className="progress-bar">
                      <div
                        className="progress-bar__fill progress-bar__fill--green"
                        style={{ width: `${Math.min(coverage.line_coverage ?? 0, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-indigo-50/50 border border-indigo-100 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-indigo-700">Changed-Code Coverage</div>
                    <div className="text-2xl font-bold text-indigo-900 font-mono mt-1">
                      {formatPercentage(coverage.changed_line_coverage)}
                    </div>
                  </div>
                  <div className="w-24">
                    <div className="progress-bar">
                      <div
                        className="progress-bar__fill"
                        style={{ width: `${Math.min(coverage.changed_line_coverage ?? 0, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--cg-muted)', padding: '24px', fontSize: '13px' }}>
                No coverage data available.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* REVIEWER RECOMMENDATIONS */}
      <div className="dashboard-panel">
        <div className="dashboard-panel__head">
          <div className="dashboard-panel__title flex items-center gap-2">
            <Users size={18} strokeWidth={2} className="text-indigo-600" />
            Suggested Reviewers
          </div>
        </div>
        <div className="dashboard-panel__body">
          {reviewers && (Array.isArray(reviewers) ? reviewers : [reviewers]).length > 0 ? (
            (Array.isArray(reviewers) ? reviewers : [reviewers]).map((r: any, idx: number) => (
              <div key={idx} className="reviewer-card">
                <div className="reviewer-card__avatar">
                  {r.reviewer_username?.charAt(0)?.toUpperCase() || '?'}
                </div>
                <div className="reviewer-card__info">
                  <div className="reviewer-card__name">@{r.reviewer_username}</div>
                  <div className="reviewer-card__reasons">
                    {r.reasons?.join(' · ') || 'Recommended by expertise'}
                  </div>
                </div>
                <div className="reviewer-card__score">
                  {formatScore(r.match_score)} match
                </div>
              </div>
            ))
          ) : (
            <div style={{ textAlign: 'center', padding: '32px', color: 'var(--cg-muted)', fontSize: '13px' }}>
              No reviewer recommendations available.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
