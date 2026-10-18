from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from codegate.database.base import Base
from codegate.database.types import JSONType


class TestConfiguration(Base):
    __tablename__ = "test_configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False, default="PYTEST")
    executor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DISABLED")
    
    working_directory: Mapped[str] = mapped_column(String(255), nullable=True)
    test_paths_json: Mapped[str] = mapped_column(JSONType, nullable=True)
    pytest_args_json: Mapped[str] = mapped_column(JSONType, nullable=True)
    
    install_command: Mapped[str] = mapped_column(String(500), nullable=True)
    test_command: Mapped[str] = mapped_column(String(500), nullable=True)
    network_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    coverage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    coverage_source_json: Mapped[str] = mapped_column(JSONType, nullable=True)
    docker_image: Mapped[str] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    repository: Mapped["Repository"] = relationship("Repository", back_populates="test_configuration")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    test_configuration_id: Mapped[int] = mapped_column(Integer, ForeignKey("test_configurations.id", ondelete="SET NULL"), nullable=True)
    
    runner_version: Mapped[str] = mapped_column(String(50), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    executor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    execution_status: Mapped[str] = mapped_column(String(50), nullable=False)
    test_outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=True)
    
    tests_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_xfailed: Mapped[int] = mapped_column(Integer, nullable=True)
    tests_xpassed: Mapped[int] = mapped_column(Integer, nullable=True)
    
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    stdout_excerpt: Mapped[str] = mapped_column(String, nullable=True)
    stderr_excerpt: Mapped[str] = mapped_column(String, nullable=True)
    error_message: Mapped[str] = mapped_column(String, nullable=True)
    
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="test_run")
    coverage_report: Mapped["CoverageReport"] = relationship("CoverageReport", uselist=False, back_populates="test_run", cascade="all, delete-orphan")


class CoverageReport(Base):
    __tablename__ = "coverage_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    coverage_version: Mapped[str] = mapped_column(String(50), nullable=False)
    line_coverage: Mapped[float] = mapped_column(Float, nullable=True)
    branch_coverage: Mapped[float] = mapped_column(Float, nullable=True)
    
    total_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    changed_line_coverage: Mapped[float] = mapped_column(Float, nullable=True)
    changed_total_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_covered_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_missing_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    breakdown_json: Mapped[str] = mapped_column(JSONType, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    test_run: Mapped["TestRun"] = relationship("TestRun", back_populates="coverage_report")


# Resolve relationship hints only after all model classes have been defined.
if TYPE_CHECKING:
    from codegate.database.models.analysis import AnalysisRun
    from codegate.database.models.repository import Repository
