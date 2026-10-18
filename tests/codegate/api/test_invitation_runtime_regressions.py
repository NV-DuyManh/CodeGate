from datetime import datetime, timedelta, timezone

import pytest

from codegate.api.dependencies import get_current_user
from codegate.api.main import app
from codegate.database.models import TeamMember, User
from codegate.database.models.team import WorkspaceInvitation


@pytest.fixture
def invitation_context(client, db_session):
    invitee = User(
        provider="github", provider_user_id="runtime-invitee", username="invitee",
        email="invitee@example.com", is_active=True,
    )
    db_session.add(invitee)
    db_session.commit()
    response = client.post(
        "/api/v1/workspaces/active/invitations",
        json={"role": "DEVELOPER", "invitee_email": "invitee@example.com"},
    )
    assert response.status_code == 200
    invitation = db_session.get(WorkspaceInvitation, response.json()["id"])
    app.dependency_overrides[get_current_user] = lambda: invitee
    return response.json()["token"], invitation, invitee


def test_pending_invitation_can_be_viewed_after_sqlite_roundtrip(client, invitation_context):
    token, invitation, _ = invitation_context

    response = client.get(f"/api/v1/invitations/{token}")

    assert response.status_code == 200
    assert response.json()["id"] == invitation.id
    assert response.json()["status"] == "PENDING"


@pytest.mark.parametrize("accept", [False, True])
def test_expired_sqlite_invitation_returns_client_error(client, db_session, invitation_context, accept):
    token, invitation, _ = invitation_context
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    db_session.expire_all()

    response = client.post(f"/api/v1/invitations/{token}/accept") if accept else client.get(
        f"/api/v1/invitations/{token}"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invitation expired"


def test_pending_invitation_can_be_accepted_after_sqlite_roundtrip(client, db_session, invitation_context):
    token, invitation, invitee = invitation_context
    invitation_id = invitation.id
    invitee_id = invitee.id

    response = client.post(f"/api/v1/invitations/{token}/accept")

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(WorkspaceInvitation, invitation_id).status == "ACCEPTED"
    membership = db_session.query(TeamMember).filter_by(team_id=1, user_id=invitee_id).one()
    assert membership.role == "DEVELOPER"
    assert db_session.get(User, invitee_id).active_workspace_id == 1


@pytest.mark.parametrize("email", [None, "other@example.com"])
def test_targeted_invitation_rejects_missing_or_different_user_email(
    client, db_session, invitation_context, email
):
    token, invitation, invitee = invitation_context
    invitee.email = email
    db_session.commit()
    db_session.expire_all()

    response = client.post(f"/api/v1/invitations/{token}/accept")

    assert response.status_code == 403
    db_session.refresh(invitation)
    assert invitation.status == "PENDING"
    assert db_session.query(TeamMember).filter_by(user_id=invitee.id).count() == 0


@pytest.mark.parametrize("status", ["ACCEPTED", "REVOKED", "EXPIRED"])
@pytest.mark.parametrize("accept", [False, True])
def test_nonpending_invitation_returns_client_error_after_roundtrip(
    client, db_session, invitation_context, status, accept
):
    token, invitation, invitee = invitation_context
    invitation.status = status
    db_session.commit()
    db_session.expire_all()

    response = client.post(f"/api/v1/invitations/{token}/accept") if accept else client.get(
        f"/api/v1/invitations/{token}"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == f"Invitation is already {status.lower()}"
    assert db_session.query(TeamMember).filter_by(user_id=invitee.id).count() == 0
