import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from codegate.database.models.analysis import AnalysisRun, Status, Trigger
from codegate.database.models.pull_request import PullRequest
from codegate.database.models.repository import Repository
from codegate.services.analysis_orchestrator import AnalysisOrchestrator


# 3. ANALYSIS LIFECYCLE VERIFICATION
@pytest.mark.asyncio
async def test_analysis_lifecycle_cases(db_session: Session):
    repo = Repository(name="test_repo", owner="test", full_name="test/test_repo", provider="github", url="https://github.com/test/repo", active=True)
    db_session.add(repo)
    db_session.commit()
    
    pr = PullRequest(
        repository_id=repo.id,
        number=10,
        title="Test PR",
        description="desc",
        author_username="user",
        source_branch="feat",
        target_branch="main",
        head_sha="sha_A",
        state="OPEN",
        changed_files=1
    )
    db_session.add(pr)
    db_session.commit()
    
    orchestrator = AnalysisOrchestrator(db_session)
    pr_url = "https://github.com/test/repo/pull/10"
    
    with (
        patch("codegate.services.analysis_orchestrator.CodeGateAdapter") as MockAdapter,
        patch("codegate.services.analysis_orchestrator.StaticAnalysisRunner.run_all", new_callable=AsyncMock),
    ):
        # Case A: New analysis
        mock_adapter_instance = MockAdapter.return_value
        # Use an async mock for run()
        future = asyncio.Future()
        future.set_result({"review": {}, "usage": {}})
        mock_adapter_instance.run.return_value = future

        run, created = await orchestrator.trigger_analysis(pr, pr_url, force=False, trigger_type=Trigger.MANUAL)
        
        assert created is True
        assert run.status == Status.COMPLETED
        assert run.head_sha == "sha_A"
        assert run.trigger == Trigger.MANUAL

        # Case B: Same PR, Same SHA, force=false -> Should reuse
        run2, created2 = await orchestrator.trigger_analysis(pr, pr_url, force=False, trigger_type=Trigger.MANUAL)
        assert created2 is False
        assert run2.id == run.id
        
        # Case C: Same PR, Same SHA, force=true -> Should create new
        future2 = asyncio.Future()
        future2.set_result({"review": {}, "usage": {}})
        mock_adapter_instance.run.return_value = future2
        
        run3, created3 = await orchestrator.trigger_analysis(pr, pr_url, force=True, trigger_type=Trigger.MANUAL)
        assert created3 is True
        assert run3.id != run.id
        assert run3.status == Status.COMPLETED
        
        # Case D: Same PR, new SHA -> Should create new automatically
        pr.head_sha = "sha_B"
        db_session.commit()
        
        future3 = asyncio.Future()
        future3.set_result({"review": {}, "usage": {}})
        mock_adapter_instance.run.return_value = future3
        
        run4, created4 = await orchestrator.trigger_analysis(pr, pr_url, force=False, trigger_type=Trigger.MANUAL)
        assert created4 is True
        assert run4.head_sha == "sha_B"
        
        # Case E: AI throws exception
        future_err = asyncio.Future()
        future_err.set_exception(Exception("AI timeout"))
        mock_adapter_instance.run.return_value = future_err
        
        pr.head_sha = "sha_C"
        db_session.commit()
        
        run5, created5 = await orchestrator.trigger_analysis(pr, pr_url, force=False, trigger_type=Trigger.MANUAL)
        assert created5 is True
        # Since the error was caught and saved inside the orchestrator
        # We need to refresh to get the latest status
        db_session.refresh(run5)
        assert run5.status == Status.FAILED
        assert "AI timeout" in run5.error_message
