from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from codegate.database.models.policy import QualityPolicy
    from codegate.database.models.pull_request import PullRequest
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base, TimestampMixin


class Provider(str, Enum):
    GITHUB = "GITHUB"
    GITLAB = "GITLAB"
    BITBUCKET = "BITBUCKET"
    AZURE_DEVOPS = "AZURE_DEVOPS"
    GITEA = "GITEA"
    OTHER = "OTHER"

class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider: Mapped[Provider] = mapped_column(String(50), nullable=False)
    provider_repository_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    access_status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    data_source: Mapped[str] = mapped_column(String(20), server_default="LIVE")
    github_connection_id: Mapped[Optional[int]] = mapped_column(ForeignKey("github_connections.id"), nullable=True)
    github_connection = relationship("GitHubConnection", back_populates="repositories")
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True, index=True)
    workspace = relationship("Team")
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    pull_requests: Mapped[List["PullRequest"]] = relationship(
        "PullRequest", 
        back_populates="repository", 
        cascade="all, delete-orphan"
    )
    policies: Mapped[List["QualityPolicy"]] = relationship(
        "QualityPolicy",
        back_populates="repository",
        cascade="all, delete-orphan"
    )
    test_configuration = relationship("TestConfiguration", back_populates="repository", cascade="all, delete-orphan")


    __table_args__ = (
        UniqueConstraint("github_connection_id", "provider_repository_id", name="uix_github_connection_provider_repo_id"),
    )
