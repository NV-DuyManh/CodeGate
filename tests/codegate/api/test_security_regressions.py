import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from codegate.api.dependencies import get_current_user, require_workspace_permission
from codegate.api.routers import auth, webhooks
from codegate.auth.permissions import Permissions
from codegate.config.settings import CodeGateSettings, settings
from codegate.database.models import AuthSession, Repository, TeamMember, User
from codegate.database.models.team import Role
from codegate.database.models.testing import TestConfiguration as DBTestConfiguration
from codegate.database.models.webhook import WebhookEvent
from codegate.services.github_auth import GitHubUser


@pytest.mark.parametrize("expired", [False, True])
def test_sqlite_session_expiration_handles_timezone_loss(db_session, expired):
    user = User(provider="github", provider_user_id="session-user", username="session-user", is_active=True)
    db_session.add(user)
    db_session.flush()
    user_id = user.id
    db_session.add(AuthSession(
        user_id=user_id,
        token_hash=hashlib.sha256(b"test-session").hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=-1 if expired else 1),
    ))
    db_session.commit()
    db_session.expire_all()
    request = Request({"type": "http", "headers": [(b"cookie", b"codegate_session=test-session")]})

    if expired:
        with pytest.raises(HTTPException) as error:
            get_current_user(request, db_session)
        assert error.value.status_code == 401
    else:
        assert get_current_user(request, db_session).id == user_id


def test_webhook_secret_loads_documented_environment_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    configured = CodeGateSettings(_env_file=None)
    assert getattr(configured, "GITHUB_WEBHOOK_SECRET", None) == "test-webhook-secret"


@pytest.mark.parametrize("secret,signature,status", [
    (None, None, 503),
    ("", None, 503),
    ("test-webhook-secret", None, 401),
    ("test-webhook-secret", "sha256=invalid", 401),
    ("test-webhook-secret", "valid", 202),
])
def test_webhook_requires_configured_secret_and_valid_signature(
    client, db_session, monkeypatch, secret, signature, status
):
    monkeypatch.setitem(settings.__dict__, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(webhooks, "get_settings", lambda: SimpleNamespace(github=SimpleNamespace(webhook_secret=None)))
    body = json.dumps({"action": "ping"}).encode()
    headers = {"X-GitHub-Event": "ping", "X-GitHub-Delivery": "security-delivery"}
    if signature == "valid":
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if signature:
        headers["X-Hub-Signature-256"] = signature

    response = client.post("/api/v1/github_webhooks", content=body, headers=headers)

    assert response.status_code == status
    assert db_session.query(WebhookEvent).count() == (1 if status == 202 else 0)


@pytest.fixture
def security_repository(client, db_session):
    repository = Repository(
        provider="GITHUB", owner="security", name="repo", full_name="security/repo",
        url="https://github.com/security/repo", workspace_id=1,
    )
    db_session.add(repository)
    db_session.commit()
    return repository


@pytest.mark.parametrize("role", [Role.DEVELOPER, Role.REVIEWER])
@pytest.mark.parametrize("method,suffix", [("PATCH", "test-config"), ("PUT", "testing")])
def test_test_configuration_requires_manage_permission(client, db_session, security_repository, role, method, suffix):
    member = db_session.query(TeamMember).filter_by(team_id=1, user_id=1).one()
    member.role = role
    db_session.commit()

    response = client.request(
        method, f"/api/v1/repositories/{security_repository.id}/{suffix}", json={"enabled": True}
    )

    assert response.status_code == 403


def test_testing_environment_does_not_bypass_permissions(client, db_session, monkeypatch):
    member = db_session.query(TeamMember).filter_by(team_id=1, user_id=1).one()
    member.role = Role.DEVELOPER
    db_session.commit()
    monkeypatch.setenv("TESTING", "1")
    checker = require_workspace_permission(Permissions.TESTING_MANAGE)

    with pytest.raises(HTTPException) as error:
        checker(user=db_session.get(User, 1), db=db_session)

    assert error.value.status_code == 403


def test_manual_test_trigger_requires_manage_permission(client, db_session):
    member = db_session.query(TeamMember).filter_by(team_id=1, user_id=1).one()
    member.role = Role.DEVELOPER
    db_session.commit()

    response = client.post("/api/v1/analyses/999/tests/run")

    assert response.status_code == 403


@pytest.mark.parametrize("allowed,status", [(False, 403), (True, 200)])
@pytest.mark.parametrize("method,suffix", [("PATCH", "test-config"), ("PUT", "testing")])
def test_local_executor_requires_server_opt_in(client, monkeypatch, security_repository, allowed, status, method, suffix):
    monkeypatch.setitem(settings.__dict__, "ALLOW_LOCAL_TEST_EXECUTOR", allowed)

    response = client.request(
        method, f"/api/v1/repositories/{security_repository.id}/{suffix}",
        json={"enabled": True, "executor_type": "LOCAL_TRUSTED"},
    )

    assert response.status_code == status


@pytest.mark.parametrize("method,suffix", [("PATCH", "test-config"), ("PUT", "testing")])
def test_updated_test_configuration_is_committed(client, db_session, security_repository, method, suffix):
    repository_id = security_repository.id

    response = client.request(
        method, f"/api/v1/repositories/{repository_id}/{suffix}",
        json={"enabled": True, "executor_type": "DOCKER", "test_paths": ["tests/unit"]},
    )
    assert response.status_code == 200
    db_session.rollback()

    configuration = db_session.query(DBTestConfiguration).filter_by(repository_id=repository_id).one_or_none()
    assert configuration is not None
    assert configuration.enabled is True
    assert configuration.test_paths_json == ["tests/unit"]


@pytest.mark.parametrize("method,suffix", [("PATCH", "test-config"), ("PUT", "testing")])
def test_partial_update_cannot_enable_existing_local_executor(client, monkeypatch, security_repository, method, suffix):
    monkeypatch.setitem(settings.__dict__, "ALLOW_LOCAL_TEST_EXECUTOR", False)
    url = f"/api/v1/repositories/{security_repository.id}/{suffix}"
    disabled_response = client.request(method, url, json={"enabled": False, "executor_type": "LOCAL_TRUSTED"})
    assert disabled_response.status_code == 200

    response = client.request(method, url, json={"enabled": True})

    assert response.status_code == 403


def test_oauth_callback_redirects_to_configured_frontend(client, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "GITHUB_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "CODEGATE_FRONTEND_URL", "https://dashboard.example.test")
    monkeypatch.setattr(auth, "get_github_access_token", AsyncMock(return_value="test-access-token"))
    monkeypatch.setattr(auth, "get_github_user", AsyncMock(return_value=GitHubUser(id=234, login="oauth-user")))
    client.cookies.set("oauth_state", "test-state")

    response = client.get("/api/v1/auth/github/callback?code=test-code&state=test-state", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://dashboard.example.test/"
