import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from codegate.database.models.github import GitHubConnection
from codegate.database.models.repository import Repository, Provider
from codegate.database.models import Team
from codegate.services.github_sync_service import GithubSyncService
from codegate.api.main import app

client = TestClient(app)

def get_mock_repo(id, name, owner, full_name=None):
    return {
        "id": id,
        "name": name,
        "owner": {"login": owner},
        "full_name": full_name or f"{owner}/{name}",
        "html_url": f"https://github.com/{owner}/{name}",
        "default_branch": "main",
    }

@pytest.fixture
def sync_setup(db_session: Session):
    workspace = Team(id=1, name="Workspace A")
    workspace2 = Team(id=2, name="Workspace B")
    db_session.merge(workspace)
    db_session.merge(workspace2)
    db_session.commit()

    conn1 = GitHubConnection(
        workspace_id=1,
        installation_id=100,
        account_login="org-a",
        account_type="Organization",
        repository_selection="all",
        status="active"
    )
    conn2 = GitHubConnection(
        workspace_id=2,
        installation_id=200,
        account_login="org-b",
        account_type="Organization",
        repository_selection="all",
        status="active"
    )
    db_session.add_all([conn1, conn2])
    db_session.commit()
    return conn1, conn2

@pytest.mark.asyncio
async def test_repository_sync_pagination(db_session: Session, sync_setup):
    conn1, _ = sync_setup
    
    # Mock pagination: 100 items on page1 to trigger next page
    page1 = [get_mock_repo(i, f"repo{i}", "org-a") for i in range(1, 101)]
    page2 = [get_mock_repo(101, "repo101", "org-a")]
    
    with patch("codegate.services.github_app.GitHubAppService.get_installation_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = "fake-token"
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            class MockResponse:
                def __init__(self, json_data, status_code=200):
                    self._json_data = json_data
                    self.status_code = status_code
                def json(self):
                    return self._json_data
                def raise_for_status(self):
                    pass

            mock_get.side_effect = [
                MockResponse({"repositories": page1}),
                MockResponse({"repositories": page2}),
                MockResponse({"repositories": []})
            ]
            
            service = GithubSyncService(db_session)
            await service.sync_repositories(conn1.id)
            
            repos = db_session.query(Repository).filter_by(workspace_id=1).all()
            assert len(repos) == 101
            assert {r.provider_repository_id for r in repos} == {str(i) for i in range(1, 102)}
            assert all(r.access_status == "ACTIVE" for r in repos)

@pytest.mark.asyncio
async def test_idempotent_sync_and_rename(db_session: Session, sync_setup):
    conn1, _ = sync_setup
    
    initial_repos = [get_mock_repo(101, "old-name", "org-a")]
    
    with patch("codegate.services.github_app.GitHubAppService.get_installation_access_token", new_callable=AsyncMock):
        with patch("codegate.services.github_app.GitHubAppService.get_installation_repositories", new_callable=AsyncMock) as mock_repos:
            mock_repos.side_effect = [initial_repos, []]
            
            service = GithubSyncService(db_session)
            res = await service.sync_repositories(conn1.id)
            assert res["created"] == 1
            
            # Idempotent call
            mock_repos.side_effect = [initial_repos, []]
            res = await service.sync_repositories(conn1.id)
            assert res["created"] == 0
            assert res["updated"] == 0
            
            # Rename call
            renamed_repos = [get_mock_repo(101, "new-name", "org-a")]
            mock_repos.side_effect = [renamed_repos, []]
            res = await service.sync_repositories(conn1.id)
            assert res["created"] == 0
            assert res["updated"] == 1
            
            repo = db_session.query(Repository).filter_by(provider_repository_id="101").first()
            assert repo.name == "new-name"
            assert repo.full_name == "org-a/new-name"

@pytest.mark.asyncio
async def test_access_removal_and_reaccess(db_session: Session, sync_setup):
    conn1, _ = sync_setup
    
    repos_abc = [
        get_mock_repo(101, "a", "org-a"),
        get_mock_repo(102, "b", "org-a"),
        get_mock_repo(103, "c", "org-a"),
    ]
    repos_ac = [
        get_mock_repo(101, "a", "org-a"),
        get_mock_repo(103, "c", "org-a"),
    ]
    
    with patch("codegate.services.github_app.GitHubAppService.get_installation_access_token", new_callable=AsyncMock):
        with patch("codegate.services.github_app.GitHubAppService.get_installation_repositories", new_callable=AsyncMock) as mock_repos:
            # Sync A, B, C
            mock_repos.side_effect = [repos_abc, []]
            service = GithubSyncService(db_session)
            await service.sync_repositories(conn1.id)
            
            # Access removal: Sync A, C
            mock_repos.side_effect = [repos_ac, []]
            res = await service.sync_repositories(conn1.id)
            assert res["removed_access"] == 1
            
            b_repo = db_session.query(Repository).filter_by(provider_repository_id="102").first()
            assert b_repo is not None
            assert b_repo.access_status == "ACCESS_REMOVED"
            
            # Re-access: Sync A, B, C
            mock_repos.side_effect = [repos_abc, []]
            res = await service.sync_repositories(conn1.id)
            assert res["updated"] == 1
            b_repo_again = db_session.query(Repository).filter_by(provider_repository_id="102").first()
            assert b_repo_again.access_status == "ACTIVE"
            assert b_repo_again.id == b_repo.id  # Same row reused

@pytest.mark.asyncio
async def test_zero_repositories(db_session: Session, sync_setup):
    conn1, _ = sync_setup
    
    with patch("codegate.services.github_app.GitHubAppService.get_installation_access_token", new_callable=AsyncMock):
        with patch("codegate.services.github_app.GitHubAppService.get_installation_repositories", new_callable=AsyncMock) as mock_repos:
            mock_repos.side_effect = [[], []]
            service = GithubSyncService(db_session)
            res = await service.sync_repositories(conn1.id)
            assert res["discovered"] == 0
            
            # Connection stays active
            db_session.refresh(conn1)
            assert conn1.status == "active"

def test_manual_sync_cross_workspace(client: TestClient, db_session: Session, sync_setup):
    conn1, conn2 = sync_setup
    
    with patch("codegate.api.dependencies.get_current_workspace", return_value=db_session.query(Team).get(1)):
        response = client.post(f"/api/v1/integrations/github/connections/{conn2.id}/sync")
        assert response.status_code == 404

def test_webhook_unknown_installation(client: TestClient, db_session: Session, monkeypatch):
    from codegate.config.settings import settings

    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    # Payload with unknown installation
    payload = {
        "action": "added",
        "installation": {"id": 9999},
        "repositories_added": [{"id": 123, "name": "foo", "full_name": "bar/foo"}]
    }
    with patch("codegate.api.routers.webhooks.verify_signature", return_value=True):
        response = client.post(
            "/api/v1/github_webhooks",
            json=payload,
            headers={"X-GitHub-Event": "installation_repositories", "X-Hub-Signature-256": "sha256=xxx", "X-GitHub-Delivery": "delivery123"}
        )
        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}

@pytest.mark.skip(reason="Phase 11 webhook pipeline refactoring")
@pytest.mark.asyncio
async def test_webhook_installation_deleted(db_session: Session, sync_setup):
    from codegate.api.routers.webhooks import process_webhook_synchronously
    conn1, _ = sync_setup
    
    payload = {
        "action": "deleted",
        "installation": {"id": conn1.installation_id},
    }
    from codegate.database.models.webhook import WebhookEvent
    webhook_event = WebhookEvent(
        provider="github",
        delivery_id="delivery123",
        event_type="installation",
        action="deleted",
        status="PENDING",
        payload_hash="xxx"
    )
    db_session.add(webhook_event)
    db_session.commit()
    
    from unittest.mock import MagicMock
    mock_session_local = MagicMock()
    mock_session_local.return_value.__enter__.return_value = db_session
    with patch("codegate.api.routers.webhooks.SessionLocal", new=mock_session_local):
        await process_webhook_synchronously(db_session, "delivery123", "installation", "deleted", payload, webhook_event)

    db_session.refresh(conn1)
    assert conn1.status == "DISCONNECTED"
