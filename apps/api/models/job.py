"""Job, Source, and Matching domain models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from apps.api.database import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from apps.api.models.application import Application
    from apps.api.models.user import User


class JobSource(Base, TimestampMixin):
    """Compliance-tracked external source."""

    __tablename__ = "job_sources"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="public_api", nullable=False)
    tos_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    allowed_methods: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Job(Base, TimestampMixin):
    """Job listing model with unique fingerprinting per user."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_fingerprint", name="uq_jobs_user_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    company: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remote_type: Mapped[str] = mapped_column(
        String(50), default="on-site", index=True, nullable=False
    )
    employment_type: Mapped[str] = mapped_column(
        String(50), default="full-time", index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    required_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_id: Mapped[str] = mapped_column(String(50), default="manual_url", nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50), default="verified_live", nullable=False
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="jobs")
    matches: Mapped[list[JobMatch]] = relationship(
        "JobMatch", back_populates="job", cascade="all, delete-orphan"
    )
    application: Mapped[Optional[Application]] = relationship(
        "Application", back_populates="job", uselist=False
    )


class JobEmbedding(Base, TimestampMixin):
    """Vector representation of job description for semantic similarity search."""

    __tablename__ = "job_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(100), default="text-embedding-004", nullable=False
    )
    dimensions: Mapped[int] = mapped_column(Integer, default=768, nullable=False)
    embedding_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class JobMatch(Base, TimestampMixin):
    """Scored evaluation of job match against confirmed user profile facts."""

    __tablename__ = "job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_job"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    hard_filter_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="matches")
