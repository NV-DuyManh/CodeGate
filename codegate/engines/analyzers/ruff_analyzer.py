import json
import logging
import os
from typing import List, Optional

from codegate.database.models.analysis import Severity, Source, Status
from codegate.engines.analyzers.base import BaseAnalyzer
from codegate.engines.analyzers.schemas import AnalyzerResult, NormalizedFinding

logger = logging.getLogger(__name__)

class RuffAnalyzer(BaseAnalyzer):
    
    @property
    def name(self) -> Source:
        return Source.RUFF
        
    @property
    def command(self) -> List[str]:
        # Using sys.executable to ensure we run the installed ruff in the same environment
        import sys
        return [sys.executable, "-I", "-m", "ruff", "check", ".", "--output-format", "json"]

    def supports(self) -> bool:
        try:
            import ruff
            return True
        except ImportError:
            return False

    def _map_severity(self, rule_id: str) -> Severity:
        """
        Deterministic mapping of Ruff rule to Severity.
        E (pycodestyle errors) -> MEDIUM
        F (Pyflakes) -> HIGH
        S (flake8-bandit) -> HIGH
        Others -> LOW
        """
        if not rule_id:
            return Severity.LOW
            
        if rule_id.startswith("F") or rule_id.startswith("S"):
            return Severity.HIGH
        elif rule_id.startswith("E") or rule_id.startswith("B") or rule_id.startswith("C90"):
            return Severity.MEDIUM
        return Severity.LOW

    def parse_output(self, stdout: str, stderr: str, returncode: int) -> AnalyzerResult:
        result = AnalyzerResult(
            analyzer=self.name,
            status=Status.SUCCESS,
            findings=[]
        )
        
        if not stdout.strip():
            # No findings, ruff might have just returned empty stdout on success
            if returncode != 0:
                result.status = Status.FAILED
                result.error_message = stderr or f"Ruff exited with code {returncode}"
            return result
            
        try:
            raw_findings = json.loads(stdout)
            
            for item in raw_findings:
                rule_id = item.get("code")
                message = item.get("message", "No message provided")
                filepath = item.get("filename", "")
                
                # Make filepath relative to workspace if possible
                if os.path.isabs(filepath):
                    # We might not know the workspace root perfectly here, but the runner 
                    # executes the command with cwd=workspace, so usually paths are absolute 
                    # and we can extract basename or just keep it. Ruff outputs absolute paths.
                    pass
                
                start = item.get("location", {})
                end = item.get("end_location", {})
                
                finding = NormalizedFinding(
                    analyzer=self.name,
                    category="CODE_QUALITY",
                    severity=self._map_severity(rule_id),
                    rule_id=rule_id,
                    file_path=filepath,
                    start_line=start.get("row"),
                    end_line=end.get("row"),
                    title=f"Ruff {rule_id}: {message}",
                    description=message,
                    raw_data=item
                )
                result.findings.append(finding)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ruff JSON output: {e}")
            result.status = Status.FAILED
            result.error_message = f"Failed to parse JSON: {e}\nStdout: {stdout}"
            
        return result
