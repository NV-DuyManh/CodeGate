from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_workspace, get_db, require_workspace_permission
from codegate.api.pagination import PaginationParams, get_pagination_params, paginate
from codegate.auth.permissions import Permissions
from codegate.database.models import Team
from codegate.repositories.policy_store import policy_evaluation_store
from codegate.schemas.analysis import AnalysisRunCreate, AnalysisRunResponse, CodeMetricResponse
from codegate.schemas.pagination import PaginatedResponse
from codegate.schemas.policy import PolicyEvaluationResponse
from codegate.schemas.quality import QualityScoreResponse
from codegate.schemas.risk import RiskScoreResponse
from codegate.services.analysis_service import analysis_service
from codegate.services.policy_service import quality_policy_service
from codegate.services.quality_service import quality_service
from codegate.services.risk_service import risk_service

router = APIRouter(tags=["Analyses"])

@router.post("/pull-requests/{pr_id}/analyses", response_model=AnalysisRunResponse, status_code=status.HTTP_201_CREATED)
def create_manual_analysis(
    pr_id: int,
    analysis_in: AnalysisRunCreate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_RETRY))
):
    return analysis_service.create(db, pr_id, analysis_in, workspace.id)

@router.get("/pull-requests/{pr_id}/analyses", response_model=PaginatedResponse[AnalysisRunResponse])
def list_analyses_for_pr(
    pr_id: int,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_VIEW))
):
    skip = (pagination.page - 1) * pagination.page_size
    items, total = analysis_service.list_by_pr(
        db, pr_id=pr_id, skip=skip, limit=pagination.page_size, workspace_id=workspace.id
    )
    return paginate(items, total, pagination)

@router.get("/analyses/{analysis_id}", response_model=AnalysisRunResponse)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_VIEW))
):
    return analysis_service.get(db, analysis_id, workspace.id)

@router.get("/analyses/{analysis_id}/metrics", response_model=PaginatedResponse[CodeMetricResponse])
def list_analysis_metrics(
    analysis_id: int,
    analyzer: Optional[str] = Query(None, description="Filter by analyzer name"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    file_path: Optional[str] = Query(None, description="Filter by file path"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_VIEW))
):
    skip = (pagination.page - 1) * pagination.page_size
    items, total = analysis_service.list_metrics(
        db, analysis_id=analysis_id, skip=skip, limit=pagination.page_size,
        analyzer=analyzer, metric_name=metric_name, file_path=file_path, workspace_id=workspace.id
    )
    return paginate(items, total, pagination)

@router.get("/analyses/{analysis_id}/quality", response_model=QualityScoreResponse)
def get_analysis_quality(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_VIEW))
):
    """Retrieve the latest quality score for an analysis run"""
    return quality_service.get_quality(db, analysis_id, workspace.id)

@router.post("/analyses/{analysis_id}/quality/recalculate", response_model=QualityScoreResponse)
def recalculate_analysis_quality(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_RETRY))
):
    """Recalculate the quality score for an analysis run"""
    return quality_service.recalculate(db, analysis_id, workspace.id)

@router.get("/analyses/{analysis_id}/risk", response_model=RiskScoreResponse)
def get_analysis_risk(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_VIEW))
):
    """Retrieve the latest risk score for an analysis run"""
    return risk_service.get_risk(db, analysis_id, workspace.id)

@router.post("/analyses/{analysis_id}/risk/recalculate", response_model=RiskScoreResponse)
def recalculate_analysis_risk(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_RETRY))
):
    """Recalculate the risk score for an analysis run"""
    return risk_service.recalculate(db, analysis_id, workspace.id)

@router.get("/analyses/{analysis_id}/policy", response_model=PolicyEvaluationResponse)
def get_analysis_policy(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.POLICY_VIEW))
):
    """Retrieve the latest policy evaluation for an analysis run"""
    # First verify we own this analysis run
    analysis_service.get(db, analysis_id, workspace.id)
    evaluation = policy_evaluation_store.get_latest_for_analysis(db, analysis_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Policy evaluation not found")
    return evaluation

@router.post("/analyses/{analysis_id}/policy/evaluate", response_model=PolicyEvaluationResponse)
def evaluate_analysis_policy(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.POLICY_MANAGE))
):
    """Recalculate policy evaluation for an analysis run"""
    analysis = analysis_service.get(db, analysis_id, workspace.id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    # Using None publisher here for manual recalculation so we don't spam checks,
    # or we can pass a dummy publisher. The prompt requires evaluating using current policy.
    # The default is publisher=None
    return quality_policy_service.evaluate_and_publish(db, analysis)

@router.post("/analyses/{analysis_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.ANALYSIS_RETRY))
):
    """Manually retry a failed or skipped analysis"""
    from codegate.database.models.analysis import AnalysisJob, AnalysisRun, Status
    from codegate.worker.tasks import analyze_pull_request
    
    analysis = analysis_service.get(db, analysis_id, workspace.id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
        
    run = db.query(AnalysisRun).filter_by(id=analysis_id).first()
    if run.status in [Status.PENDING, Status.QUEUED, Status.RUNNING]:
        raise HTTPException(status_code=400, detail=f"Analysis is currently {run.status.name}")

    # Reset states for retry
    run.status = Status.QUEUED
    run.error_message = None
    
    job = db.query(AnalysisJob).filter_by(analysis_run_id=analysis_id).first()
    if not job:
        job = AnalysisJob(analysis_run_id=analysis_id)
        db.add(job)
        
    job.status = "QUEUED"
    job.queued_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.commit()
    
    # Enqueue task
    analyze_pull_request.delay(analysis_id)
    
    return {"status": "retry_accepted"}
