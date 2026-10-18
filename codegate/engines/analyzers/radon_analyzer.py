import json
import logging
from typing import List

from codegate.database.models.analysis import Severity, Source, Status
from codegate.engines.analyzers.base import BaseAnalyzer
from codegate.engines.analyzers.schemas import AnalyzerResult, NormalizedFinding, NormalizedMetric

logger = logging.getLogger(__name__)

class RadonAnalyzer(BaseAnalyzer):
    
    @property
    def name(self) -> Source:
        return Source.RADON
        
    @property
    def command(self) -> List[str]:
        import sys
        return [sys.executable, "-I", "-m", "radon", "cc", ".", "--json"]

    def supports(self) -> bool:
        try:
            import radon
            return True
        except ImportError:
            return False

    def parse_output(self, stdout: str, stderr: str, returncode: int) -> AnalyzerResult:
        result = AnalyzerResult(
            analyzer=self.name,
            status=Status.SUCCESS,
            metrics=[],
            findings=[]
        )
        
        if not stdout.strip():
            if returncode != 0:
                result.status = Status.FAILED
                result.error_message = stderr or f"Radon exited with code {returncode}"
            return result
            
        try:
            data = json.loads(stdout)
            
            for filepath, blocks in data.items():
                if isinstance(blocks, dict) and "error" in blocks:
                    logger.warning(f"Radon error in {filepath}: {blocks['error']}")
                    continue
                    
                for block in blocks:
                    block_type = block.get("type", "unknown")
                    name = block.get("name", "unknown")
                    complexity = block.get("complexity", 0)
                    rank = block.get("rank", "A")
                    
                    symbol = f"{block_type}:{name}"
                    if "classname" in block and block["classname"]:
                        symbol = f"{block['classname']}.{name}"
                        
                    metric = NormalizedMetric(
                        analyzer=self.name,
                        metric_name="cyclomatic_complexity",
                        file_path=filepath,
                        symbol=symbol,
                        value=str(complexity),
                        grade=rank,
                        metadata=block
                    )
                    result.metrics.append(metric)
                    
                    # If complexity is extremely high (F), map to a finding as well
                    if rank in ("F", "E"):
                        result.findings.append(NormalizedFinding(
                            analyzer=self.name,
                            category="COMPLEXITY",
                            severity=Severity.HIGH if rank == "F" else Severity.MEDIUM,
                            file_path=filepath,
                            start_line=block.get("lineno"),
                            end_line=block.get("endline"),
                            title=f"High Cyclomatic Complexity ({rank})",
                            description=f"The complexity of {symbol} is {complexity}, which is considered highly complex.",
                            raw_data=block
                        ))
                        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Radon JSON output: {e}")
            result.status = Status.FAILED
            result.error_message = f"Failed to parse JSON: {e}\nStdout: {stdout}"
            
        return result
