import asyncio
import logging
from datetime import datetime, timezone

from celery import Task
from celery.exceptions import Retry

from codegate.database.models.analysis import AnalysisJob, AnalysisRun, Status
from codegate.database.models.pull_request import PullRequest
from codegate.database.session import SessionLocal
from codegate.services.analysis_orchestrator import AnalysisOrchestrator

from .celery_app import celery_app

logger = logging.getLogger(__name__)

class CodeGateBaseTask(Task):
    """
    Base task that manages DB sessions.
    """
    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if self._db is not None:
            self._db.close()
            self._db = None

@celery_app.task(bind=True, base=CodeGateBaseTask, max_retries=3, default_retry_delay=60)
def analyze_pull_request(self, analysis_run_id: int):
    """
    Celery task that orchestrates the PR analysis.
    """
    logger.info(f"Starting analysis task for run {analysis_run_id}")
    db = self.db

    # 1. Load job and run
    job = db.query(AnalysisJob).filter_by(analysis_run_id=analysis_run_id).first()
    run = db.query(AnalysisRun).filter_by(id=analysis_run_id).first()

    if not job or not run:
        logger.error(f"AnalysisRun or AnalysisJob not found for id {analysis_run_id}")
        return

    # Update job state
    job.celery_task_id = self.request.id
    job.status = "RUNNING"
    job.started_at = datetime.now(timezone.utc)
    job.attempt_count += 1
    
    # If run is already in a terminal state, don't run it again
    if run.status in [Status.COMPLETED, Status.FAILED]:
        job.status = "SKIPPED"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Analysis run {analysis_run_id} is already in state {run.status}. Skipping.")
        return

    pr = db.query(PullRequest).filter_by(id=run.pull_request_id).first()
    if not pr:
        job.status = "FAILED"
        job.last_error = "PullRequest not found"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        return

    # 2. Check Stale Job Protection
    # If the PR has been updated with a new head_sha, this job is stale.
    if pr.head_sha != run.head_sha:
        logger.info(f"Stale job protection triggered for run {analysis_run_id}. PR head {pr.head_sha} != Run head {run.head_sha}")
        job.status = "SKIPPED"
        job.finished_at = datetime.now(timezone.utc)
        run.status = Status.SKIPPED
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    db.commit()

    try:
        # Publish initial check status to GitHub (Queued/In Progress)
        try:
            # We construct pr_url from the DB info. But wait, we need the exact URL for the git provider.
            repo_full_name = pr.repository.full_name
            pr_url = f"https://github.com/{repo_full_name}/pull/{pr.number}"
            # It's better if `_execute_run` handles the Check publication natively or we do it here.
            # AnalysisOrchestrator publishes check upon completion.
        except Exception as e:
            logger.warning(f"Failed to resolve PR URL for run {analysis_run_id}: {e}")
            pr_url = pr.repository.url + f"/pull/{pr.number}" if pr.repository else ""

        if not pr_url:
            raise ValueError("Could not determine PR URL")

        # Inject settings for PR-Agent
        from codegate.config.settings import settings as cg_settings
        from pr_agent.config_loader import get_settings
        get_settings().set("GITHUB.DEPLOYMENT_TYPE", "app")
        get_settings().set("GITHUB.APP_ID", cg_settings.GITHUB_APP_ID)
        if cg_settings.GITHUB_APP_PRIVATE_KEY_PATH:
            with open(cg_settings.GITHUB_APP_PRIVATE_KEY_PATH, 'r') as f:
                get_settings().set("GITHUB.PRIVATE_KEY", f.read())
        
        # Get installation ID from the repository's connection
        if pr.repository and pr.repository.github_connection:
            installation_id = pr.repository.github_connection.installation_id
            get_settings().set("GITHUB.INSTALLATION_ID", int(installation_id))

        # 3. Execute Analysis
        orchestrator = AnalysisOrchestrator(db)
        # A synchronous Celery task owns and closes its event loop for each invocation.
        asyncio.run(orchestrator._execute_run(run, pr_url))

        # Check the run status after execution
        db.refresh(run)
        
        job.status = "SUCCEEDED" if run.status == Status.COMPLETED else "FAILED"
        if run.status == Status.FAILED:
            job.last_error = run.error_message
            
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Finished analysis task for run {analysis_run_id} with status {job.status}")

    except Exception as exc:
        logger.exception(f"Exception during analysis task for run {analysis_run_id}")
        db.rollback()
        
        # Determine if we should retry
        # For now, let's just log and fail, or retry on generic exceptions.
        # PR-Agent can throw rate limit exceptions.
        error_msg = str(exc)
        if "rate limit" in error_msg.lower() or "timeout" in error_msg.lower():
            logger.info("Transient error detected, retrying...")
            try:
                self.retry(exc=exc)
            except Retry:
                # Retry was successfully scheduled
                raise
        
        # Terminal failure
        job = db.query(AnalysisJob).filter_by(analysis_run_id=analysis_run_id).first()
        run = db.query(AnalysisRun).filter_by(id=analysis_run_id).first()
        if job:
            job.status = "FAILED"
            job.last_error = error_msg
            job.finished_at = datetime.now(timezone.utc)
        if run:
            run.status = Status.FAILED
            run.error_message = error_msg
            run.completed_at = datetime.now(timezone.utc)
        db.commit()
