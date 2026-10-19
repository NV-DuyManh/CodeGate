"""Exercise the recording fixture through real Git, analyzers, pytest and SQLAlchemy."""
import asyncio
import importlib.util

import pytest
from fastapi import HTTPException, Request

from codegate.database.models import AnalysisRun, AuthSession, Finding


def test_recording_cases_persist_real_failed_and_passed_results(db_session, tmp_path):
    assert importlib.util.find_spec("tools.recording") is not None, "Recording harness is not implemented"
    from tools.recording.harness import RecordingHarness

    harness = RecordingHarness(tmp_path)
    unsafe = asyncio.run(harness.analyze(db_session, "unsafe"))
    safe = asyncio.run(harness.analyze(db_session, "safe"))

    assert unsafe["base_sha"] == safe["base_sha"]
    assert unsafe["source_repository"] == safe["source_repository"]
    assert unsafe["tests"]["test_outcome"] == "FAILED"
    assert safe["tests"]["test_outcome"] == "PASSED"
    assert unsafe["policy"]["decision"] == "BLOCK"
    assert safe["policy"]["decision"] == "WARNING"
    assert "PARTIAL_QUALITY" in safe["policy"]["flags_json"]
    assert unsafe["quality"]["overall_score"] < safe["quality"]["overall_score"]
    assert {item["analyzer"] for item in safe["analyzers"]} == {"RUFF", "BANDIT", "RADON"}
    assert all(item["status"] == "SUCCESS" for item in safe["analyzers"])
    assert safe["coverage"]["changed_line_coverage"] == 100.0
    assert safe["quality"]["is_complete"] is False
    assert safe["integrations"]["ai"] == "NOT_CONFIGURED"
    assert safe["integrations"]["github_oauth"] == "NOT_CONFIGURED"
    assert db_session.query(AnalysisRun).count() == 2
    assert db_session.query(Finding).filter(Finding.source == "AI").count() == 0
    assert any(item["source"] == "BANDIT" for item in unsafe["findings"])


def test_recording_session_uses_existing_authentication(db_session, tmp_path):
    assert importlib.util.find_spec("tools.recording") is not None, "Recording harness is not implemented"
    from tools.recording.harness import RecordingHarness

    token, user = RecordingHarness(tmp_path).create_session(db_session)
    import hashlib
    row = db_session.query(AuthSession).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert user.provider == "local-recording"
    assert user.active_workspace_id is not None


def test_recording_rejects_disabled_static_analysis(db_session, tmp_path, monkeypatch):
    from codegate.config.settings import settings
    from tools.recording.harness import RecordingHarness

    monkeypatch.setattr(settings, "STATIC_ANALYSIS_ENABLED", False)
    with pytest.raises(RuntimeError, match="successful Ruff, Bandit and Radon"):
        asyncio.run(RecordingHarness(tmp_path).analyze(db_session, "safe"))
    run = db_session.query(AnalysisRun).one()
    assert run.status == "FAILED"
    assert run.quality_scores == []
    assert run.test_run is None


def test_recording_rejects_failed_analyzer_subprocess(db_session, tmp_path, monkeypatch):
    import sys

    from codegate.engines.analyzers.ruff_analyzer import RuffAnalyzer
    from tools.recording.harness import RecordingHarness

    # Execute a real failing process, rather than synthesizing an AnalyzerResult.
    monkeypatch.setattr(RuffAnalyzer, "command", property(lambda self: [sys.executable, "-c", "raise SystemExit(2)"]))
    with pytest.raises(RuntimeError, match="successful Ruff, Bandit and Radon"):
        asyncio.run(RecordingHarness(tmp_path).analyze(db_session, "safe"))
    run = db_session.query(AnalysisRun).one()
    assert run.status == "FAILED"
    assert any(item.analyzer == "RUFF" and item.status == "FAILED" for item in run.analyzer_runs)
    assert run.quality_scores == []


@pytest.mark.parametrize("host,origin", [
    ("rebound.example:8000", None),
    ("127.0.0.1:8000", "http://127.0.0.1.evil.example"),
    ("127.0.0.1:8000", "http://127.0.0.1/path"),
    ("127.0.0.1:8000", "http://127.0.0.1:invalid"),
    ("127.0.0.1:8000", "http://[broken"),
])
def test_recording_rejects_invalid_host_and_origin(host, origin):
    from tools.recording import server

    assert hasattr(server, "local_only"), "Local request validation must be independently testable"
    headers = [(b"host", host.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    request = Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": headers})
    with pytest.raises(HTTPException) as rejected:
        server.local_only(request)
    assert rejected.value.status_code == 403


@pytest.mark.parametrize("host,origin", [
    ("127.0.0.1:8000", None),
    ("127.0.0.1:8000", "http://127.0.0.1:5173"),
    ("localhost:8000", "http://localhost:8000"),
    ("[::1]:8000", "http://[::1]:5173"),
])
def test_recording_accepts_local_host_and_origin(host, origin):
    from tools.recording import server

    assert hasattr(server, "local_only"), "Local request validation must be independently testable"
    headers = [(b"host", host.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    server.local_only(Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": headers}))
