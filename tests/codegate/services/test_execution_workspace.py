"""Ensure test execution and changed coverage use the same checked-out revision."""

import subprocess
from unittest.mock import AsyncMock

import pytest

from codegate.database.models import AnalysisRun, PullRequest, Repository
from codegate.database.models.analysis import Status, Trigger
from codegate.database.models.testing import TestConfiguration
from codegate.engines.testing.schemas import CoverageMetrics, ExecutionStatus, JUnitMetrics
from codegate.engines.testing.schemas import TestOutcome as Outcome
from codegate.repositories.analysis_store import AnalysisStore
from codegate.repositories.testing_store import TestingStore
from codegate.services.test_service import TestExecutionService as ExecutionService


@pytest.fixture
def configured_run(db_session):
    repo = Repository(provider="GITHUB", owner="test", name="repo", full_name="test/repo", url="https://example.test")
    db_session.add(repo)
    db_session.flush()
    pr = PullRequest(repository_id=repo.id, number=1, title="test", head_sha="head", state="OPEN",
                     author_username="dev", source_branch="feature", target_branch="main")
    db_session.add(pr)
    db_session.flush()
    run = AnalysisRun(pull_request_id=pr.id, head_sha="head", status=Status.RUNNING, trigger=Trigger.MANUAL)
    db_session.add(run)
    config = TestConfiguration(repository_id=repo.id, enabled=True, executor_type="DOCKER", coverage_enabled=True)
    db_session.add(config)
    db_session.commit()
    return run, config


@pytest.mark.asyncio
@pytest.mark.parametrize("escape", ["..", "/", "symlink"])
async def test_working_directory_cannot_escape_checkout(db_session, configured_run, tmp_path, monkeypatch, escape):
    run, config = configured_run
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    if escape == "symlink":
        try:
            (checkout / "outside").symlink_to(tmp_path, target_is_directory=True)
        except OSError:
            pytest.skip("Creating symlinks requires privileges on this Windows host")
        config.working_directory = "outside"
    else:
        config.working_directory = escape
    monkeypatch.setattr("codegate.services.test_service.tempfile.mkdtemp", lambda **kwargs: str(checkout))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    execute = AsyncMock()
    monkeypatch.setattr("codegate.services.test_service.PytestRunner.run", execute)
    result = await ExecutionService(TestingStore(), AnalysisStore()).execute_tests(
        db_session, run.id, "wrong-repo", "base", "head"
    )
    execute.assert_not_awaited()
    assert result.execution_status == ExecutionStatus.FAILED
    assert "workspace" in result.error_message.lower()


@pytest.mark.asyncio
async def test_changed_coverage_reads_checkout_not_provider_path(db_session, configured_run, tmp_path, monkeypatch):
    run, config = configured_run
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    config.working_directory = "src"
    monkeypatch.setattr("codegate.services.test_service.tempfile.mkdtemp", lambda **kwargs: str(checkout))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    coverage = CoverageMetrics(total_lines=2, covered_lines=1, missing_lines=1, line_coverage=50,
                               files={"app.py": {"executed_lines": [1], "missing_lines": [2]}})
    execute = AsyncMock(return_value=(
        ExecutionStatus.COMPLETED, Outcome.PASSED, JUnitMetrics(tests=1, passed=1), coverage, "", ""
    ))
    monkeypatch.setattr("codegate.services.test_service.PytestRunner.run", execute)
    changed = AsyncMock(return_value={"src/app.py": {1, 2}})
    monkeypatch.setattr("codegate.services.test_service.ChangedLinesResolver.get_changed_lines", changed)
    result = await ExecutionService(TestingStore(), AnalysisStore()).execute_tests(
        db_session, run.id, "wrong-repo", "base", "head"
    )
    changed.assert_awaited_once_with(str(checkout), "base", "head")
    assert result.coverage_report.changed_line_coverage == 50
    assert not checkout.exists()


def test_preexisting_local_config_cannot_bypass_server_policy(monkeypatch, tmp_path):
    from codegate.config.settings import settings
    from codegate.engines.testing.executor import DisabledExecutor

    monkeypatch.setattr(settings, "ALLOW_LOCAL_TEST_EXECUTOR", False)
    config = TestConfiguration(enabled=True, executor_type="LOCAL_TRUSTED")
    executor = ExecutionService(TestingStore(), AnalysisStore())._get_executor(config, str(tmp_path))
    assert isinstance(executor, DisabledExecutor)
