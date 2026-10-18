import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from codegate.api.main import app
from codegate.config.settings import settings
from codegate.database.models.webhook import WebhookEvent
from codegate.database.models.pull_request import PullRequest
from codegate.database.models.analysis import AnalysisRun, Trigger, Status
from codegate.integrations.pr_agent.normalizer import PRAgentNormalizer

client = TestClient(app)

def test_normalizer_basic():
    raw_data = {
        "review": {
            "key_issues_to_review": [
                {
                    "relevant_file": "src/main.py",
                    "start_line": 10,
                    "end_line": 12,
                    "issue_header": "Bug in logic",
                    "suggestion": "Fix it"
                }
            ],
            "security_concerns": "Possible SQL Injection"
        },
        "usage": {
            "total_tokens": 100
        }
    }
    findings = PRAgentNormalizer.normalize_findings(raw_data)
    assert len(findings) == 2
    assert findings[0].file_path == "src/main.py"
    assert findings[0].start_line == 10
    assert findings[0].category == "BUG"
    
    assert findings[1].category == "SECURITY"
    assert findings[1].title == "Security Concern"

def test_webhook_unauthorized(client, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    response = client.post("/api/v1/github_webhooks", json={"action": "opened"}, headers={})
    assert response.status_code == 401

def test_webhook_deduplication(client, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
    headers = {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": "test-delivery-id-dedup-123"
    }
    body = {
        "action": "opened",
        "pull_request": {"number": 1, "html_url": "https://github.com/foo/bar/pull/1"},
        "repository": {"full_name": "foo/bar"}
    }
    
    body_bytes = json.dumps(body).encode()
    headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(
        b"test-webhook-secret", body_bytes, hashlib.sha256
    ).hexdigest()
    response = client.post("/api/v1/github_webhooks", content=body_bytes, headers=headers)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert db_session.query(WebhookEvent).count() == 1

    response2 = client.post("/api/v1/github_webhooks", content=body_bytes, headers=headers)
    assert response2.status_code == 200
    assert response2.json() == {"status": "ignored", "reason": "Duplicate event"}
    assert db_session.query(WebhookEvent).count() == 1
