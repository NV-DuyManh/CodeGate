import hashlib
from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from codegate.auth.permissions import has_permission
from codegate.database.models import AuthSession, Team, User
from codegate.database.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Validates the codegate_session cookie and returns the active user.
    """
    session_token = request.cookies.get("codegate_session")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash)
    )

    if not auth_session:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    now = datetime.now(timezone.utc)
    expires_at = auth_session.expires_at
    # SQLite returns naive values even for DateTime(timezone=True); stored sessions use UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=401, detail="Session expired")
        
    if auth_session.revoked_at:
        raise HTTPException(status_code=401, detail="Session revoked")

    user = db.scalar(select(User).where(User.id == auth_session.user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not active or deleted")

    # Update last seen optionally (debounced to avoid db writes on every request)
    # Keeping it simple for Phase 7
    return user


def get_current_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Team:
    """
    Returns the user's active workspace, verifying they actually belong to it.
    """
    if not user.active_workspace_id:
        raise HTTPException(status_code=403, detail="No active workspace selected")
        
    # Verify membership
    from codegate.database.models import TeamMember
    member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == user.active_workspace_id)
        .where(TeamMember.user_id == user.id)
    )
    
    if not member:
        raise HTTPException(status_code=403, detail="User does not belong to the active workspace")
        
    workspace = db.scalar(select(Team).where(Team.id == user.active_workspace_id))
    if not workspace:
        raise HTTPException(status_code=403, detail="Active workspace not found")
        
    return workspace


def require_workspace_permission(permission: str):
    """
    Dependency generator that verifies the user has the required permission
    in their active workspace. Returns the active workspace Team object.
    """
    def permission_checker(
        user: User = Depends(get_current_user), 
        db: Session = Depends(get_db)
    ) -> Team:
        if not user.active_workspace_id:
            raise HTTPException(status_code=403, detail="No active workspace selected")
            
        from codegate.database.models import TeamMember
        member = db.scalar(
            select(TeamMember)
            .where(TeamMember.team_id == user.active_workspace_id)
            .where(TeamMember.user_id == user.id)
        )
        
        if not member:
            raise HTTPException(status_code=403, detail="User does not belong to the active workspace")
            
        if not has_permission(member.role, permission):
            raise HTTPException(status_code=403, detail=f"User lacks required permission: {permission}")
            
        workspace = db.scalar(select(Team).where(Team.id == user.active_workspace_id))
        if not workspace:
            raise HTTPException(status_code=403, detail="Active workspace not found")
            
        return workspace
        
    return permission_checker
