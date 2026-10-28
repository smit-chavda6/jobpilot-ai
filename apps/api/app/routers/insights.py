"""Email triage, interview prep and analytics endpoints."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from app import agents
from app.models import EmailMessage, Job, MockInterviewSession
from app.repositories import Repo
from app.security.deps import CurrentUser, SessionDep, parse_uuid, rate_limit
from app.services import analytics, ingestion, interview_prep, profile_service, tasks, triage
from app.services.email_import import ParsedEmail, parse_email_upload

router = APIRouter(prefix="/api", tags=["insights"])


# ------------------------------------------------------------------ triage


@router.post("/triage/upload", status_code=201, dependencies=[rate_limit("upload")])
async def triage_upload(user: CurrentUser, session: SessionDep, file: UploadFile = File(...)) -> list[dict[str, Any]]:
    messages = parse_email_upload(file.filename or "", await file.read())
    profile = await profile_service.get_profile(session, user.id)
    out = await agents.email_triage.run(
        session, user.id, agents.TriageInput(messages=[asdict(m) for m in messages], name=profile.full_name or "")
    )
    return out.emails


@router.get("/triage")
async def triage_list(user: CurrentUser, session: SessionDep, status: str | None = None) -> list[dict[str, Any]]:
    where = [EmailMessage.review_status == status] if status else []
    rows = await Repo(session, EmailMessage, user.id).list(*where, order_by=EmailMessage.created_at.desc(), limit=200)
    return [triage.email_dict(r) for r in rows]


@router.post("/triage/{email_id}/accept")
async def triage_accept(email_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    msg = await Repo(session, EmailMessage, user.id).get(parse_uuid(email_id))
    app = await triage.accept(session, user.id, msg)
    await tasks.run_inline(session, user.id)
    return {"email": triage.email_dict(msg), "application_status": app.status}


@router.post("/triage/{email_id}/dismiss")
async def triage_dismiss(email_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    msg = await Repo(session, EmailMessage, user.id).get(parse_uuid(email_id))
    msg.review_status = "dismissed"
    return triage.email_dict(msg)


@router.post("/triage/{email_id}/import-jobs")
async def triage_import_jobs(email_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    msg = await Repo(session, EmailMessage, user.id).get(parse_uuid(email_id))
    links = [("", u) for u in re.findall(r"https?://[^\s<>\")]+", msg.body_text)]
    parsed = ParsedEmail(msg.message_id, msg.subject, msg.sender, msg.received_at, msg.body_text, links)
    report = await ingestion.import_emails(session, user.id, [parsed])
    await tasks.run_inline(session, user.id)
    return report.as_dict()


# ------------------------------------------------------------------ interview prep


@router.get("/interview-prep/bank")
async def bank(user: CurrentUser, session: SessionDep, job_id: str | None = None) -> dict[str, Any]:
    job = await Repo(session, Job, user.id).get(parse_uuid(job_id)) if job_id else None
    facts = await profile_service.confirmed_facts(session, user.id)
    return interview_prep.question_bank(job, facts)


class StarIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    job_id: str | None = None


@router.post("/interview-prep/star")
async def star(body: StarIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    job = await Repo(session, Job, user.id).get(parse_uuid(body.job_id)) if body.job_id else None
    facts = await profile_service.confirmed_facts(session, user.id)
    skills = (job.required_skills or []) + (job.preferred_skills or []) if job else []
    return interview_prep.star_scaffold(body.question, facts, skills)


class SessionIn(BaseModel):
    job_id: str | None = None
    questions: int = Field(default=5, ge=1, le=10)


@router.post("/interview-prep/sessions", status_code=201)
async def create_session(body: SessionIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    if body.job_id:
        parse_uuid(body.job_id)
    out = await agents.interview.run(
        session, user.id, agents.InterviewPrepInput(job_id=body.job_id, questions=body.questions)
    )
    return out.session


@router.get("/interview-prep/sessions")
async def list_sessions(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await Repo(session, MockInterviewSession, user.id).list(order_by=MockInterviewSession.created_at)
    return [interview_prep.session_dict(s) for s in rows]


@router.get("/interview-prep/sessions/{session_id}")
async def get_session(session_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    s = await Repo(session, MockInterviewSession, user.id).get(parse_uuid(session_id))
    return interview_prep.session_dict(s)


class AnswerIn(BaseModel):
    question_id: str = Field(max_length=10)
    answer: str = Field(min_length=1, max_length=6000)


@router.post("/interview-prep/sessions/{session_id}/answers")
async def answer(session_id: str, body: AnswerIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    s = await Repo(session, MockInterviewSession, user.id).get(parse_uuid(session_id))
    feedback = await interview_prep.submit_answer(session, user.id, s, body.question_id, body.answer)
    return {"feedback": feedback, "session": interview_prep.session_dict(s)}


# ------------------------------------------------------------------ analytics


@router.get("/analytics")
async def get_analytics(user: CurrentUser, session: SessionDep, include_demo: bool = True) -> dict[str, Any]:
    return await analytics.compute(session, user.id, include_demo)
