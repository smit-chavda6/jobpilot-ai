"""User and authentication domain models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from apps.api.models.application import Application
    from apps.api.models.fact import ProfileFact
    from apps.api.models.job import Job
    from apps.api.models.profile import UserProfile
    from apps.api.models.resume import Resume
    from apps.api.models.security import ConsentRecord


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="candidate", nullable=False)
    daily_token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    profile: Mapped[UserProfile] = relationship(
        "UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    facts: Mapped[list[ProfileFact]] = relationship(
        "ProfileFact", back_populates="user", cascade="all, delete-orphan"
    )
    resumes: Mapped[list[Resume]] = relationship(
        "Resume", back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="user", cascade="all, delete-orphan"
    )
    consents: Mapped[list[ConsentRecord]] = relationship(
        "ConsentRecord", back_populates="user", cascade="all, delete-orphan"
    )
