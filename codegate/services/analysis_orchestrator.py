import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from codegate.database.models.analysis import AnalysisRun, Finding, Status, Trigger
from codegate.database.models.pull_request import PullRequest
from codegate.engines.analyzers.runner import StaticAnalysisRunner
from codegate.integrations.pr_agent.adapter import CodeGateAdapter
from codegate.integrations.pr_agent.normalizer import PRAgentNormalizer
from codegate.services.policy_publisher import GitHubPolicyCheckPublisher
from codegate.services.policy_service import quality_policy_service
from codegate.services.quality_service import quality_service
from codegate.services.risk_service import risk_service
from pr_agent.git_providers import get_git_provider

logger = logging.getLogger(__name__)

class AnalysisOrchestrator:
    """
    Manages the lifecycle of an AnalysisRun, interacting with the PRAgentAdapter
    and persisting results to the database.
    """
    def __init__(self, db: Session):
        self.db = db

    def _get_latest_completed_run(self, pull_request_id: int, head_sha: str) -> Optional[AnalysisRun]:
        return self.db.query(AnalysisRun).filter(
            AnalysisRun.pull_request_id == pull_request_id,
            AnalysisRun.head_sha == head_sha,
            AnalysisRun.status == Status.COMPLETED
        ).order_by(AnalysisRun.created_at.desc()).first()

    async def trigger_analysis(self, pr: PullRequest, pr_url: str, force: bool = False, trigger_type: Trigger = Trigger.MANUAL) -> Tuple[AnalysisRun, bool]:
        """
        Triggers an analysis.
        Returns Tuple[AnalysisRun, bool] where bool is True if it was a newly created/run analysis,
        and False if it reused an existing completed one.
        """
        # 1. Idempotency check
        if not force:
            existing = self._get_latest_completed_run(pr.id, pr.head_sha)
            if existing:
                logger.info(f"Reusing existing completed analysis {existing.id} for PR {pr.id} (SHA: {pr.head_sha})")
                return existing, False
                
        # 2. Create pending run
        run = AnalysisRun(
            pull_request_id=pr.id,
            head_sha=pr.head_sha,
            status=Status.PENDING,
            trigger=trigger_type
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        # 3. Execute Run
        await self._execute_run(run, pr_url)
        return run, True

    async def _execute_run(self, run: AnalysisRun, pr_url: str):
        """
        Executes the AI review flow using CodeGateAdapter, updates status, and saves findings.
        """
        try:
            # Transition to RUNNING
            run.status = Status.RUNNING
            run.started_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(run)

            # Invoke Adapter
            adapter = CodeGateAdapter(pr_url)
            raw_data = await adapter.run()

            # Normalize Findings
            finding_schemas = PRAgentNormalizer.normalize_findings(raw_data)
            
            # Save Findings
            for schema in finding_schemas:
                finding_db = Finding(
                    analysis_run_id=run.id,
                    source=schema.source,
                    category=schema.category,
                    severity=schema.severity,
                    rule_id=schema.rule_id,
                    file_path=schema.file_path,
                    start_line=schema.start_line,
                    end_line=schema.end_line,
                    title=schema.title,
                    description=schema.description,
                    recommendation=schema.recommendation,
                    confidence=schema.confidence,
                    raw_data=schema.raw_data
                )
                self.db.add(finding_db)

            # Save Usage / Metadata if available
            usage = PRAgentNormalizer.extract_usage(raw_data)
            run.tokens_used = usage.get("total_tokens", 0)
            
            # Commit findings first so quality engine can read them
            self.db.commit()

            # Analyze the same immutable head before scoring static findings and metrics.
            repository = run.pull_request.repository
            provider = getattr(getattr(adapter, "reviewer", None), "git_provider", None)
            token = getattr(getattr(provider, "auth", None), "token", None)
            static_runner = StaticAnalysisRunner(
                self.db,
                run,
                clone_url=repository.url,
                head_sha=run.head_sha,
                token=token if isinstance(token, str) else None,
            )
            await static_runner.run_all()
            
            # 1. Execute Tests & Coverage
            try:
                from codegate.repositories.analysis_store import AnalysisStore
                from codegate.repositories.testing_store import TestingStore
                from codegate.services.test_service import TestExecutionService
                
                git_provider = get_git_provider()(pr_url)
                # Need local repo path. Pr agent adapter usually clones to a temp dir.
                # Here we assume git_provider provides repo_path or it runs locally
                repo_path = getattr(git_provider, "repo_path", ".")
                base = getattr(git_provider.pr, "base", None)
                base_sha = getattr(base, "sha", "") if base else ""
                
                test_service = TestExecutionService(TestingStore(), AnalysisStore())
                # Fire and wait for tests
                # Note: async call
                await test_service.execute_tests(
                    db=self.db,
                    analysis_run_id=run.id,
                    repo_path=repo_path,
                    base_sha=base_sha,
                    head_sha=run.head_sha
                )
            except Exception as e:
                logger.error(f"Test execution failed for AnalysisRun {run.id}: {e}", exc_info=True)
            
            # Calculate Quality Score (errors caught inside, shouldn't fail the run)
            # Will read test results implicitly
            quality_service.calculate_and_persist(self.db, run.id)
            
            # Calculate Risk Score (independent from Quality)
            risk_service.calculate_and_persist(self.db, run.id)

            # Execute Reviewer Recommendation Engine
            try:
                from codegate.services.reviewer_service import reviewer_service
                git_provider = get_git_provider()(pr_url)
                repo_path = getattr(git_provider, "repo_path", ".")
                reviewer_service.evaluate_and_persist(self.db, run, repo_path=repo_path)
            except Exception as e:
                logger.error(f"Reviewer recommendation failed for AnalysisRun {run.id}: {e}", exc_info=True)

            # Evaluate Quality Policy and Publish GitHub Check
            try:
                git_provider = get_git_provider()(pr_url)
                publisher = GitHubPolicyCheckPublisher(git_provider)
                quality_policy_service.evaluate_and_publish(self.db, run, publisher)
            except Exception as e:
                logger.error(f"Policy evaluation or publish failed for AnalysisRun {run.id}: {e}")

            # Complete Run
            run.status = Status.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        except Exception as e:
            logger.exception(f"AnalysisRun {run.id} failed: {str(e)}")
            self.db.rollback()
            
            # Set failed status in a new transaction context
            run.status = Status.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            self.db.add(run)
            self.db.commit()
