from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_workspace, get_db, require_workspace_permission
from codegate.auth.permissions import Permissions
from codegate.config.settings import settings
from codegate.database.models import Team
from codegate.repositories.repo_store import repo_store
from codegate.repositories.testing_store import TestingStore
from codegate.schemas.testing import (
    CoverageReportResponse,
    TestConfigurationResponse,
    TestConfigurationUpdate,
    TestRunResponse,
)

router = APIRouter()
testing_store = TestingStore()

@router.get("/repositories/{repository_id}/test-config", response_model=TestConfigurationResponse)
def get_test_configuration(
    repository_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    """Get test runner configuration for a repository."""
    repo = repo_store.get_by_id(db, repository_id)
    if not repo or repo.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    config = testing_store.get_test_configuration(db, repository_id)
    if not config:
        # Return default mock if none exists
        config = testing_store.upsert_test_configuration(db, repository_id, {})
        db.commit()
        db.refresh(config)
        
    return config


@router.patch("/repositories/{repository_id}/test-config", response_model=TestConfigurationResponse)
def update_test_configuration(
    repository_id: int,
    config_update: TestConfigurationUpdate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.TESTING_MANAGE))
):
    """Update test runner configuration."""
    repo = repo_store.get_by_id(db, repository_id)
    if not repo or repo.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    update_data = config_update.model_dump(exclude_unset=True)
    existing = testing_store.get_test_configuration(db, repository_id)
    enabled = update_data.get("enabled", existing.enabled if existing else False)
    executor_type = update_data.get("executor_type", existing.executor_type if existing else "DISABLED")
    if enabled and (executor_type or "DISABLED").upper() == "LOCAL_TRUSTED" and not settings.ALLOW_LOCAL_TEST_EXECUTOR:
        raise HTTPException(status_code=403, detail="Local test execution is disabled by server policy")
    
    # Map special JSON fields
    if "test_paths" in update_data:
        update_data["test_paths_json"] = update_data.pop("test_paths")
    if "pytest_args" in update_data:
        update_data["pytest_args_json"] = update_data.pop("pytest_args")
    if "coverage_source" in update_data:
        update_data["coverage_source_json"] = update_data.pop("coverage_source")
        
    config = testing_store.upsert_test_configuration(db, repository_id, update_data)
    db.commit()
    db.refresh(config)
    
    return config

@router.get("/analyses/{analysis_id}/tests", response_model=TestRunResponse)
def get_test_run_for_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    """Get the test run results for a specific analysis run."""
    from codegate.repositories.analysis_store import analysis_store
    run = analysis_store.get_by_id(db, analysis_id)
    if not run or run.pull_request.repository.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")
        
    test_run = testing_store.get_test_run(db, analysis_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="No test run found for this analysis")
        
    return test_run

@router.get("/analyses/{analysis_id}/coverage", response_model=CoverageReportResponse)
def get_coverage_for_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    """Get the coverage report for a specific analysis run."""
    from codegate.repositories.analysis_store import analysis_store
    run = analysis_store.get_by_id(db, analysis_id)
    if not run or run.pull_request.repository.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")
        
    test_run = testing_store.get_test_run(db, analysis_id)
    if not test_run:
        raise HTTPException(status_code=404, detail="No test run found for this analysis")
        
    cov = testing_store.get_coverage_report(db, test_run.id)
    if not cov:
        raise HTTPException(status_code=404, detail="No coverage report found for this test run")
        
    return cov

@router.post("/analyses/{analysis_id}/tests/run", response_model=TestRunResponse)
async def trigger_tests_for_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.TESTING_MANAGE))
):
    """Manually trigger test execution for an analysis run."""
    from codegate.repositories.analysis_store import analysis_store
    from codegate.services.test_service import TestExecutionService
    
    run = analysis_store.get_by_id(db, analysis_id)
    if not run or run.pull_request.repository.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")
        
    repo = run.pull_request.repository
    
    service = TestExecutionService(testing_store, analysis_store)
    # Need async db session or handle in background, for now assume synchronous trigger blocks or is handled
    # We will just return not implemented or run it
    raise HTTPException(status_code=501, detail="Manual trigger via API is reserved for future background worker architecture.")
