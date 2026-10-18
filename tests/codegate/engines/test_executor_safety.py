import sys
from unittest.mock import AsyncMock

import pytest

from codegate.engines.testing.executor import DisabledExecutor, DockerTestExecutor, LocalTrustedExecutor


@pytest.mark.asyncio
async def test_disabled_executor_returns_error():
    code, stdout, _, timed_out = await DisabledExecutor().execute(["unused"], ".")
    assert code == -1 and "DISABLED" in stdout and not timed_out


def test_local_executor_validates_real_paths(tmp_path):
    checkout = tmp_path / "checkout"
    tests = checkout / "tests"
    tests.mkdir(parents=True)
    executor = LocalTrustedExecutor(str(checkout))
    assert executor._validate_path(str(checkout))
    assert executor._validate_path(str(tests))
    assert not executor._validate_path(str(tmp_path))
    assert not executor._validate_path(str(checkout / "missing"))
    assert not LocalTrustedExecutor()._validate_path(str(checkout))


def test_local_executor_does_not_inherit_service_credentials(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "parent-only-token")
    monkeypatch.setenv("OPENAI_API_KEY", "parent-only-key")
    safe = LocalTrustedExecutor()._sanitize_env({"SAFE_VAR": "value"})
    assert "GITHUB_TOKEN" not in safe and "OPENAI_API_KEY" not in safe
    assert safe["SAFE_VAR"] == "value"


@pytest.mark.asyncio
async def test_local_executor_timeout(tmp_path):
    executor = LocalTrustedExecutor(str(tmp_path))
    code, _, stderr, timed_out = await executor.execute(
        [sys.executable, "-c", "import time; time.sleep(10)"], str(tmp_path), timeout_seconds=0.1
    )
    assert code == -1 and timed_out
    assert "Execution timed out" in stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code", [0, 127])
async def test_docker_preserves_exit_code_and_cleans_container(tmp_path, monkeypatch, exit_code):
    process = AsyncMock()
    process.returncode = exit_code
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("codegate.engines.testing.executor._communicate_limited",
                        AsyncMock(return_value=(b"out", b"err", False)))
    code, out, err, timed_out = await DockerTestExecutor("python:3.12-slim", str(tmp_path)).execute(
        ["pytest"], str(tmp_path)
    )
    assert code == exit_code and out == "out" and err == "err" and not timed_out
    launch, cleanup = spawn.call_args_list
    assert "--network" in launch.args and "none" in launch.args
    assert "--cap-drop=ALL" in launch.args
    assert cleanup.args[:3] == ("docker", "rm", "--force")
    assert cleanup.args[3] == launch.args[launch.args.index("--name") + 1]


@pytest.mark.asyncio
async def test_docker_timeout_also_removes_named_container(tmp_path, monkeypatch):
    spawn = AsyncMock(return_value=AsyncMock())
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("codegate.engines.testing.executor._communicate_limited",
                        AsyncMock(return_value=(b"", b"", True)))
    code, _, _, timed_out = await DockerTestExecutor("python:3.12-slim", str(tmp_path)).execute(
        ["pytest"], str(tmp_path), timeout_seconds=1
    )
    assert code == -1 and timed_out
    assert spawn.call_args_list[-1].args[:3] == ("docker", "rm", "--force")
