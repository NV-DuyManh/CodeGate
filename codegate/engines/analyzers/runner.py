import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from codegate.config.settings import settings
from codegate.database.models.analysis import AnalysisRun, AnalyzerRun, CodeMetric, Finding, Status
from codegate.engines.analyzers.bandit_analyzer import BanditAnalyzer
from codegate.engines.analyzers.base import BaseAnalyzer
from codegate.engines.analyzers.radon_analyzer import RadonAnalyzer
from codegate.engines.analyzers.ruff_analyzer import RuffAnalyzer
from codegate.engines.analyzers.schemas import AnalyzerResult
from codegate.engines.analyzers.workspace import AnalyzerWorkspace

logger = logging.getLogger(__name__)

class StaticAnalysisRunner:
    def __init__(self, db: Session, analysis_run: AnalysisRun, clone_url: str, head_sha: str, token: Optional[str] = None):
        self.db = db
        self.analysis_run = analysis_run
        self.workspace = AnalyzerWorkspace(clone_url, head_sha, token)
        self.analyzers: List[BaseAnalyzer] = []
        
        self._register_analyzers()

    def _register_analyzers(self):
        if settings.RUFF_ENABLED:
            self.analyzers.append(RuffAnalyzer())
        if settings.BANDIT_ENABLED:
            self.analyzers.append(BanditAnalyzer())
        if settings.RADON_ENABLED:
            self.analyzers.append(RadonAnalyzer())
            
        # Filter supported only
        self.analyzers = [a for a in self.analyzers if a.supports()]

    async def _run_analyzer(self, analyzer: BaseAnalyzer, workspace_dir: str) -> AnalyzerResult:
        """Run a single analyzer asynchronously with timeout."""
        start_time = time.time()
        
        # Initialize DB run record
        db_run = AnalyzerRun(
            analysis_run_id=self.analysis_run.id,
            analyzer=analyzer.name,
            status=Status.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(db_run)
        self.db.commit()
        
        # Prepare subprocess
        try:
            # We use asyncio.create_subprocess_exec
            process = await asyncio.create_subprocess_exec(
                *analyzer.command,
                cwd=workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=settings.ANALYZER_TIMEOUT_SECONDS
                )
                
                # Decode
                stdout_str = stdout.decode('utf-8', errors='replace')
                stderr_str = stderr.decode('utf-8', errors='replace')
                
                # Parse
                result = analyzer.parse_output(stdout_str, stderr_str, process.returncode)
                
            except asyncio.TimeoutError:
                # Kill process
                try:
                    process.kill()
                except OSError:
                    pass
                await process.communicate()
                result = AnalyzerResult(
                    analyzer=analyzer.name,
                    status=Status.TIMEOUT,
                    error_message=f"Analyzer timed out after {settings.ANALYZER_TIMEOUT_SECONDS}s"
                )
                
        except Exception as e:
            logger.exception(f"Analyzer {analyzer.name} failed unexpectedly")
            result = AnalyzerResult(
                analyzer=analyzer.name,
                status=Status.FAILED,
                error_message=str(e)
            )
            
        # Update run stats
        end_time = time.time()
        result.duration_ms = int((end_time - start_time) * 1000)
        
        # Update DB run record
        db_run.status = result.status
        db_run.completed_at = datetime.now(timezone.utc)
        db_run.duration_ms = result.duration_ms
        db_run.error_message = result.error_message
        self.db.commit()
        
        return result

    def _relative_path(self, path: Optional[str], workspace_dir: Optional[str]) -> Optional[str]:
        if path is None:
            return None
        if workspace_dir and os.path.isabs(path):
            path = os.path.relpath(path, workspace_dir)
        return path.replace("\\", "/").removeprefix("./")

    def _persist_results(self, result: AnalyzerResult, workspace_dir: Optional[str] = None):
        """Persist findings and metrics to DB."""
        workspace_dir = workspace_dir or self.workspace.workspace_dir
        changed_files = {item.filename for item in self.analysis_run.pull_request.files}
        for finding in result.findings:
            file_path = self._relative_path(finding.file_path, workspace_dir)
            db_finding = Finding(
                analysis_run_id=self.analysis_run.id,
                source=finding.analyzer,
                category=finding.category,
                severity=finding.severity,
                rule_id=finding.rule_id,
                file_path=file_path,
                is_changed_file=file_path in changed_files if changed_files else None,
                is_new_code=finding.is_new_code,
                start_line=finding.start_line,
                end_line=finding.end_line,
                title=finding.title,
                description=finding.description,
                recommendation=finding.recommendation,
                raw_data=finding.raw_data
            )
            self.db.add(db_finding)
            
        for metric in result.metrics:
            file_path = self._relative_path(metric.file_path, workspace_dir)
            if changed_files and file_path not in changed_files:
                continue
            db_metric = CodeMetric(
                analysis_run_id=self.analysis_run.id,
                analyzer=metric.analyzer,
                metric_name=metric.metric_name,
                file_path=file_path,
                symbol=metric.symbol,
                value=metric.value,
                grade=metric.grade,
                metadata_json=metric.metadata
            )
            self.db.add(db_metric)
            
        self.db.commit()

    async def run_all(self):
        """Run all registered analyzers, isolate failures, persist results."""
        if not settings.STATIC_ANALYSIS_ENABLED or not self.analyzers:
            return
            
        workspace_dir = None
        try:
            workspace_dir = self.workspace.prepare()
            
            # We run sequentially here to avoid killing disk I/O, but could run concurrently
            # with asyncio.gather if desired.
            for analyzer in self.analyzers:
                result = await self._run_analyzer(analyzer, workspace_dir)
                self._persist_results(result, workspace_dir)
                
        except Exception:
            logger.exception("Failed to prepare workspace or run analyzers")
            raise
        finally:
            self.workspace.cleanup()
