from enum import Enum
from typing import Dict, List, Set

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from codegate.database.models import TeamMember
from codegate.database.models.team import Role


class Permissions(str, Enum):
    # Workspace
    WORKSPACE_VIEW = "workspace.view"
    WORKSPACE_UPDATE = "workspace.update"
    
    # Members
    MEMBERS_VIEW = "members.view"
    MEMBERS_INVITE = "members.invite"
    MEMBERS_ROLE_CHANGE = "members.role_change"
    MEMBERS_REMOVE = "members.remove"
    
    # GitHub Integration
    GITHUB_VIEW = "github.view"
    GITHUB_CONNECT = "github.connect"
    GITHUB_VERIFY = "github.verify"
    GITHUB_DISCONNECT = "github.disconnect"
    GITHUB_SYNC = "github.sync"
    
    # Repositories & Analysis
    REPOSITORY_VIEW = "repository.view"
    ANALYSIS_VIEW = "analysis.view"
    ANALYSIS_RETRY = "analysis.retry"
    
    # Policy
    POLICY_VIEW = "policy.view"
    POLICY_MANAGE = "policy.manage"
    
    # Testing
    TESTING_VIEW = "testing.view"
    TESTING_MANAGE = "testing.manage"
    
    # Other
    REVIEWER_VIEW = "reviewer.view"
    DASHBOARD_VIEW = "dashboard.view"
    ANALYTICS_VIEW = "analytics.view"


# Role to Permissions Matrix
ROLE_PERMISSIONS: Dict[Role, Set[Permissions]] = {
    Role.ADMIN: {
        Permissions.WORKSPACE_VIEW,
        Permissions.WORKSPACE_UPDATE,
        Permissions.MEMBERS_VIEW,
        Permissions.MEMBERS_INVITE,
        Permissions.MEMBERS_ROLE_CHANGE,
        Permissions.MEMBERS_REMOVE,
        Permissions.GITHUB_VIEW,
        Permissions.GITHUB_CONNECT,
        Permissions.GITHUB_VERIFY,
        Permissions.GITHUB_DISCONNECT,
        Permissions.GITHUB_SYNC,
        Permissions.REPOSITORY_VIEW,
        Permissions.ANALYSIS_VIEW,
        Permissions.ANALYSIS_RETRY,
        Permissions.POLICY_VIEW,
        Permissions.POLICY_MANAGE,
        Permissions.TESTING_VIEW,
        Permissions.TESTING_MANAGE,
        Permissions.REVIEWER_VIEW,
        Permissions.DASHBOARD_VIEW,
        Permissions.ANALYTICS_VIEW,
    },
    Role.MAINTAINER: {
        Permissions.WORKSPACE_VIEW,
        Permissions.MEMBERS_VIEW,
        Permissions.MEMBERS_INVITE,
        Permissions.GITHUB_VIEW,
        Permissions.GITHUB_VERIFY,
        Permissions.GITHUB_SYNC,
        Permissions.REPOSITORY_VIEW,
        Permissions.ANALYSIS_VIEW,
        Permissions.ANALYSIS_RETRY,
        Permissions.POLICY_VIEW,
        Permissions.POLICY_MANAGE,
        Permissions.TESTING_VIEW,
        Permissions.TESTING_MANAGE,
        Permissions.REVIEWER_VIEW,
        Permissions.DASHBOARD_VIEW,
        Permissions.ANALYTICS_VIEW,
    },
    Role.REVIEWER: {
        Permissions.WORKSPACE_VIEW,
        Permissions.MEMBERS_VIEW,
        Permissions.REPOSITORY_VIEW,
        Permissions.ANALYSIS_VIEW,
        Permissions.REVIEWER_VIEW,
        Permissions.DASHBOARD_VIEW,
        Permissions.ANALYTICS_VIEW,
        Permissions.POLICY_VIEW,
        Permissions.TESTING_VIEW,
    },
    Role.DEVELOPER: {
        Permissions.WORKSPACE_VIEW,
        Permissions.REPOSITORY_VIEW,
        Permissions.ANALYSIS_VIEW,
        Permissions.DASHBOARD_VIEW,
        Permissions.TESTING_VIEW,
    }
}


def has_permission(role: Role, permission: str) -> bool:
    """Check if a specific role has a permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def check_last_admin(db: Session, workspace_id: int, target_user_id: int) -> None:
    """
    Checks if the target_user_id is the last ADMIN in the workspace.
    Raises an HTTPException if they are, preventing removal or demotion.
    """
    # Check if target user is an admin
    target_member = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace_id)
        .where(TeamMember.user_id == target_user_id)
    )
    
    if not target_member or target_member.role != Role.ADMIN:
        return # They aren't an admin, so demoting/removing them is fine
        
    # Count how many admins there are
    admin_count = db.scalar(
        select(TeamMember)
        .where(TeamMember.team_id == workspace_id)
        .where(TeamMember.role == Role.ADMIN)
        .with_only_columns(TeamMember.id)
    )
    
    # We actually need a count scalar query
    from sqlalchemy import func
    admin_count = db.scalar(
        select(func.count(TeamMember.id))
        .where(TeamMember.team_id == workspace_id)
        .where(TeamMember.role == Role.ADMIN)
    )
    
    if admin_count <= 1:
        raise HTTPException(
            status_code=403, 
            detail="Cannot perform this action: user is the last ADMIN in the workspace."
        )


def can_grant_role(actor_role: Role, target_role: Role) -> bool:
    """Check if the actor_role is authorized to grant the target_role."""
    if actor_role == Role.ADMIN:
        return True
    
    if actor_role == Role.MAINTAINER:
        # Maintainer can invite/grant roles up to Maintainer, but NOT Admin
        return target_role in {Role.MAINTAINER, Role.REVIEWER, Role.DEVELOPER}
        
    return False
