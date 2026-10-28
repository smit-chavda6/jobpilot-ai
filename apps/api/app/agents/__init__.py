"""Agents (spec §10): typed `run(input) -> output` units with a timeout and retry policy.

Agents never touch the database directly - they call services. LLM output inside agents can
only *propose* content; side effects (status changes, persistence) are enforced by services and
the state machine. The orchestrator is the persisted application workflow in
app/services/applications.py + app/services/state_machine.py (ADR-0004).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import applications, documents, ingestion, interview_prep, match_service, profile_service, triage
from app.services.email_import import ParsedEmail


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1  # >1 only for idempotent agents
    timeout_seconds: float = 60.0


class AgentTimeout(Exception):
    pass


class Agent[I: BaseModel, O: BaseModel]:
    name: str = "agent"
    policy = RetryPolicy()

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: I) -> O:
        raise NotImplementedError

    async def run(self, session: AsyncSession, user_id: uuid.UUID, data: I) -> O:
        last: Exception | None = None
        for _ in range(max(1, self.policy.attempts)):
            try:
                return await asyncio.wait_for(self._run(session, user_id, data), self.policy.timeout_seconds)
            except TimeoutError as exc:
                last = AgentTimeout(f"{self.name} timed out")
                last.__cause__ = exc
        assert last is not None
        raise last


# ------------------------------------------------------------------ agents


class DiscoveryInput(BaseModel):
    source: str
    params: dict[str, Any]


class DiscoveryOutput(BaseModel):
    report: dict[str, Any]


class DiscoveryAgent(Agent[DiscoveryInput, DiscoveryOutput]):
    name = "discovery"
    policy = RetryPolicy(attempts=1, timeout_seconds=90)  # fetch-level retries live in safe_fetch

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: DiscoveryInput) -> DiscoveryOutput:
        report = await ingestion.run_import(session, user_id, data.source, data.params)
        return DiscoveryOutput(report=report.as_dict())


class ResumeParsingInput(BaseModel):
    filename: str
    mime: str | None
    data: bytes


class ResumeParsingOutput(BaseModel):
    resume_id: str
    parse_status: str
    parse_error: str | None
    facts: list[dict[str, Any]]
    suggestions: dict[str, Any]


class ResumeParsingAgent(Agent[ResumeParsingInput, ResumeParsingOutput]):
    name = "resume_parsing"
    policy = RetryPolicy(attempts=1, timeout_seconds=60)

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: ResumeParsingInput) -> ResumeParsingOutput:
        resume, facts, suggestions = await profile_service.upload_resume(
            session, user_id, data.filename, data.mime, data.data
        )
        await session.flush()
        return ResumeParsingOutput(
            resume_id=str(resume.id),
            parse_status=resume.parse_status,
            parse_error=resume.parse_error,
            facts=[profile_service.fact_dict(f) for f in facts],
            suggestions=suggestions,
        )


class MatchingInput(BaseModel):
    job_ids: list[str] | None = None


class MatchingOutput(BaseModel):
    scored: int


class MatchingAgent(Agent[MatchingInput, MatchingOutput]):
    name = "matching"
    policy = RetryPolicy(attempts=2, timeout_seconds=120)  # idempotent upsert

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: MatchingInput) -> MatchingOutput:
        return MatchingOutput(scored=await match_service.score_jobs(session, user_id))


class PreparationInput(BaseModel):
    application_id: str
    email: str
    include_cover_letter: bool = True


class PreparationOutput(BaseModel):
    resume_doc_id: str
    cover_letter_doc_id: str | None
    grounded: bool


class ApplicationPreparationAgent(Agent[PreparationInput, PreparationOutput]):
    name = "application_preparation"
    policy = RetryPolicy(attempts=1, timeout_seconds=120)

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: PreparationInput) -> PreparationOutput:
        from app.models import Application
        from app.repositories import Repo

        app = await Repo(session, Application, user_id).get(uuid.UUID(data.application_id))
        resume = await documents.generate_resume(session, user_id, data.email, app.job_id)
        cover = (
            await documents.generate_cover_letter(session, user_id, data.email, app.job_id)
            if data.include_cover_letter
            else None
        )
        await applications.attach_documents(session, app, resume.id, cover.id if cover else None)
        return PreparationOutput(
            resume_doc_id=str(resume.id),
            cover_letter_doc_id=str(cover.id) if cover else None,
            grounded=resume.grounded and (cover.grounded if cover else True),
        )


class TriageInput(BaseModel):
    messages: list[dict[str, Any]]
    name: str = ""


class TriageOutput(BaseModel):
    emails: list[dict[str, Any]]


class EmailTriageAgent(Agent[TriageInput, TriageOutput]):
    name = "email_triage"
    policy = RetryPolicy(attempts=1, timeout_seconds=90)

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: TriageInput) -> TriageOutput:
        msgs = [ParsedEmail(**m) for m in data.messages]
        rows = await triage.ingest(session, user_id, msgs, data.name)
        return TriageOutput(emails=[triage.email_dict(r) for r in rows])


class InterviewPrepInput(BaseModel):
    job_id: str | None = None
    questions: int = 5


class InterviewPrepOutput(BaseModel):
    session: dict[str, Any]


class InterviewPrepAgent(Agent[InterviewPrepInput, InterviewPrepOutput]):
    name = "interview_prep"
    policy = RetryPolicy(attempts=1, timeout_seconds=30)

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: InterviewPrepInput) -> InterviewPrepOutput:
        s = await interview_prep.create_session(
            session, user_id, uuid.UUID(data.job_id) if data.job_id else None, data.questions
        )
        return InterviewPrepOutput(session=interview_prep.session_dict(s))


class TrackingInput(BaseModel):
    application_id: str
    target: str


class TrackingOutput(BaseModel):
    status: str


class ApplicationTrackingAgent(Agent[TrackingInput, TrackingOutput]):
    """Moves applications through *non-gated* transitions only (the state machine enforces gates)."""

    name = "application_tracking"

    async def _run(self, session: AsyncSession, user_id: uuid.UUID, data: TrackingInput) -> TrackingOutput:
        from app.models import Application
        from app.repositories import Repo

        app = await Repo(session, Application, user_id).get(uuid.UUID(data.application_id))
        await applications.transition(session, app, data.target)
        return TrackingOutput(status=app.status)


discovery = DiscoveryAgent()
resume_parsing = ResumeParsingAgent()
matching = MatchingAgent()
preparation = ApplicationPreparationAgent()
email_triage = EmailTriageAgent()
interview = InterviewPrepAgent()
tracking = ApplicationTrackingAgent()
