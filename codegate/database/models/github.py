from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base

if TYPE_CHECKING:
    from codegate.database.models.repository import Repository


class GitHubConnection(Base):
    __tablename__ = "github_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="github")
    account_login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(50), nullable=True)
    auth_type: Mapped[str] = mapped_column(String(50), default="app") # app or pat
    status: Mapped[str] = mapped_column(String(50), default="active")
    installation_id: Mapped[str] = mapped_column(String(255), nullable=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True, index=True)
    repository_selection: Mapped[str] = mapped_column(String(50), nullable=True)
    
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    workspace = relationship("Team")
    repositories: Mapped[list["Repository"]] = relationship("Repository", back_populates="github_connection")

    __table_args__ = (
        UniqueConstraint("provider", "installation_id", name="uix_provider_installation_id"),
    )


class GitHubInstallationState(Base):
    __tablename__ = "github_installation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    state_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

