from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base, TimestampMixin
from codegate.database.types import JSONType


class Status(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class Trigger(str, Enum):
    WEBHOOK = "WEBHOOK"
    MANUAL = "MANUAL"
    PUSH = "PUSH"
    SCHEDULED = "SCHEDULED"

class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class Source(str, Enum):
    AI = "AI"
    RUFF = "RUFF"
    BANDIT = "BANDIT"
    SEMGREP = "SEMGREP"
    RADON = "RADON"
    TEST = "TEST"
    COVERAGE = "COVERAGE"
    SYSTEM = "SYSTEM"


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pull_request_id: Mapped[int] = mapped_column(
        ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    head_sha: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    status: Mapped[Status] = mapped_column(String(50), nullable=False, index=True)
    trigger: Mapped[Trigger] = mapped_column(String(50), nullable=False)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    ai_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="analysis_runs")
    analyzer_runs: Mapped[List["AnalyzerRun"]] = relationship(
        "AnalyzerRun", 
        back_populates="analysis_run", 
        cascade="all, delete-orphan"
    )
    code_metrics: Mapped[List["CodeMetric"]] = relationship(
        "CodeMetric", 
        back_populates="analysis_run", 
        cascade="all, delete-orphan"
    )
    findings: Mapped[List["Finding"]] = relationship(
        "Finding", 
        back_populates="analysis_run", 
        cascade="all, delete-orphan"
    )
    quality_scores: Mapped[List["QualityScore"]] = relationship(
        "QualityScore",
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )
    risk_scores: Mapped[List["RiskScore"]] = relationship(
        "RiskScore",
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )
    policy_evaluations: Mapped[List["PolicyEvaluation"]] = relationship(
        "PolicyEvaluation",
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )
    test_run: Mapped["TestRun"] = relationship(
        "TestRun",
        uselist=False,
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )
    job: Mapped["AnalysisJob"] = relationship(
        "AnalysisJob",
        uselist=False,
        back_populates="analysis_run",
        cascade="all, delete-orphan"
    )

class AnalysisJob(Base, TimestampMixin):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    last_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="job")



class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    source: Mapped[Source] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[Severity] = mapped_column(String(50), nullable=False, index=True)
    
    rule_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    start_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_changed_file: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_new_code: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    recommendation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    raw_data: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="findings")

class AnalyzerRun(Base, TimestampMixin):
    __tablename__ = "analyzer_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analyzer: Mapped[Source] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[Status] = mapped_column(String(50), nullable=False)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[Any]] = mapped_column("metadata", JSONType, nullable=True)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="analyzer_runs")

class CodeMetric(Base, TimestampMixin):
    __tablename__ = "code_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analyzer: Mapped[Source] = mapped_column(String(50), nullable=False, index=True)
    
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    grade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    metadata_json: Mapped[Optional[Any]] = mapped_column("metadata", JSONType, nullable=True)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="code_metrics")


class QualityScore(Base, TimestampMixin):
    __tablename__ = "quality_scores"
    __table_args__ = (
        UniqueConstraint('analysis_run_id', 'calculation_version', name='uq_quality_score_version'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    overall_score: Mapped[float] = mapped_column(nullable=False)
    grade: Mapped[str] = mapped_column(String(5), nullable=False)
    
    code_quality_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    security_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    testing_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    complexity_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    maintainability_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    ai_review_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    available_weight: Mapped[float] = mapped_column(nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    missing_dimensions: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)
    breakdown_json: Mapped[Any] = mapped_column(JSONType, nullable=False)
    
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="quality_scores")

class RiskScore(Base, TimestampMixin):
    __tablename__ = "risk_scores"
    __table_args__ = (
        UniqueConstraint('analysis_run_id', 'calculation_version', name='uq_risk_score_version'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    overall_risk: Mapped[float] = mapped_column(nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    
    change_surface_risk: Mapped[Optional[float]] = mapped_column(nullable=True)
    sensitive_path_risk: Mapped[Optional[float]] = mapped_column(nullable=True)
    security_risk: Mapped[Optional[float]] = mapped_column(nullable=True)
    complexity_risk: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    available_weight: Mapped[float] = mapped_column(nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    missing_dimensions: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)
    breakdown_json: Mapped[Any] = mapped_column(JSONType, nullable=False)
    
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="risk_scores")


# Resolve relationship hints only after all model classes have been defined.
if TYPE_CHECKING:
    from codegate.database.models.policy import PolicyEvaluation
    from codegate.database.models.pull_request import PullRequest
    from codegate.database.models.testing import TestRun
