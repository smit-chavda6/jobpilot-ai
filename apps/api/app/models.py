"""SQLAlchemy domain model (spec §4). Every user-owned table carries `user_id`.

Relationships are intentionally not declared: all access goes through explicit,
user-scoped repository queries (see app/repositories.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)


# --------------------------------------------------------------------------- identity


class User(Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lockouts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reauth_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuthToken(Base):
    """Hashed, single-use, expiring tokens: refresh / verify_email / reset_password."""

    __tablename__ = "auth_tokens"
    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DevMailbox(Base):
    """Development-only outbox for transactional emails (verification / reset).

    JobPilot never sends email to third parties; in production this would be
    replaced by an SMTP relay for *account* emails only.
    """

    __tablename__ = "dev_mailbox"
    user_id: Mapped[uuid.UUID] = _user_fk()
    to_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    headline: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[float | None] = mapped_column(Float)
    education_level: Mapped[str | None] = mapped_column(String(32))
    target_titles: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    remote_preference: Mapped[str] = mapped_column(String(16), default="any")  # remote|hybrid|onsite|any
    employment_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    needs_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    blocked_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    blocked_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience_filter_mode: Mapped[str] = mapped_column(String(8), default="soft")  # soft|hard
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    ai_daily_token_budget: Mapped[int | None] = mapped_column(Integer)
    adapter_flags: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)
    notify_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_triage: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    saved_job_filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    user_id: Mapped[uuid.UUID] = _user_fk()
    purpose: Mapped[str] = mapped_column(String(64))  # ai_processing | email_access
    granted: Mapped[bool] = mapped_column(Boolean)
    provider: Mapped[str] = mapped_column(String(32), default="")
    policy_version: Mapped[str] = mapped_column(String(16), default="1")


# --------------------------------------------------------------------------- profile facts


class Resume(Base):
    __tablename__ = "resumes"
    user_id: Mapped[uuid.UUID] = _user_fk()
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text, default="")
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|parsed|failed
    parse_error: Mapped[str | None] = mapped_column(Text)


class ProfileFact(Base):
    """Atomic, user-verifiable claim (spec §6). Only `confirmed` facts may be used downstream."""

    __tablename__ = "profile_facts"
    user_id: Mapped[uuid.UUID] = _user_fk()
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # resume|manual
    status: Mapped[str] = mapped_column(String(16), default="candidate")  # candidate|confirmed|rejected
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    __table_args__ = (Index("ix_profile_facts_user_status", "user_id", "status"),)


class UserSkill(Base):
    __tablename__ = "user_skills"
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(100))
    proficiency: Mapped[str | None] = mapped_column(String(16))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profile_facts.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_skills_user_name"),)


# --------------------------------------------------------------------------- jobs


class Job(Base):
    __tablename__ = "jobs"
    user_id: Mapped[uuid.UUID] = _user_fk()
    source: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    remote_policy: Mapped[str] = mapped_column(String(16), default="unknown")
    employment_type: Mapped[str] = mapped_column(String(32), default="unknown")
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    min_years: Mapped[float | None] = mapped_column(Float)
    education_req: Mapped[str | None] = mapped_column(String(32))
    sponsorship: Mapped[str] = mapped_column(String(16), default="unknown")  # offered|not_offered|unknown
    description_html: Mapped[str] = mapped_column(Text, default="")
    description_text: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    fingerprint: Mapped[str] = mapped_column(String(64))
    potential_duplicate_of: Mapped[uuid.UUID | None] = mapped_column()
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    scam_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_jobs_user_fingerprint"),
        Index("ix_jobs_user_created", "user_id", "created_at"),
        Index("ix_jobs_user_source", "user_id", "source"),
    )


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    model: Mapped[str] = mapped_column(String(64))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSON)


class JobMatch(Base):
    __tablename__ = "job_matches"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    eligible: Mapped[bool] = mapped_column(Boolean)
    recommended_action: Mapped[str] = mapped_column(String(32))
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_job"),
        Index("ix_job_matches_user_score", "user_id", "score"),
    )


class FailedImport(Base):
    """User-visible dead-letter list for ingestion failures."""

    __tablename__ = "failed_imports"
    user_id: Mapped[uuid.UUID] = _user_fk()
    source: Mapped[str] = mapped_column(String(32))
    input_ref: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(32))
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class ScamFeedback(Base):
    __tablename__ = "scam_feedback"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    signal_code: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default="")


# --------------------------------------------------------------------------- documents & applications


class GeneratedDocument(Base):
    """Tailored resume or cover letter. `content.items[]` = {id, section, text, supporting_fact_ids}."""

    __tablename__ = "generated_documents"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # resume|cover_letter
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    base_content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounding_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    keyword_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    generator: Mapped[str] = mapped_column(String(64), default="deterministic")
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Application(Base):
    __tablename__ = "applications"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(40), default="saved")
    resume_doc_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generated_documents.id", ondelete="SET NULL"))
    cover_letter_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_documents.id", ondelete="SET NULL")
    )
    adapter_level: Mapped[str] = mapped_column(String(32), default="manual_handoff")
    notes: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        Index("ix_applications_user_status", "user_id", "status"),
    )


class ApplicationActivity(Base):
    """Append-only history. Never updated or deleted except by account hard-deletion."""

    __tablename__ = "application_activities"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str | None] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(16), default="user")  # user|system
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ScreeningAnswer(Base):
    __tablename__ = "screening_answers"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    suggested_answer: Mapped[str | None] = mapped_column(Text)
    supporting_fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    invalidated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    invalidated_reason: Mapped[str | None] = mapped_column(String(255))


class RecruiterContact(Base):
    __tablename__ = "recruiter_contacts"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    company: Mapped[str] = mapped_column(String(200), default="")


class Interview(Base):
    __tablename__ = "interviews"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    kind: Mapped[str] = mapped_column(String(32), default="general")
    notes: Mapped[str] = mapped_column(Text, default="")


class MockInterviewSession(Base):
    __tablename__ = "mock_interview_sessions"
    user_id: Mapped[uuid.UUID] = _user_fk()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    answers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    feedback: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    overall_score: Mapped[float | None] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Reminder(Base):
    __tablename__ = "reminders"
    user_id: Mapped[uuid.UUID] = _user_fk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    message: Mapped[str] = mapped_column(String(500))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(300))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),)


class EmailMessage(Base):
    """Imported email (upload) awaiting triage review. Never replied to automatically."""

    __tablename__ = "email_messages"
    user_id: Mapped[uuid.UUID] = _user_fk()
    message_id: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(500), default="")
    sender: Mapped[str] = mapped_column(String(320), default="")
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    body_text: Mapped[str] = mapped_column(Text, default="")
    classification: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[str] = mapped_column(Text, default="")
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    suggested_status: Mapped[str | None] = mapped_column(String(40))
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|accepted|dismissed
    scam_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    draft_reply: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_email_messages_user_msg"),)


# --------------------------------------------------------------------------- platform


class UserIntegration(Base):
    __tablename__ = "user_integrations"
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(32))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    token_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="connected")


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, default=0.0)
    outcome: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str] = mapped_column(String(64), default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))


class OutboxEvent(Base):
    """Transactional outbox: written in the same transaction as the state change."""

    __tablename__ = "outbox_events"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    dead: Mapped[bool] = mapped_column(Boolean, default=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    user_id: Mapped[uuid.UUID] = _user_fk()
    key: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[Any] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("user_id", "key", "endpoint", name="uq_idempotency_user_key"),)


# Tables a user owns; used by the privacy export / hard-delete verification.
USER_OWNED_MODELS: list[type[Base]] = [
    AuthToken,
    DevMailbox,
    UserProfile,
    UserSettings,
    ConsentRecord,
    Resume,
    ProfileFact,
    UserSkill,
    Job,
    JobEmbedding,
    JobMatch,
    FailedImport,
    ScamFeedback,
    GeneratedDocument,
    Application,
    ApplicationActivity,
    ScreeningAnswer,
    ApprovalRecord,
    RecruiterContact,
    Interview,
    MockInterviewSession,
    Reminder,
    Notification,
    EmailMessage,
    UserIntegration,
    AIUsageLog,
    AuditLog,
    OutboxEvent,
    IdempotencyRecord,
]
