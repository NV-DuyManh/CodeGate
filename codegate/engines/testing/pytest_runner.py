import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

from codegate.engines.testing.coverage_parser import CoverageParser
from codegate.engines.testing.executor import TestExecutor
from codegate.engines.testing.junit_parser import JUnitParser
from codegate.engines.testing.schemas import CoverageMetrics, ExecutionStatus, JUnitMetrics, TestOutcome

logger = logging.getLogger(__name__)

class PytestRunner:
    """Orchestrates pytest + coverage.py via a TestExecutor."""
    
    def __init__(self, executor: TestExecutor):
        self.executor = executor
        
    async def run(self, 
                  working_directory: str, 
                  test_paths: list[str], 
                  pytest_args: list[str], 
                  timeout_seconds: int,
                  coverage_enabled: bool,
                  install_command: Optional[str] = None,
                  test_command: Optional[str] = None,
                  network_enabled: bool = False) -> Tuple[ExecutionStatus, TestOutcome, JUnitMetrics, Optional[CoverageMetrics], str, str]:
        
        # We output xml to a fixed file in the working directory
        junit_xml_path = "junit_report.xml"
        coverage_json_path = "coverage_report.json"
        python_executable = getattr(self.executor, "python_executable", "python")

        # Never trust reports left by an earlier run or committed in the repo.
        for report in (junit_xml_path, coverage_json_path, ".coverage"):
            report_path = os.path.join(working_directory, report)
            if os.path.lexists(report_path):
                os.remove(report_path)
        
        if install_command:
            command = ["sh", "-c", f"{install_command} && {test_command or 'pytest'}"]
        elif test_command:
            command = ["sh", "-c", test_command]
        else:
            command = [
                python_executable, "-m"
            ]
            
            if coverage_enabled:
                command.extend(["coverage", "run", "--branch", "-m", "pytest"])
            else:
                command.append("pytest")
                
            command.extend([
                f"--junitxml={junit_xml_path}"
            ])
            
            if pytest_args:
                command.extend(pytest_args)
                
            if test_paths:
                command.extend(test_paths)
            
        # Execute the test command
        exit_code, stdout, stderr, is_timeout = await self.executor.execute(
            command=command,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled
        )
        
        if is_timeout:
            return ExecutionStatus.TIMEOUT, TestOutcome.UNKNOWN, JUnitMetrics(), None, stdout, stderr
            
        if exit_code == -1: # Executor failed to run entirely (e.g., path traversal or disabled)
            return ExecutionStatus.SKIPPED if "DISABLED" in stdout else ExecutionStatus.FAILED, TestOutcome.UNKNOWN, JUnitMetrics(), None, stdout, stderr
            
        # Parse JUnit
        junit_metrics = JUnitMetrics()
        junit_full_path = os.path.join(working_directory, junit_xml_path)
        if os.path.exists(junit_full_path):
            with open(junit_full_path, 'r', encoding='utf-8') as f:
                junit_metrics = JUnitParser.parse(f.read())
                
        # Parse Coverage if enabled
        coverage_metrics = None
        if coverage_enabled:
            # Generate the json report
            cov_cmd = [python_executable, "-m", "coverage", "json", "-o", coverage_json_path]
            # If the user supplied a custom test command, we don't know how to run coverage automatically unless they output coverage.json.
            # We'll just run `coverage json` and see if they ran coverage via their script.
            cov_exit_code, _, _, cov_timed_out = await self.executor.execute(
                command=cov_cmd,
                working_directory=working_directory,
                timeout_seconds=60,
                network_enabled=False
            )
            
            cov_full_path = os.path.join(working_directory, coverage_json_path)
            if cov_exit_code == 0 and not cov_timed_out and os.path.exists(cov_full_path):
                with open(cov_full_path, 'r', encoding='utf-8') as f:
                    coverage_metrics = CoverageParser.parse(f.read())
                    
        # Determine test outcome
        test_outcome = TestOutcome.UNKNOWN
        if exit_code != 0:
            test_outcome = TestOutcome.FAILED
        elif junit_metrics.tests > 0:
            if junit_metrics.failures > 0 or junit_metrics.errors > 0:
                test_outcome = TestOutcome.FAILED
            else:
                test_outcome = TestOutcome.PASSED
        else:
            if exit_code == 0:
                test_outcome = TestOutcome.PASSED
            else:
                test_outcome = TestOutcome.FAILED
                
        return ExecutionStatus.COMPLETED, test_outcome, junit_metrics, coverage_metrics, stdout, stderr
