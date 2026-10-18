from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_workspace, get_db, require_workspace_permission
from codegate.api.pagination import PaginationParams, get_pagination_params, paginate
from codegate.auth.permissions import Permissions
from codegate.config.settings import settings
from codegate.database.models import Provider, Team
from codegate.repositories.policy_store import quality_policy_store
from codegate.repositories.testing_store import TestingStore
from codegate.schemas.pagination import PaginatedResponse
from codegate.schemas.policy import QualityPolicyResponse, QualityPolicyUpdate
from codegate.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryUpdate
from codegate.schemas.testing import TestConfigurationResponse, TestConfigurationUpdate
from codegate.services.repository_service import repository_service

router = APIRouter(prefix="/repositories", tags=["Repositories"])

@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def create_repository(
    repo_in: RepositoryCreate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    return repository_service.create(db, repo_in, workspace.id)

@router.get("", response_model=PaginatedResponse[RepositoryResponse])
def list_repositories(
    provider: Optional[Provider] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    skip = (pagination.page - 1) * pagination.page_size
    items, total = repository_service.list(
        db, provider=provider, active=active, search=search, skip=skip, limit=pagination.page_size, workspace_id=workspace.id
    )
    return paginate(items, total, pagination)

@router.get("/{repo_id}", response_model=RepositoryResponse)
def get_repository(
    repo_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    return repository_service.get(db, repo_id, workspace.id)

@router.patch("/{repo_id}", response_model=RepositoryResponse)
def update_repository(
    repo_id: int,
    repo_in: RepositoryUpdate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    return repository_service.update(db, repo_id, repo_in, workspace.id)

@router.delete("/{repo_id}", response_model=RepositoryResponse)
def delete_repository(
    repo_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    return repository_service.delete(db, repo_id, workspace.id)

@router.get("/{repo_id}/policy", response_model=QualityPolicyResponse)
def get_repository_policy(
    repo_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    repo = repository_service.get(db, repo_id, workspace.id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    policy = quality_policy_store.get_by_repository(db, repo_id)
    if not policy:
        policy = quality_policy_store.create_default(db, repo_id)
    return policy

@router.put("/{repo_id}/policy", response_model=QualityPolicyResponse)
def update_repository_policy(
    repo_id: int,
    policy_in: QualityPolicyUpdate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(get_current_workspace)
):
    repo = repository_service.get(db, repo_id, workspace.id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    obj_in = policy_in.model_dump(exclude_unset=True)
    
    # Validation logic inside API (can be pushed to schemas but we'll do here for simplicity)
    current_policy = quality_policy_store.get_by_repository(db, repo_id) or quality_policy_store.create_default(db, repo_id)
    
    pass_t = obj_in.get('quality_pass_threshold', current_policy.quality_pass_threshold)
    block_t = obj_in.get('quality_block_threshold', current_policy.quality_block_threshold)
    if block_t > pass_t:
        raise HTTPException(status_code=422, detail="quality_block_threshold must be <= quality_pass_threshold")
        
    warn_r = obj_in.get('risk_warning_threshold', current_policy.risk_warning_threshold)
    block_r = obj_in.get('risk_block_threshold', current_policy.risk_block_threshold)
    if warn_r > block_r:
        raise HTTPException(status_code=422, detail="risk_warning_threshold must be <= risk_block_threshold")
    policy = quality_policy_store.update_policy(db, repo_id, obj_in)
    db.commit()
    return policy
@router.get("/{repo_id}/testing", response_model=TestConfigurationResponse)
def get_repository_testing(
    repo_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.TESTING_VIEW))
):
    repo = repository_service.get(db, repo_id, workspace.id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    store = TestingStore()
    config = store.get_test_configuration(db, repo_id)
    if not config:
        config = store.upsert_test_configuration(db, repo_id, {})
        db.commit()
        db.refresh(config)
    return config

@router.put("/{repo_id}/testing", response_model=TestConfigurationResponse)
def update_repository_testing(
    repo_id: int,
    config_in: TestConfigurationUpdate,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.TESTING_MANAGE))
):
    repo = repository_service.get(db, repo_id, workspace.id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    store = TestingStore()
    obj_in = config_in.model_dump(exclude_unset=True)
    existing = store.get_test_configuration(db, repo_id)
    enabled = obj_in.get("enabled", existing.enabled if existing else False)
    executor_type = obj_in.get("executor_type", existing.executor_type if existing else "DISABLED")
    if enabled and (executor_type or "DISABLED").upper() == "LOCAL_TRUSTED" and not settings.ALLOW_LOCAL_TEST_EXECUTOR:
        raise HTTPException(status_code=403, detail="Local test execution is disabled by server policy")
    for field in ("test_paths", "pytest_args", "coverage_source"):
        if field in obj_in:
            obj_in[f"{field}_json"] = obj_in.pop(field)
    config = store.upsert_test_configuration(db, repo_id, obj_in)
    db.commit()
    db.refresh(config)
    return config
