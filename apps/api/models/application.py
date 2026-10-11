"""Application tracking and state machine models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from apps.api.database import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from apps.api.models.job import Job
    from apps.api.models.user import User


class Application(Base, TimestampMixin):
    """Job application instance tracked through human-in-the-loop state machine."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="discovered", index=True, nullable=False
    )
    resume_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    cover_letter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="applications")
    job: Mapped[Job] = relationship("Job", back_populates="application")
    activities: Mapped[list[ApplicationActivity]] = relationship(
        "ApplicationActivity",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationActivity.created_at.desc()",
    )
    documents: Mapped[list[ApplicationDocument]] = relationship(
        "ApplicationDocument", back_populates="application", cascade="all, delete-orphan"
    )
    screening_answers: Mapped[list[ScreeningAnswer]] = relationship(
        "ScreeningAnswer", back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationDocument(Base, TimestampMixin):
    __tablename__ = "application_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    application: Mapped[Application] = relationship("Application", back_populates="documents")


class ApplicationActivity(Base, TimestampMixin):
    """Append-only audit trail of every status transition and candidate action."""

    __tablename__ = "application_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(50), default="status_change", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    activity_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    application: Mapped[Application] = relationship("Application", back_populates="activities")


class ScreeningAnswer(Base, TimestampMixin):
    """Screening question and grounded or manual answer."""

    __tablename__ = "screening_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="needs_user_input", nullable=False)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    application: Mapped[Application] = relationship(
        "Application", back_populates="screening_answers"
    )
