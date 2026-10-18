import asyncio
import os
import re
import sys
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def resolve_workspace_directory(workspace_root: str, working_directory: str) -> Path:
    """Resolve symlinks and reject directories outside the allocated checkout."""
    root = Path(workspace_root).resolve(strict=True)
    directory = Path(working_directory).resolve(strict=True)
    if not root.is_dir() or not directory.is_dir() or not directory.is_relative_to(root):
        raise ValueError("Working directory must be inside the allocated workspace.")
    return directory


async def _communicate_limited(process, timeout_seconds: int) -> Tuple[bytes, bytes, bool]:
    """Drain both pipes continuously while retaining at most 64 KiB per pipe."""
    async def read_limited(stream):
        retained = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            available = max(0, 64 * 1024 - len(retained))
            retained.extend(chunk[:available])
            truncated = truncated or len(chunk) > available
        if truncated:
            retained.extend(b"\n...[TRUNCATED]")
        return bytes(retained)

    stdout_task = asyncio.create_task(read_limited(process.stdout))
    stderr_task = asyncio.create_task(read_limited(process.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
    finally:
        # Descendants can inherit pipes; do not wait indefinitely for EOF.
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task), timeout=5
            )
        except asyncio.TimeoutError:
            stdout, stderr = b"", b"Output drain timed out."
    return stdout, stderr, timed_out


class TestExecutor(ABC):
    @abstractmethod
    async def execute(self, command: List[str], working_directory: str,
                      env: Optional[Dict[str, str]] = None, timeout_seconds: int = 900,
                      network_enabled: bool = False) -> Tuple[int, str, str, bool]:
        """Return (exit_code, stdout, stderr, is_timeout)."""


class DisabledExecutor(TestExecutor):
    async def execute(self, command: List[str], working_directory: str,
                      env: Optional[Dict[str, str]] = None, timeout_seconds: int = 900,
                      network_enabled: bool = False) -> Tuple[int, str, str, bool]:
        return -1, "Test execution is DISABLED by policy.", "", False


class WorkspaceExecutor(TestExecutor):
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root

    def _validate_path(self, working_directory: str) -> bool:
        if not self.workspace_root:
            return False
        try:
            resolve_workspace_directory(self.workspace_root, working_directory)
        except (OSError, ValueError, RuntimeError):
            return False
        return True


class LocalTrustedExecutor(WorkspaceExecutor):
    """Runs arbitrary repository code on the host. This is NOT a sandbox.

    Enable only with server-side opt-in and repositories the operator trusts.
    The workspace check prevents configuration mistakes, not malicious Python.
    """

    python_executable = sys.executable

    def _sanitize_env(self, provided_env: Optional[Dict[str, str]]) -> Dict[str, str]:
        safe_env = {
            key: os.environ[key]
            for key in ["PATH", "SYSTEMROOT", "USERPROFILE", "HOME", "LANG", "LC_ALL", "TEMP", "TMP"]
            if key in os.environ
        }
        if provided_env:
            safe_env.update(provided_env)
        return safe_env

    async def execute(self, command: List[str], working_directory: str,
                      env: Optional[Dict[str, str]] = None, timeout_seconds: int = 900,
                      network_enabled: bool = False) -> Tuple[int, str, str, bool]:
        if not self._validate_path(working_directory):
            return -1, "", "Working directory is outside the allocated workspace.", False
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=working_directory, env=self._sanitize_env(env),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr, timed_out = await _communicate_limited(process, timeout_seconds)
            if timed_out:
                return -1, "", f"Execution timed out after {timeout_seconds} seconds.", True
            return (
                process.returncode if process.returncode is not None else -1,
                stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace"), False
            )
        except Exception as exc:
            return -1, "", f"Executor exception: {exc}", False


class DockerTestExecutor(WorkspaceExecutor):
    """Container execution with bounded output and explicit workspace mounting.

    Requires a reachable Docker daemon. Use a dedicated worker for untrusted PRs;
    this container implementation is not a guarantee against hostile code.
    """

    def __init__(self, docker_image: str, workspace_root: Optional[str] = None):
        super().__init__(workspace_root)
        self.docker_image = docker_image

    async def execute(self, command: List[str], working_directory: str,
                      env: Optional[Dict[str, str]] = None, timeout_seconds: int = 900,
                      network_enabled: bool = False) -> Tuple[int, str, str, bool]:
        if not self._validate_path(working_directory):
            return -1, "", "Working directory is outside the allocated workspace.", False
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", self.docker_image):
            return -1, "", "Invalid Docker image reference.", False
        container_name = f"codegate-test-{uuid.uuid4().hex}"
        docker_cmd = [
            "docker", "run", "--rm", "--name", container_name,
            "--memory=1g", "--cpus=1.0", "--pids-limit=256",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--network", "bridge" if network_enabled else "none",
            "-v", f"{Path(working_directory).resolve()}:/workspace", "-w", "/workspace",
        ]
        for key, value in (env or {}).items():
            docker_cmd.extend(["--env", f"{key}={value}"])
        docker_cmd.extend([self.docker_image, *command])
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr, timed_out = await _communicate_limited(process, timeout_seconds)
            if timed_out:
                return -1, "", f"Docker execution timed out after {timeout_seconds} seconds.", True
            return (
                process.returncode if process.returncode is not None else -1,
                stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace"), False
            )
        except Exception as exc:
            return -1, "", f"Docker executor exception: {exc}", False
        finally:
            # Killing the CLI alone does not stop its container.
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "rm", "--force", container_name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                try:
                    await asyncio.wait_for(cleanup.wait(), timeout=10)
                except asyncio.TimeoutError:
                    cleanup.kill()
                    await cleanup.wait()
            except OSError:
                pass
