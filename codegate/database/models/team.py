from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codegate.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from codegate.database.models.user import User


class Role(str, Enum):
    ADMIN = "ADMIN"
    MAINTAINER = "MAINTAINER"
    REVIEWER = "REVIEWER"
    DEVELOPER = "DEVELOPER"

class InvitationStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"

class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    members: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    invitations: Mapped[List["WorkspaceInvitation"]] = relationship("WorkspaceInvitation", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Role] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    team: Mapped["Team"] = relationship("Team", back_populates="members")
    # user relationship can be added here if we need to query user from member

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uix_team_id_user_id"),
    )


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    inviter_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Role] = mapped_column(String(50), nullable=False)
    
    # Optional explicitly targeted github login or email
    invitee_github_login: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invitee_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Hashed token for secure lookups
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    status: Mapped[InvitationStatus] = mapped_column(String(50), default=InvitationStatus.PENDING, nullable=False)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    team: Mapped["Team"] = relationship("Team", back_populates="invitations")
    inviter: Mapped["User"] = relationship("User", foreign_keys=[inviter_user_id])
