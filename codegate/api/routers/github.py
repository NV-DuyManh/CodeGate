import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_user, get_db, require_workspace_permission
from codegate.auth.permissions import Permissions
from codegate.config.settings import settings
from codegate.database.models import Team, User
from codegate.database.models.github import GitHubConnection, GitHubInstallationState
from codegate.database.session import SessionLocal
from codegate.services.github_app import GitHubAppService
from codegate.services.github_sync_service import GithubSyncService

router = APIRouter(prefix="/integrations/github", tags=["GitHub Integration"])

async def background_sync(connection_id: int):
    with SessionLocal() as db:
        service = GithubSyncService(db)
        try:
            await service.sync_repositories(connection_id)
        except Exception as e:
            # Errors are already logged in sync_repositories
            pass


@router.get("/install")
def install_github_app(
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_CONNECT)),
    user: User = Depends(get_current_user)
):
    if not settings.GITHUB_APP_SLUG:
        raise HTTPException(status_code=500, detail="GitHub App is not configured on this server.")

    # Generate secure random state
    state_token = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state_token.encode()).hexdigest()

    # Store state
    state = GitHubInstallationState(
        state_hash=state_hash,
        user_id=user.id,
        workspace_id=workspace.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    db.add(state)
    db.commit()

    install_url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={state_token}"
    
    return {"install_url": install_url}


@router.get("/setup")
async def setup_github_callback(
    installation_id: str,
    setup_action: str,
    background_tasks: BackgroundTasks,
    state: str = Query(..., description="State token from installation"),
    db: Session = Depends(get_db)
):
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    
    state_record = db.scalar(
        select(GitHubInstallationState)
        .where(GitHubInstallationState.state_hash == state_hash)
    )

    if not state_record:
        raise HTTPException(status_code=400, detail="Invalid installation state.")
    
    now = datetime.now(timezone.utc)
    # Handle naive datetime mapping in SQLite/SQLAlchemy sometimes lacking timezone info
    if state_record.expires_at.tzinfo is None:
        state_record.expires_at = state_record.expires_at.replace(tzinfo=timezone.utc)
        
    if state_record.expires_at < now:
        raise HTTPException(status_code=400, detail="Installation state has expired.")
        
    if state_record.consumed_at:
        raise HTTPException(status_code=400, detail="Installation state has already been consumed.")
        
    # Mark as consumed
    state_record.consumed_at = now
    db.commit()

    # Verify installation via GitHub App API
    github_service = GitHubAppService()
    try:
        installation_data = await github_service.get_installation(installation_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    account_login = installation_data.get("account", {}).get("login", "unknown")
    account_type = installation_data.get("account", {}).get("type", "unknown")
    repository_selection = installation_data.get("repository_selection", "all")

    # Check for existing connection in ANY workspace
    existing_conn = db.scalar(
        select(GitHubConnection)
        .where(GitHubConnection.provider == "github")
        .where(GitHubConnection.installation_id == str(installation_id))
    )

    if existing_conn:
        if existing_conn.workspace_id != state_record.workspace_id:
            # Cross-workspace installation collision
            raise HTTPException(status_code=400, detail="This GitHub installation is already connected to another workspace.")
        
        # Idempotent reconnect - update metadata
        existing_conn.account_login = account_login
        existing_conn.account_type = account_type
        existing_conn.repository_selection = repository_selection
        existing_conn.status = "active"
        existing_conn.last_verified_at = now
    else:
        # Create new connection
        new_conn = GitHubConnection(
            provider="github",
            account_login=account_login,
            account_type=account_type,
            auth_type="app",
            status="active",
            installation_id=str(installation_id),
            workspace_id=state_record.workspace_id,
            repository_selection=repository_selection,
            last_verified_at=now
        )
        db.add(new_conn)
        
    db.commit()
    db.refresh(existing_conn if existing_conn else new_conn)
    conn_id = existing_conn.id if existing_conn else new_conn.id
    
    # Trigger auto-sync
    background_tasks.add_task(background_sync, conn_id)
    
    # Redirect to frontend
    redirect_url = f"{settings.CODEGATE_FRONTEND_URL}/integrations?github=connected"
    return RedirectResponse(url=redirect_url)


@router.get("/connections")
def get_github_connections(db: Session = Depends(get_db), workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_VIEW))):
    connections = db.scalars(select(GitHubConnection).where(GitHubConnection.workspace_id == workspace.id)).all()
    return [{
        "id": c.id, 
        "account_login": c.account_login, 
        "account_type": c.account_type,
        "status": c.status, 
        "auth_type": c.auth_type,
        "repository_selection": c.repository_selection,
        "last_sync_status": c.last_sync_status,
        "last_sync_error": c.last_sync_error,
        "last_synced_at": c.last_synced_at,
        "installation_id": c.installation_id,
        "last_verified_at": c.last_verified_at
    } for c in connections]


@router.post("/connections/{conn_id}/sync")
async def sync_github_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_SYNC))
):
    connection = db.scalar(
        select(GitHubConnection)
        .where(GitHubConnection.id == conn_id)
        .where(GitHubConnection.workspace_id == workspace.id)
    )
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    service = GithubSyncService(db)
    try:
        summary = await service.sync_repositories(conn_id)
        return summary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Sync failed: " + str(e))


@router.post("/connections/{connection_id}/verify")
async def verify_github_connection(connection_id: int, db: Session = Depends(get_db), workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_VERIFY))):
    conn = db.get(GitHubConnection, connection_id)
    if not conn or conn.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    if conn.auth_type != "app" or not conn.installation_id:
        raise HTTPException(status_code=400, detail="Cannot dynamically verify non-app connection")
        
    github_service = GitHubAppService()
    try:
        installation_data = await github_service.get_installation(conn.installation_id)
        
        conn.account_login = installation_data.get("account", {}).get("login", conn.account_login)
        conn.account_type = installation_data.get("account", {}).get("type", conn.account_type)
        conn.repository_selection = installation_data.get("repository_selection", conn.repository_selection)
        
        # If suspended
        if installation_data.get("suspended_at"):
            conn.status = "suspended"
        else:
            conn.status = "active"
            
        conn.last_verified_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "success", "message": "Connection verified successfully", "connection_status": conn.status}
    except HTTPException as e:
        if e.status_code == 400:
             conn.status = "invalid"
             db.commit()
        raise e


@router.post("/connections/{connection_id}/disconnect")
def disconnect_github(connection_id: int, db: Session = Depends(get_db), workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_DISCONNECT))):
    conn = db.get(GitHubConnection, connection_id)
    if not conn or conn.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn.status = "disconnected"
    db.commit()
    return {"status": "success", "message": "Connection disconnected successfully"}


@router.get("/connections/{connection_id}/repositories")
def get_available_repositories(connection_id: int, db: Session = Depends(get_db), workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_VIEW))):
    conn = db.get(GitHubConnection, connection_id)
    if not conn or conn.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Mocking available repositories for the demo flow
    return [
        {"id": 101, "name": "backend", "full_name": f"{conn.account_login}/backend", "private": True},
        {"id": 102, "name": "frontend", "full_name": f"{conn.account_login}/frontend", "private": False}
    ]


class ImportRepositoryRequest(BaseModel):
    full_name: str
    
@router.post("/connections/{connection_id}/import")
def import_repository(connection_id: int, request: ImportRepositoryRequest, db: Session = Depends(get_db), workspace: Team = Depends(require_workspace_permission(Permissions.GITHUB_SYNC))):
    conn = db.get(GitHubConnection, connection_id)
    if not conn or conn.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "success", "message": f"Repository {request.full_name} imported"}
