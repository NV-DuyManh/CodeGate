"""Run controlled local source revisions through CodeGate's existing engines."""
import hashlib
import json
import secrets
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect

from codegate.database.models import (
    AnalysisRun,
    AuthSession,
    PullRequest,
    PullRequestFile,
    Repository,
    Team,
    TeamMember,
    User,
)
from codegate.database.models.analysis import AnalyzerRun
from codegate.engines.analyzers.runner import StaticAnalysisRunner
from codegate.engines.testing.changed_lines import ChangedLinesResolver
from codegate.engines.testing.executor import LocalTrustedExecutor
from codegate.engines.testing.pytest_runner import PytestRunner
from codegate.repositories.policy_store import quality_policy_store
from codegate.repositories.testing_store import TestingStore
from codegate.services.policy_service import quality_policy_service
from codegate.services.quality_service import quality_service
from codegate.services.risk_service import risk_service


def row_data(row):
    if row is None:
        return None
    return jsonable_encoder({item.key: getattr(row, item.key) for item in inspect(row).mapper.column_attrs})


class RecordingHarness:
    """Execute only a locally generated fixture, with no provider or AI adapter."""

    def __init__(self, runtime_root):
        self.root = Path(runtime_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._fixture = None

    def identity(self, db):
        user = db.query(User).filter_by(provider="local-recording", provider_user_id="viewer").first()
        if user is None:
            team = Team(name="Local runtime recording", description="Real local analyzers and tests; no GitHub or AI")
            db.add(team)
            db.flush()
            user = User(provider="local-recording", provider_user_id="viewer", username="local-recording-viewer",
                        display_name="Local recording session", active_workspace_id=team.id)
            db.add(user)
            db.flush()
            db.add(TeamMember(team_id=team.id, user_id=user.id, role="ADMIN"))
            db.commit()
        return user

    def create_session(self, db):
        user = self.identity(db)
        token = secrets.token_urlsafe(64)
        db.add(AuthSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=4)))
        db.commit()
        return token, user

    @staticmethod
    def git(repo, *args):
        result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=60)
        return result.stdout.strip()

    def fixture(self):
        if self._fixture is not None:
            return self._fixture
        repo = self.root / f"fixture-{uuid.uuid4().hex[:12]}"
        repo.mkdir()
        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.name", "CodeGate Local Recording")
        self.git(repo, "config", "user.email", "recording@localhost.invalid")
        self.git(repo, "config", "core.autocrlf", "false")
        (repo / "calculator.py").write_text("def add(left, right):\n    return 0\n", encoding="utf-8")
        (repo / "test_calculator.py").write_text(
            "from calculator import add\n\n\n"
            "def test_positive():\n    if add(2, 3) != 5:\n        raise AssertionError('2 + 3 must equal 5')\n\n\n"
            "def test_negative():\n    if add(-2, -3) != -5:\n        raise AssertionError('-2 + -3 must equal -5')\n",
            encoding="utf-8",
        )
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "baseline fixture")
        base = self.git(repo, "rev-parse", "HEAD")
        (repo / "calculator.py").write_text(
            "import os\n\n\ndef add(left, right):\n    return left - right\n\n\n"
            "def parse_untrusted(expression):\n    return eval(expression)\n", encoding="utf-8"
        )
        self.git(repo, "commit", "-am", "introduce deliberate lint, unsafe evaluation and arithmetic regression")
        unsafe = self.git(repo, "rev-parse", "HEAD")
        (repo / "calculator.py").write_text("def add(left, right):\n    return left + right\n", encoding="utf-8")
        self.git(repo, "commit", "-am", "fix arithmetic and remove unsafe evaluation and unused import")
        safe = self.git(repo, "rev-parse", "HEAD")
        self._fixture = repo, base, {"unsafe": unsafe, "safe": safe}
        return self._fixture

    async def analyze(self, db, case):
        if case not in {"unsafe", "safe"}:
            raise ValueError("Case must be unsafe or safe")
        user = self.identity(db)
        source, base, heads = self.fixture()
        head = heads[case]
        repo = db.query(Repository).filter_by(
            workspace_id=user.active_workspace_id, full_name="local-recording/calculator"
        ).first()
        if repo is None:
            repo = Repository(provider="OTHER", owner="local-recording", name="calculator",
                              full_name="local-recording/calculator", url=source.as_uri(),
                              workspace_id=user.active_workspace_id, data_source="LIVE")
            db.add(repo)
            db.commit()
            policy = quality_policy_store.create_default(db, repo.id)
            policy.test_gate_enabled = True
            policy.require_tests = True
            policy.coverage_gate_enabled = True
            policy.require_coverage = True
            db.commit()
        number = db.query(PullRequest).filter_by(repository_id=repo.id).count() + 1
        stats = []
        for line in self.git(source, "diff", "--numstat", base, head).splitlines():
            additions, deletions, filename = line.split("\t", 2)
            stats.append((int(additions), int(deletions), filename))
        pr = PullRequest(repository_id=repo.id, number=number,
                         title=f"Local source run: {'fix verified' if case == 'safe' else 'regression detected'}",
                         description="Controlled local Git fixture. Real analyzers and pytest; no GitHub or AI review.",
                         author_username=user.username, source_branch=f"recording/{case}", target_branch="main",
                         state="OPEN", base_sha=base, head_sha=head, additions=sum(item[0] for item in stats),
                         deletions=sum(item[1] for item in stats), changed_files=len(stats))
        db.add(pr)
        db.flush()
        for additions, deletions, filename in stats:
            db.add(PullRequestFile(pull_request_id=pr.id, filename=filename, status="modified", additions=additions,
                                   deletions=deletions, changes=additions + deletions))
        run = AnalysisRun(pull_request_id=pr.id, head_sha=head, status="RUNNING", trigger="MANUAL",
                          started_at=datetime.now(timezone.utc), ai_model=None)
        db.add(run)
        db.commit()
        try:
            runner = StaticAnalysisRunner(db, run, source.as_uri(), head)
            if len(runner.analyzers) != 3:
                raise RuntimeError("Recording requires installed and enabled Ruff, Bandit and Radon")
            await runner.run_all()
            analyzer_runs = db.query(AnalyzerRun).filter_by(analysis_run_id=run.id).all()
            if len(analyzer_runs) != 3 or {
                item.analyzer for item in analyzer_runs if item.status == "SUCCESS"
            } != {"RUFF", "BANDIT", "RADON"}:
                raise RuntimeError("Recording requires actual successful Ruff, Bandit and Radon analyzer runs")
            self.git(source, "checkout", "--detach", head)
            started = datetime.now(timezone.utc)
            execution, outcome, junit, coverage, stdout, stderr = await PytestRunner(
                LocalTrustedExecutor(workspace_root=str(source))
            ).run(str(source), ["test_calculator.py"], ["-q", "--import-mode=importlib"], 60, True)
            store = TestingStore()
            test = store.upsert_test_run(db, run.id, {
                "runner_version": "pytest-v1", "framework": "PYTEST", "executor_type": "LOCAL_TRUSTED",
                "execution_status": execution.value, "test_outcome": outcome.value,
                "tests_total": junit.tests, "tests_passed": junit.passed, "tests_failed": junit.failures,
                "tests_errors": junit.errors, "tests_skipped": junit.skipped,
                "duration_ms": int(junit.duration * 1000), "started_at": started,
                "finished_at": datetime.now(timezone.utc), "stdout_excerpt": stdout, "stderr_excerpt": stderr,
            })
            if coverage is not None:
                lines = await ChangedLinesResolver.get_changed_lines(str(source), base, head)
                covered, total, percent = ChangedLinesResolver.calculate_changed_coverage(coverage, lines)
                store.upsert_coverage_report(db, test.id, {
                    "coverage_version": "coverage-v1", "line_coverage": coverage.line_coverage,
                    "branch_coverage": coverage.branch_coverage, "total_lines": coverage.total_lines,
                    "covered_lines": coverage.covered_lines, "missing_lines": coverage.missing_lines,
                    "changed_line_coverage": percent if total else None, "changed_total_lines": total,
                    "changed_covered_lines": covered, "changed_missing_lines": total - covered,
                    "is_complete": total > 0, "breakdown_json": coverage.model_dump(),
                })
            db.commit()
            db.expire_all()
            if quality_service.calculate_and_persist(db, run.id) is None:
                raise RuntimeError("Quality calculation failed")
            if risk_service.calculate_and_persist(db, run.id) is None:
                raise RuntimeError("Risk calculation failed")
            evaluation = quality_policy_service.evaluate_and_publish(db, run, publisher=None)
            if evaluation.evaluation_status != "COMPLETED":
                raise RuntimeError("Policy evaluation failed")
            run.status = "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.expire_all()
            result = self.evidence(db, run.id)
            result.update({"case": case, "source_repository": str(source), "base_sha": base, "head_sha": head})
            evidence_dir = self.root / "evidence"
            evidence_dir.mkdir(exist_ok=True)
            (evidence_dir / f"analysis-{run.id}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
        except Exception as exc:
            db.rollback()
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise

    @staticmethod
    def evidence(db, analysis_id):
        run = db.get(AnalysisRun, analysis_id)
        return {
            "analysis": row_data(run), "pull_request": row_data(run.pull_request),
            "analyzers": [row_data(item) for item in run.analyzer_runs],
            "findings": [row_data(item) for item in run.findings],
            "metrics": [row_data(item) for item in run.code_metrics],
            "quality": row_data(run.quality_scores[-1]) if run.quality_scores else None,
            "risk": row_data(run.risk_scores[-1]) if run.risk_scores else None,
            "policy": row_data(run.policy_evaluations[-1]) if run.policy_evaluations else None,
            "tests": row_data(run.test_run),
            "coverage": row_data(run.test_run.coverage_report) if run.test_run else None,
            "integrations": {"ai": "NOT_CONFIGURED", "github_oauth": "NOT_CONFIGURED",
                             "github_app": "NOT_CONFIGURED", "github_publish": "NOT_ATTEMPTED",
                             "queue": "NOT_USED", "session": "LOCAL_RECORDING"},
        }
