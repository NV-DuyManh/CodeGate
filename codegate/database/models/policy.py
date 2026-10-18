from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base, TimestampMixin
from codegate.database.types import JSONType


class PolicyDecision(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCK = "BLOCK"


class EvaluationStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PublishStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class QualityPolicy(Base, TimestampMixin):
    __tablename__ = "quality_policies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    policy_engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    quality_pass_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    quality_block_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)

    risk_warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=40.0)
    risk_block_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=70.0)

    max_critical_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_high_security_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    require_quality_score: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_risk_score: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    require_complete_quality: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_complete_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    test_gate_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_tests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coverage_gate_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_coverage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changed_coverage_warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=70.0)
    changed_coverage_block_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="policies")
    evaluations: Mapped[list["PolicyEvaluation"]] = relationship(
        "PolicyEvaluation", back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyEvaluation(Base, TimestampMixin):
    __tablename__ = "policy_evaluations"
    __table_args__ = (
        UniqueConstraint('analysis_run_id', 'policy_id', 'policy_revision', name='uq_policy_evaluation'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("quality_policies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    policy_engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    decision: Mapped[Optional[PolicyDecision]] = mapped_column(String(50), nullable=True)

    passed_rules_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    warning_rules_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    blocked_rules_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    breakdown_json: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)
    flags_json: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)
    config_snapshot_json: Mapped[Optional[Any]] = mapped_column(JSONType, nullable=True)

    evaluation_status: Mapped[EvaluationStatus] = mapped_column(String(50), nullable=False, default=EvaluationStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    github_check_run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    github_publish_status: Mapped[Optional[PublishStatus]] = mapped_column(String(50), nullable=True)
    github_publish_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="policy_evaluations")
    policy: Mapped["QualityPolicy"] = relationship("QualityPolicy", back_populates="evaluations")


# Resolve relationship hints only after all model classes have been defined.
if TYPE_CHECKING:
    from codegate.database.models.analysis import AnalysisRun
    from codegate.database.models.repository import Repository
