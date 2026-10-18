"""Metrics API coverage; the real pipeline is tested in test_pipeline_regressions.py."""

from codegate.database.models.analysis import AnalysisRun, CodeMetric, Source, Status, Trigger
from codegate.database.models.pull_request import PullRequest
from codegate.database.models.repository import Repository


def test_get_metrics_api(client, db_session):
    from codegate.database.models import Team
    # Ensure workspace exists
    ws = db_session.get(Team, 1)
    if not ws:
        ws = Team(id=1, name="Test Workspace", description="Mock")
        db_session.add(ws)
        db_session.commit()

    repo = Repository(owner="test", name="test_repo", full_name="test/test_repo", provider="github", url="https://github.com/test/repo", active=True, workspace_id=1)
    db_session.add(repo)
    db_session.commit()

    pr = PullRequest(repository_id=repo.id, number=1, title="Test PR", author_username="user", source_branch="feat", target_branch="main", head_sha="sha_A", state="OPEN", changed_files=1)
    db_session.add(pr)
    db_session.commit()

    run = AnalysisRun(pull_request_id=pr.id, head_sha="sha_A", status=Status.COMPLETED, trigger=Trigger.MANUAL)
    db_session.add(run)
    db_session.commit()

    metric = CodeMetric(analysis_run_id=run.id, analyzer=Source.RADON, metric_name="cyclomatic_complexity", file_path="complex.py", symbol="foo", value="15", grade="F")
    db_session.add(metric)
    db_session.commit()

    response = client.get(f"/api/v1/analyses/{run.id}/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["analyzer"] == Source.RADON
    assert data["items"][0]["metric_name"] == "cyclomatic_complexity"
    assert data["items"][0]["file_path"] == "complex.py"
    assert data["items"][0]["value"] == "15"

