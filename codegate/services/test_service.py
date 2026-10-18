import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from codegate.config.settings import settings
from codegate.database.models import AnalysisRun, Repository
from codegate.database.models.testing import CoverageReport, TestConfiguration, TestRun
from codegate.engines.testing.changed_lines import ChangedLinesResolver
from codegate.engines.testing.executor import (
    DisabledExecutor,
    DockerTestExecutor,
    LocalTrustedExecutor,
    resolve_workspace_directory,
)
from codegate.engines.testing.pytest_runner import PytestRunner
from codegate.engines.testing.schemas import CoverageMetrics, ExecutionStatus, JUnitMetrics, TestOutcome
from codegate.repositories.analysis_store import AnalysisStore
from codegate.repositories.testing_store import TestingStore

logger = logging.getLogger(__name__)

class TestExecutionService:
    def __init__(self, testing_store: TestingStore, analysis_store: AnalysisStore):
        self.testing_store = testing_store
        self.analysis_store = analysis_store
        
    def _get_executor(self, config: TestConfiguration, workspace_root: Optional[str] = None):
        if not config.enabled:
            return DisabledExecutor()
            
        executor_type = config.executor_type.upper() if config.executor_type else "DISABLED"
        if executor_type == "LOCAL_TRUSTED":
            if not settings.ALLOW_LOCAL_TEST_EXECUTOR:
                return DisabledExecutor()
            return LocalTrustedExecutor(workspace_root=workspace_root)
        elif executor_type == "DOCKER":
            image = config.docker_image or "python:3.12-slim"
            return DockerTestExecutor(docker_image=image, workspace_root=workspace_root)
        else:
            return DisabledExecutor()
            
    async def execute_tests(self, db: Session, analysis_run_id: int, repo_path: str, base_sha: str, head_sha: str) -> Optional[TestRun]:
        # Load AnalysisRun
        analysis_run = db.query(AnalysisRun).filter_by(id=analysis_run_id).first()
        if not analysis_run:
            logger.error(f"AnalysisRun {analysis_run_id} not found.")
            return None
            
        repo_id = analysis_run.pull_request.repository_id
        
        # Load Config
        config = self.testing_store.get_test_configuration(db, repo_id)
        if not config:
            # Create default disabled config
            config = self.testing_store.upsert_test_configuration(db, repo_id, {})
            
        # Create pending TestRun
        test_run_data = {
            "runner_version": "test-v1",
            "framework": config.framework,
            "executor_type": config.executor_type,
            "execution_status": ExecutionStatus.PENDING.value,
            "test_outcome": TestOutcome.UNKNOWN.value,
            "started_at": datetime.utcnow()
        }
        test_run = self.testing_store.upsert_test_run(db, analysis_run_id, test_run_data)
        
        if not config.enabled:
            logger.info(f"Tests disabled for repository {repo_id}")
            self.testing_store.update_test_run(db, analysis_run_id, {
                "execution_status": ExecutionStatus.SKIPPED.value,
                "finished_at": datetime.utcnow()
            })
            return test_run
            
        # Prepare safe isolated workspace
        workspace_dir = tempfile.mkdtemp(prefix=f"codegate_tests_{analysis_run_id}_")
        try:
            # Clone and checkout
            analysis_run = self.analysis_store.get_by_id(db, analysis_run_id)
            repo_full_name = analysis_run.pull_request.repository.full_name
            clone_url = f"https://github.com/{repo_full_name}.git"
            
            import subprocess
            try:
                subprocess.run(["git", "clone", clone_url, workspace_dir], check=True, capture_output=True, timeout=300)
                if head_sha:
                    subprocess.run(["git", "checkout", head_sha], cwd=workspace_dir, check=True,
                                   capture_output=True, timeout=60)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to clone {clone_url} for run {analysis_run_id}: {e.stderr}")
                raise

            working_directory = str(resolve_workspace_directory(
                workspace_dir, os.path.join(workspace_dir, config.working_directory or ".")
            ))
                
            self.testing_store.update_test_run(db, analysis_run_id, {"execution_status": ExecutionStatus.RUNNING.value})
            
            executor = self._get_executor(config, workspace_dir)
            runner = PytestRunner(executor)
            
            test_paths = config.test_paths_json or []
            pytest_args = config.pytest_args_json or []
            
            # RUN
            exec_status, outcome, junit, cov, stdout, stderr = await runner.run(
                working_directory=working_directory,
                test_paths=test_paths,
                pytest_args=pytest_args,
                timeout_seconds=config.timeout_seconds,
                coverage_enabled=config.coverage_enabled,
                install_command=config.install_command,
                test_command=config.test_command,
                network_enabled=config.network_enabled
            )
            
            # Process Changed Code Coverage
            changed_cov_percent = None
            changed_total = 0
            changed_covered = 0
            changed_missing = 0
            
            if cov and config.coverage_enabled:
                changed_lines_map = await ChangedLinesResolver.get_changed_lines(workspace_dir, base_sha, head_sha)

                # Coverage paths are relative to the test working directory,
                # while git paths are relative to the checkout root.
                prefix = Path(working_directory).relative_to(Path(workspace_dir).resolve())
                if cov.files:
                    cov.files = {
                        (prefix / path.replace("\\", "/")).as_posix(): data
                        for path, data in cov.files.items()
                    }
                
                if not base_sha:
                    # Missing base_sha, coverage = null
                    changed_cov_percent = None
                else:
                    changed_covered, changed_total, changed_cov_percent = ChangedLinesResolver.calculate_changed_coverage(
                        cov, changed_lines_map
                    )
                    
                    if changed_total == 0:
                        # No executable changed lines
                        changed_cov_percent = None
                        # Optionally record reason = NO_EXECUTABLE_CHANGED_LINES
                
            # Update TestRun
            self.testing_store.update_test_run(db, analysis_run_id, {
                "execution_status": exec_status.value,
                "test_outcome": outcome.value,
                "tests_total": junit.tests,
                "tests_passed": junit.passed,
                "tests_failed": junit.failures,
                "tests_skipped": junit.skipped,
                "tests_errors": junit.errors,
                "duration_ms": int(junit.duration * 1000),
                "stdout_excerpt": stdout,
                "stderr_excerpt": stderr,
                "finished_at": datetime.utcnow()
            })
            
            if cov:
                cov_data = {
                    "coverage_version": "cov-v1",
                    "line_coverage": cov.line_coverage,
                    "branch_coverage": cov.branch_coverage,
                    "total_lines": cov.total_lines,
                    "covered_lines": cov.covered_lines,
                    "missing_lines": cov.missing_lines,
                    "changed_line_coverage": changed_cov_percent,
                    "is_complete": True
                }
                self.testing_store.upsert_coverage_report(db, test_run.id, cov_data)
                
        except Exception as e:
            logger.error(f"Error executing tests for {analysis_run_id}: {str(e)}")
            self.testing_store.update_test_run(db, analysis_run_id, {
                "execution_status": ExecutionStatus.FAILED.value,
                "error_message": str(e),
                "finished_at": datetime.utcnow()
            })
        finally:
            # Cleanup temp directory
            try:
                shutil.rmtree(workspace_dir)
            except Exception as e:
                logger.error(f"Failed to cleanup temp workspace {workspace_dir}: {str(e)}")
                
        return self.testing_store.get_test_run(db, analysis_run_id)
