import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from codegate.api.dependencies import get_current_user, get_db, require_workspace_permission
from codegate.auth.permissions import Permissions, can_grant_role, check_last_admin
from codegate.database.models import Team, User
from codegate.database.models.team import InvitationStatus, Role, TeamMember, WorkspaceInvitation

router = APIRouter(prefix="/api/v1", tags=["Members & Invitations"])


class MemberResponse(BaseModel):
    user_id: int
    github_login: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    role: Role
    joined_at: datetime
    
    class Config:
        from_attributes = True

class InvitationCreate(BaseModel):
    role: Role
    invitee_github_login: Optional[str] = None
    invitee_email: Optional[EmailStr] = None

class InvitationResponse(BaseModel):
    id: int
    team_name: str
    inviter_name: str
    role: Role
    invitee_github_login: Optional[str]
    invitee_email: Optional[str]
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    
    # We only return the raw token when it's initially created
    token: Optional[str] = None

    class Config:
        from_attributes = True


class MembersListResponse(BaseModel):
    members: List[MemberResponse]
    invitations: List[InvitationResponse]


class RoleUpdateRequest(BaseModel):
    role: Role


@router.get("/workspaces/active/members", response_model=MembersListResponse)
def get_workspace_members(
    workspace: Team = Depends(require_workspace_permission(Permissions.MEMBERS_VIEW)),
    db: Session = Depends(get_db)
):
    """List all members and pending invitations in the active workspace."""
    # Members
    members_db = db.execute(
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == workspace.id)
    ).all()
    
    members = [
        MemberResponse(
            user_id=user.id,
            github_login=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            role=tm.role,
            joined_at=tm.created_at
        )
        for tm, user in members_db
    ]
    
    # Invitations
    invites_db = db.scalars(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.team_id == workspace.id)
        .where(WorkspaceInvitation.status == InvitationStatus.PENDING)
    ).all()
    
    invitations = [
        InvitationResponse(
            id=inv.id,
            team_name=workspace.name,
            inviter_name=inv.inviter.display_name or inv.inviter.username,
            role=inv.role,
            invitee_github_login=inv.invitee_github_login,
            invitee_email=inv.invitee_email,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            token=None
        )
        for inv in invites_db
    ]
    
    return MembersListResponse(members=members, invitations=invitations)


@router.post("/workspaces/active/invitations", response_model=InvitationResponse)
def create_invitation(
    request: InvitationCreate,
    user: User = Depends(get_current_user),
    workspace: Team = Depends(require_workspace_permission(Permissions.MEMBERS_INVITE)),
    db: Session = Depends(get_db)
):
    """Create a new workspace invitation (Admin only)."""
    # Verify the current user is an Admin (per Phase 12 req: Admin only invite)
    # The dependency already checks MEMBERS_INVITE, but we can be extra safe.
    
    # Generate token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    
    # Get actor member to check grant authorization
    actor_member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace.id)
        .where(TeamMember.user_id == user.id)
    )
    if not actor_member or not can_grant_role(actor_member.role, request.role):
        raise HTTPException(status_code=403, detail="Not authorized to grant this role")
        
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    # Check if target is already a member (if github login provided)
    if request.invitee_github_login:
        existing_member = db.execute(
            select(TeamMember)
            .join(User, TeamMember.user_id == User.id)
            .where(TeamMember.team_id == workspace.id)
            .where(User.username == request.invitee_github_login)
        ).first()
        
        if existing_member:
            raise HTTPException(status_code=400, detail="User is already a member of this workspace")
    
    invitation = WorkspaceInvitation(
        team_id=workspace.id,
        inviter_user_id=user.id,
        role=request.role,
        invitee_github_login=request.invitee_github_login,
        invitee_email=request.invitee_email,
        token_hash=token_hash,
        status=InvitationStatus.PENDING,
        expires_at=expires_at
    )
    
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    
    response = InvitationResponse(
        id=invitation.id,
        team_name=workspace.name,
        inviter_name=user.display_name or user.username,
        role=invitation.role,
        invitee_github_login=invitation.invitee_github_login,
        invitee_email=invitation.invitee_email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=raw_token
    )
    return response


@router.delete("/workspaces/active/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: int,
    workspace: Team = Depends(require_workspace_permission(Permissions.MEMBERS_INVITE)),
    db: Session = Depends(get_db)
):
    """Revoke a pending invitation."""
    invitation = db.scalar(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.id == invitation_id)
        .where(WorkspaceInvitation.team_id == workspace.id)
    )
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
        
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending invitations can be revoked")
        
    invitation.status = InvitationStatus.REVOKED
    invitation.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.get("/invitations/{token}", response_model=InvitationResponse)
def get_invitation(token: str, db: Session = Depends(get_db)):
    """View invite details safely (does not require login)."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    invitation = db.scalar(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.token_hash == token_hash)
    )
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid invitation token")
        
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")
        
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Invitation is already {invitation.status.lower()}")
        
    return InvitationResponse(
        id=invitation.id,
        team_name=invitation.team.name,
        inviter_name=invitation.inviter.display_name or invitation.inviter.username,
        role=invitation.role,
        invitee_github_login=invitation.invitee_github_login,
        invitee_email=invitation.invitee_email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at
    )


@router.post("/invitations/{token}/accept")
def accept_invitation(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept an invitation (Requires Auth)."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    invitation = db.scalar(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.token_hash == token_hash)
    )
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid invitation token")
        
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")
        
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Invitation is already {invitation.status.lower()}")
        
    # Enforce strict github login match if target was specified
    if invitation.invitee_github_login and invitation.invitee_github_login.lower() != user.username.lower():
        raise HTTPException(status_code=403, detail="This invitation was sent to a different GitHub account")
        
    # Enforce strict email match if target was specified
    if invitation.invitee_email and (not user.email or invitation.invitee_email.lower() != user.email.lower()):
        raise HTTPException(status_code=403, detail="This invitation was sent to a different email account")
        
    # Check if already a member
    existing_member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == invitation.team_id)
        .where(TeamMember.user_id == user.id)
    )
    
    if existing_member:
        raise HTTPException(status_code=400, detail="Already a member of this workspace")
        
    # Create TeamMember
    member = TeamMember(
        team_id=invitation.team_id,
        user_id=user.id,
        role=invitation.role
    )
    db.add(member)
    
    # Mark invitation as accepted
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    
    # Switch active workspace
    user.active_workspace_id = invitation.team_id
    
    db.commit()
    return {"status": "ok", "workspace_id": invitation.team_id}


@router.patch("/workspaces/active/members/{user_id}")
def update_member_role(
    user_id: int,
    request: RoleUpdateRequest,
    user: User = Depends(get_current_user),
    workspace: Team = Depends(require_workspace_permission(Permissions.MEMBERS_ROLE_CHANGE)),
    db: Session = Depends(get_db)
):
    """Change member role (with Last-Admin check)."""
    # Get actor member to check grant authorization
    actor_member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace.id)
        .where(TeamMember.user_id == user.id)
    )
    if not actor_member or not can_grant_role(actor_member.role, request.role):
        raise HTTPException(status_code=403, detail="Not authorized to grant this role")

    # If they are demoting an Admin, ensure they aren't the last one
    if request.role != Role.ADMIN:
        check_last_admin(db, workspace.id, user_id)
        
    member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace.id)
        .where(TeamMember.user_id == user_id)
    )
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    member.role = request.role
    db.commit()
    return {"status": "ok"}


@router.delete("/workspaces/active/members/{user_id}")
def remove_member(
    user_id: int,
    workspace: Team = Depends(require_workspace_permission(Permissions.MEMBERS_REMOVE)),
    db: Session = Depends(get_db)
):
    """Remove member (with Last-Admin check)."""
    check_last_admin(db, workspace.id, user_id)
    
    member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace.id)
        .where(TeamMember.user_id == user_id)
    )
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    db.delete(member)
    db.commit()
    return {"status": "ok"}
