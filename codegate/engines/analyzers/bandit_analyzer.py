import json
import logging
import os
from typing import List, Optional

from codegate.database.models.analysis import Severity, Source, Status
from codegate.engines.analyzers.base import BaseAnalyzer
from codegate.engines.analyzers.schemas import AnalyzerResult, NormalizedFinding

logger = logging.getLogger(__name__)

class BanditAnalyzer(BaseAnalyzer):
    
    @property
    def name(self) -> Source:
        return Source.BANDIT
        
    @property
    def command(self) -> List[str]:
        import sys
        return [sys.executable, "-I", "-m", "bandit", "-r", ".", "-f", "json"]

    def supports(self) -> bool:
        try:
            import bandit
            return True
        except ImportError:
            return False

    def _map_severity(self, bandit_severity: str) -> Severity:
        mapping = {
            "LOW": Severity.LOW,
            "MEDIUM": Severity.MEDIUM,
            "HIGH": Severity.HIGH
        }
        return mapping.get(bandit_severity.upper(), Severity.LOW)

    def parse_output(self, stdout: str, stderr: str, returncode: int) -> AnalyzerResult:
        result = AnalyzerResult(
            analyzer=self.name,
            status=Status.SUCCESS,
            findings=[]
        )
        
        if not stdout.strip():
            if returncode != 0:
                result.status = Status.FAILED
                result.error_message = stderr or f"Bandit exited with code {returncode}"
            return result
            
        try:
            data = json.loads(stdout)
            raw_findings = data.get("results", [])
            
            for item in raw_findings:
                test_id = item.get("test_id")
                test_name = item.get("test_name", "")
                issue_text = item.get("issue_text", "")
                filepath = item.get("filename", "")
                
                finding = NormalizedFinding(
                    analyzer=self.name,
                    category="SECURITY",
                    severity=self._map_severity(item.get("issue_severity", "LOW")),
                    rule_id=test_id,
                    file_path=filepath,
                    start_line=item.get("line_number"),
                    end_line=item.get("line_range", [item.get("line_number")])[-1] if item.get("line_range") else item.get("line_number"),
                    title=f"Bandit {test_id} ({test_name})",
                    description=issue_text,
                    raw_data={
                        "confidence": item.get("issue_confidence"),
                        "more_info": item.get("more_info")
                    }
                )
                result.findings.append(finding)
                
            if data.get("errors"):
                logger.warning(f"Bandit encountered errors on some files: {data['errors']}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bandit JSON output: {e}")
            result.status = Status.FAILED
            result.error_message = f"Failed to parse JSON: {e}\nStdout: {stdout}"
            
        return result
