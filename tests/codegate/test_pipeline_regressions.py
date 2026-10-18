"""Regressions for the local analysis pipeline and synchronous Celery entry point."""

import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from codegate.database.models.analysis import (
    AnalysisJob,
    AnalysisRun,
    AnalyzerRun,
    CodeMetric,
    Finding,
    Status,
    Trigger,
)
from codegate.database.models.pull_request import PullRequest, PullRequestFile
from codegate.database.models.repository import Repository
from codegate.engines.analyzers.workspace import AnalyzerWorkspace
from codegate.services.analysis_orchestrator import AnalysisOrchestrator


def seed_pull_request(db_session, url="https://github.com/test/repo", head_sha="abc123"):
    repo = Repository(provider="GITHUB", owner="test", name="repo", full_name="test/repo", url=url)
    db_session.add(repo)
    db_session.flush()
    pr = PullRequest(
        repository_id=repo.id, number=1, title="Regression", state="OPEN", head_sha=head_sha,
        author_username="tester", source_branch="feature", target_branch="main", base_sha=head_sha,
    )
    db_session.add(pr)
    db_session.flush()
    db_session.add(PullRequestFile(pull_request_id=pr.id, filename="bad_code.py", status="added"))
    db_session.commit()
    return pr


@pytest.mark.asyncio
async def test_orchestrator_runs_real_static_analyzers_before_scoring(db_session, tmp_path, monkeypatch):
    """Use real git and analyzer processes; replace only provider/AI boundaries."""
    for module in ("ruff", "bandit", "radon"):
        pytest.importorskip(module)
    repo_path = tmp_path / "source"
    repo_path.mkdir()
    (repo_path / "bad_code.py").write_text(
        "import os\nimport subprocess\n\ndef run(value):\n"
        "    subprocess.run('echo ' + value, shell=True)\n",
        encoding="utf-8",
    )
    for args in (
        ["init"], ["add", "."],
        ["-c", "user.name=Regression", "-c", "user.email=regression@example.test", "commit", "-m", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=repo_path, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path, text=True).strip()
    pr = seed_pull_request(db_session, str(repo_path), sha)
    provider = SimpleNamespace(repo_path=str(repo_path), pr=SimpleNamespace(base=SimpleNamespace(sha=sha)))
    adapter = MagicMock()
    adapter.run = AsyncMock(return_value={"review": {"key_issues_to_review": []}})
    monkeypatch.setattr("codegate.services.analysis_orchestrator.CodeGateAdapter", lambda _: adapter)
    monkeypatch.setattr("codegate.services.analysis_orchestrator.get_git_provider", lambda: lambda _: provider)
    monkeypatch.setattr("codegate.services.test_service.TestExecutionService.execute_tests", AsyncMock())
    monkeypatch.setattr("codegate.services.reviewer_service.reviewer_service.evaluate_and_persist", MagicMock())
    monkeypatch.setattr("codegate.services.analysis_orchestrator.GitHubPolicyCheckPublisher", MagicMock())
    monkeypatch.setattr("codegate.services.analysis_orchestrator.quality_policy_service.evaluate_and_publish", MagicMock())

    run, created = await AnalysisOrchestrator(db_session).trigger_analysis(pr, "https://github.com/test/repo/pull/1")

    assert created
    assert run.status == Status.COMPLETED
    analyzer_runs = db_session.query(AnalyzerRun).filter_by(analysis_run_id=run.id).all()
    assert {item.analyzer for item in analyzer_runs} == {"RUFF", "BANDIT", "RADON"}
    assert all(item.status == Status.SUCCESS for item in analyzer_runs)
    findings = db_session.query(Finding).filter_by(analysis_run_id=run.id).all()
    assert {item.source for item in findings} >= {"RUFF", "BANDIT"}
    assert all(item.file_path == "bad_code.py" and item.is_changed_file for item in findings)
    assert db_session.query(CodeMetric).filter_by(analysis_run_id=run.id).count() > 0
    assert run.quality_scores[0].code_quality_score < 100
    assert run.quality_scores[0].security_score < 100
    assert run.risk_scores

    reused, was_created = await AnalysisOrchestrator(db_session).trigger_analysis(pr, "https://github.com/test/repo/pull/1")
    assert reused.id == run.id
    assert not was_created
    assert db_session.query(AnalyzerRun).filter_by(analysis_run_id=run.id).count() == 3


@pytest.mark.asyncio
async def test_workspace_failure_does_not_publish_a_successful_analysis(db_session, monkeypatch):
    pr = seed_pull_request(db_session)
    adapter = MagicMock()
    adapter.run = AsyncMock(return_value={"review": {"key_issues_to_review": []}})
    monkeypatch.setattr("codegate.services.analysis_orchestrator.CodeGateAdapter", lambda _: adapter)
    monkeypatch.setattr("codegate.services.analysis_orchestrator.get_git_provider", MagicMock)
    monkeypatch.setattr("codegate.services.test_service.TestExecutionService.execute_tests", AsyncMock())
    monkeypatch.setattr("codegate.services.reviewer_service.reviewer_service.evaluate_and_persist", MagicMock())
    monkeypatch.setattr("codegate.services.analysis_orchestrator.GitHubPolicyCheckPublisher", MagicMock())
    monkeypatch.setattr("codegate.services.analysis_orchestrator.quality_policy_service.evaluate_and_publish", MagicMock())
    monkeypatch.setattr(
        "codegate.engines.analyzers.workspace.AnalyzerWorkspace.prepare",
        MagicMock(side_effect=RuntimeError("Fixture workspace cannot be prepared")),
    )

    run, _ = await AnalysisOrchestrator(db_session).trigger_analysis(pr, "https://github.com/test/repo/pull/1")

    assert run.status == Status.FAILED
    assert "workspace cannot be prepared" in run.error_message
    assert not run.quality_scores


def test_celery_task_owns_event_loop_when_none_is_installed(db_session, monkeypatch):
    from codegate.worker.tasks import analyze_pull_request

    pr = seed_pull_request(db_session)
    run = AnalysisRun(pull_request_id=pr.id, head_sha=pr.head_sha, status=Status.QUEUED, trigger=Trigger.MANUAL)
    db_session.add(run)
    db_session.flush()
    job = AnalysisJob(analysis_run_id=run.id, status="QUEUED")
    db_session.add(job)
    db_session.commit()
    loops = []

    async def execute(_self, analysis_run, _url):
        loops.append(asyncio.get_running_loop())
        analysis_run.status = Status.COMPLETED
        db_session.commit()

    monkeypatch.setattr(AnalysisOrchestrator, "_execute_run", execute)
    monkeypatch.setattr("pr_agent.config_loader.get_settings", MagicMock)
    monkeypatch.setattr(analyze_pull_request, "_db", db_session)
    asyncio.set_event_loop(None)

    analyze_pull_request.run(run.id)

    db_session.refresh(job)
    assert job.status == "SUCCEEDED"
    assert job.attempt_count == 1
    assert len(loops) == 1
    assert loops[0].is_closed()

    analyze_pull_request.run(run.id)
    assert len(loops) == 1
    assert job.status == "SKIPPED"


def test_analyzer_workspace_redacts_credentials_on_git_failure(monkeypatch, caplog):
    token = "fixture-token-never-a-real-secret"
    workspace = AnalyzerWorkspace("https://github.com/test/repo.git", "abc123", token)
    git_run = MagicMock(side_effect=subprocess.CalledProcessError(
        128, ["git", "remote", "add", "origin", workspace._get_auth_url()],
        stderr=f"fatal: authentication rejected for {workspace._get_auth_url()}".encode(),
    ))
    monkeypatch.setattr("codegate.engines.analyzers.workspace.subprocess.run", git_run)

    with pytest.raises(RuntimeError, match="Workspace preparation failed") as exc_info:
        workspace.prepare()

    assert token not in caplog.text
    assert "[REDACTED]" in caplog.text
    assert token not in str(exc_info.value)
    assert exc_info.value.__suppress_context__
    assert workspace.workspace_dir is None


def test_analyzer_workspace_bounds_every_git_command(monkeypatch):
    workspace = AnalyzerWorkspace("https://github.com/test/repo.git", "abc123")
    git_run = MagicMock()
    monkeypatch.setattr("codegate.engines.analyzers.workspace.subprocess.run", git_run)
    try:
        workspace.prepare()
        assert git_run.call_count == 4
        assert all(call.kwargs.get("timeout", 0) > 0 for call in git_run.call_args_list)
    finally:
        workspace.cleanup()


def test_analyzer_workspace_cleans_up_after_git_timeout(monkeypatch):
    workspace = AnalyzerWorkspace("https://github.com/test/repo.git", "abc123")
    git_run = MagicMock(side_effect=subprocess.TimeoutExpired(["git", "fetch"], 1))
    monkeypatch.setattr("codegate.engines.analyzers.workspace.subprocess.run", git_run)

    with pytest.raises(RuntimeError, match="timed out"):
        workspace.prepare()

    assert workspace.workspace_dir is None
