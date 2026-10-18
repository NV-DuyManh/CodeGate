from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base, TimestampMixin


class State(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"

class PullRequest(Base, TimestampMixin):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    
    provider_pr_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    author_username: Mapped[str] = mapped_column(String(255), nullable=False)
    
    source_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    
    state: Mapped[State] = mapped_column(String(50), nullable=False, index=True)
    
    additions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deletions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    changed_files: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    head_sha: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    base_sha: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    provider_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="pull_requests")
    files: Mapped[List["PullRequestFile"]] = relationship(
        "PullRequestFile", 
        back_populates="pull_request", 
        cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[List["AnalysisRun"]] = relationship(
        "AnalysisRun", 
        back_populates="pull_request", 
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "number", name="uix_repository_id_number"),
    )


class PullRequestFile(Base):
    __tablename__ = "pull_request_files"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="files")

    __table_args__ = (
        UniqueConstraint("pull_request_id", "filename", name="uix_pull_request_id_filename"),
    )


# Resolve relationship hints only after all model classes have been defined.
if TYPE_CHECKING:
    from codegate.database.models.analysis import AnalysisRun
    from codegate.database.models.repository import Repository
