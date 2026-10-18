"""Regression cases for executing repository code and trusting test reports."""

import sys
from unittest.mock import AsyncMock

import pytest

from codegate.engines.testing.executor import DockerTestExecutor, LocalTrustedExecutor
from codegate.engines.testing.pytest_runner import PytestRunner
from codegate.engines.testing.schemas import ExecutionStatus
from codegate.engines.testing.schemas import TestOutcome as Outcome


@pytest.mark.asyncio
async def test_local_executor_accepts_real_workspace_and_bounds_output(tmp_path):
    executor = LocalTrustedExecutor(workspace_root=str(tmp_path))
    code, stdout, stderr, timed_out = await executor.execute(
        [sys.executable, "-c", "print('x' * 100000)"], str(tmp_path)
    )
    assert code == 0 and not timed_out and not stderr
    assert len(stdout) < 66000
    assert "TRUNCATED" in stdout


@pytest.mark.asyncio
@pytest.mark.parametrize("executor_name", ["local", "docker"])
async def test_executor_rejects_directory_outside_explicit_workspace(tmp_path, monkeypatch, executor_name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = (LocalTrustedExecutor(workspace_root=str(workspace)) if executor_name == "local"
                else DockerTestExecutor("python:3.12-slim", workspace_root=str(workspace)))
    spawn = AsyncMock()
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    code, _, stderr, _ = await executor.execute(["echo", "unsafe"], str(tmp_path))
    assert code == -1
    assert "workspace" in stderr.lower()
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_local_executor_without_workspace_fails_closed(tmp_path):
    code, _, stderr, _ = await LocalTrustedExecutor().execute(["echo", "unsafe"], str(tmp_path))
    assert code == -1
    assert "workspace" in stderr.lower()


@pytest.mark.asyncio
async def test_nonzero_pytest_exit_cannot_be_overridden_by_passing_xml(tmp_path):
    class FailedCollection:
        async def execute(self, **kwargs):
            (tmp_path / "junit_report.xml").write_text(
                '<testsuite tests="1"><testcase name="passed"/></testsuite>', encoding="utf-8"
            )
            return 2, "", "collection interrupted", False

    status, outcome, _, _, _, _ = await PytestRunner(FailedCollection()).run(
        str(tmp_path), [], [], 5, False
    )
    assert status == ExecutionStatus.COMPLETED
    assert outcome == Outcome.FAILED


@pytest.mark.asyncio
async def test_preexisting_reports_are_removed_before_execution(tmp_path):
    report = tmp_path / "junit_report.xml"
    report.write_text('<testsuite tests="20" failures="0"/>', encoding="utf-8")
    (tmp_path / "coverage_report.json").write_text('{"fake":true}', encoding="utf-8")

    class NoReport:
        async def execute(self, **kwargs):
            assert not report.exists()
            assert not (tmp_path / "coverage_report.json").exists()
            return 2, "", "no tests collected", False

    _, outcome, metrics, coverage, _, _ = await PytestRunner(NoReport()).run(
        str(tmp_path), [], [], 5, False
    )
    assert outcome == Outcome.FAILED
    assert metrics.tests == 0 and coverage is None


@pytest.mark.asyncio
async def test_failed_coverage_export_is_not_accepted(tmp_path):
    class FailedCoverage:
        async def execute(self, command, **kwargs):
            if "json" in command:
                (tmp_path / "coverage_report.json").write_text(
                    '{"totals":{"num_statements":1,"covered_lines":1,"percent_covered":100}}',
                    encoding="utf-8",
                )
                return 1, "", "coverage export failed", False
            return 0, "", "", False

    _, outcome, _, coverage, _, _ = await PytestRunner(FailedCoverage()).run(
        str(tmp_path), [], [], 5, True
    )
    assert outcome == Outcome.PASSED
    assert coverage is None


@pytest.mark.asyncio
async def test_local_pytest_uses_venv_interpreter_not_path_python(tmp_path):
    executor = LocalTrustedExecutor(str(tmp_path))
    executor.execute = AsyncMock(return_value=(0, "", "", False))
    await PytestRunner(executor).run(str(tmp_path), [], [], 5, False)
    assert executor.execute.call_args.kwargs["command"][:2] == [sys.executable, "-m"]
