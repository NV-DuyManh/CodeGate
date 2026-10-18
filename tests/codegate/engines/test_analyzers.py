import pytest
import asyncio
import os
import tempfile
import stat
import shutil
from unittest.mock import patch, MagicMock, AsyncMock
from codegate.database.models.analysis import Source, Severity, Status
from codegate.engines.analyzers.ruff_analyzer import RuffAnalyzer
from codegate.engines.analyzers.bandit_analyzer import BanditAnalyzer
from codegate.engines.analyzers.radon_analyzer import RadonAnalyzer
from codegate.engines.analyzers.workspace import AnalyzerWorkspace
from codegate.engines.analyzers.runner import StaticAnalysisRunner

@pytest.fixture
def sample_workspace():
    """Create a temporary workspace with some python files containing intentional issues."""
    temp_dir = tempfile.mkdtemp(prefix="codegate_test_")
    
    # ruff issue (unused import)
    with open(os.path.join(temp_dir, "ruff_issue.py"), "w") as f:
        f.write("import os\nimport sys\n\nx = 1\n")
        
    # bandit issue (exec)
    with open(os.path.join(temp_dir, "bandit_issue.py"), "w") as f:
        f.write("def do_something(user_input):\n    exec(user_input)\n")
        
    # radon issue (high complexity)
    with open(os.path.join(temp_dir, "radon_issue.py"), "w") as f:
        f.write("def complex_func(x):\n" + 
                "".join([f"    if x == {i}:\n        return {i}\n" for i in range(50)]) +
                "    return 0\n")
                
    yield temp_dir
    
    # Cleanup
    def remove_readonly(func, path, _):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    shutil.rmtree(temp_dir, onerror=remove_readonly)


# 17. TESTS — RUFF
@pytest.mark.asyncio
async def test_ruff_analyzer(sample_workspace):
    analyzer = RuffAnalyzer()
    assert analyzer.supports()
    
    # Run the real tool on the workspace
    import subprocess
    proc = subprocess.run(analyzer.command, cwd=sample_workspace, capture_output=True, text=True)
    
    result = analyzer.parse_output(proc.stdout, proc.stderr, proc.returncode)
    
    # It should have a finding for unused import in ruff_issue.py
    assert result.status == Status.SUCCESS or result.status == Status.FAILED # Ruff exits with 1 if issues found
    findings = result.findings
    assert any("ruff_issue.py" in f.file_path for f in findings)
    
    ruff_finding = next(f for f in findings if "ruff_issue.py" in f.file_path)
    assert ruff_finding.analyzer == Source.RUFF
    assert ruff_finding.rule_id == "F401" # Unused import
    assert ruff_finding.start_line is not None

# 18. TESTS — BANDIT
@pytest.mark.asyncio
async def test_bandit_analyzer(sample_workspace):
    analyzer = BanditAnalyzer()
    if not analyzer.supports():
        pytest.skip("Bandit not installed")
        
    import subprocess
    proc = subprocess.run(analyzer.command, cwd=sample_workspace, capture_output=True, text=True)
    
    result = analyzer.parse_output(proc.stdout, proc.stderr, proc.returncode)
    
    findings = result.findings
    assert any("bandit_issue.py" in f.file_path for f in findings)
    
    bandit_finding = next(f for f in findings if "bandit_issue.py" in f.file_path)
    assert bandit_finding.analyzer == Source.BANDIT
    assert bandit_finding.severity in (Severity.MEDIUM, Severity.HIGH)
    assert bandit_finding.category == "SECURITY"
    assert bandit_finding.rule_id == "B102" # Exec used

# 19. TESTS — RADON
@pytest.mark.asyncio
async def test_radon_analyzer(sample_workspace):
    analyzer = RadonAnalyzer()
    if not analyzer.supports():
        pytest.skip("Radon not installed")
        
    import subprocess
    proc = subprocess.run(analyzer.command, cwd=sample_workspace, capture_output=True, text=True)
    
    result = analyzer.parse_output(proc.stdout, proc.stderr, proc.returncode)
    
    metrics = result.metrics
    assert any("radon_issue.py" in m.file_path for m in metrics)
    
    radon_metric = next(m for m in metrics if "radon_issue.py" in m.file_path)
    assert radon_metric.analyzer == Source.RADON
    assert radon_metric.metric_name == "cyclomatic_complexity"
    assert int(radon_metric.value) > 10 # Should be high complexity
    
    # High complexity should trigger a finding
    findings = result.findings
    assert len(findings) > 0
    assert findings[0].analyzer == Source.RADON
    assert findings[0].category == "COMPLEXITY"

# 20. ANALYZER FAILURE TEST & 21. TIMEOUT TEST
@pytest.mark.asyncio
async def test_analyzer_runner_timeout_and_failure(sample_workspace):
    # Mock DB
    db_session = MagicMock()
    analysis_run = MagicMock()
    analysis_run.id = 1
    
    # Mock workspace so it returns sample_workspace
    runner = StaticAnalysisRunner(db_session, analysis_run, "url", "sha", None)
    runner.workspace.prepare = MagicMock(return_value=sample_workspace)
    runner.workspace.cleanup = MagicMock()
    
    # Mock Ruff to timeout
    class TimeoutRuff(RuffAnalyzer):
        def supports(self): return True
        def parse_output(self, stdout, stderr, rc):
            return super().parse_output(stdout, stderr, rc)
    
    # Mock Bandit to fail with exception
    class FailingBandit(BanditAnalyzer):
        def supports(self): return True
        def parse_output(self, stdout, stderr, rc):
            raise RuntimeError("Intentional failure")
            
    runner.analyzers = [TimeoutRuff(), FailingBandit()]
    
    # Patch asyncio.wait_for to simulate timeout for Ruff
    original_wait_for = asyncio.wait_for
    call_count = {"ruff": 0}
    async def mock_wait_for(aw, timeout):
        call_count["ruff"] += 1
        if call_count["ruff"] == 1:
            aw.close()
            raise asyncio.TimeoutError()
        return await original_wait_for(aw, timeout)
        
    with patch("asyncio.wait_for", side_effect=mock_wait_for):
        await runner.run_all()
        
    # Check that DB was updated with TIMEOUT and FAILED
    # DB calls are add and commit
    added_runs = [call[0][0] for call in db_session.add.call_args_list if type(call[0][0]).__name__ == "AnalyzerRun"]
    assert any(run.analyzer == Source.RUFF and run.status == Status.TIMEOUT for run in added_runs)
    assert any(run.analyzer == Source.BANDIT and run.status == Status.FAILED for run in added_runs)

# 22. WORKSPACE CLEANUP TEST
def test_workspace_cleanup():
    workspace = AnalyzerWorkspace("fake_url", "fake_sha")
    with patch("subprocess.run") as mock_run:
        # Prevent actual git commands
        mock_run.return_value = MagicMock(returncode=0)
        
        path = workspace.prepare()
        assert os.path.exists(path)
        
        workspace.cleanup()
        assert not os.path.exists(path)
