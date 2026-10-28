from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import agents
from app.models import Application, ApplicationActivity, ApprovalRecord, Interview, Job, Reminder, ScreeningAnswer
from app.repositories import Repo, paginate
from app.routers._idem import idempotent
from app.security.deps import CurrentUser, SessionDep, check_if_match, etag_for, parse_uuid, rate_limit
from app.services import applications as svc
from app.services import state_machine, tasks
from app.services.platform import audit

router = APIRouter(prefix="/api", tags=["applications"])


class CreateIn(BaseModel):
    job_id: str
    notes: str = Field(default="", max_length=4000)


class AttachIn(BaseModel):
    resume_doc_id: str | None = None
    cover_letter_doc_id: str | None = None


class MoveIn(BaseModel):
    status: str


class ApproveIn(BaseModel):
    payload_hash: str = Field(min_length=64, max_length=64)


class ConfirmIn(BaseModel):
    confirmed: Literal[True]
    note: str = Field(default="", max_length=500)


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class NotesIn(BaseModel):
    notes: str = Field(max_length=4000)


class ReminderIn(BaseModel):
    due_at: datetime
    message: str = Field(min_length=1, max_length=500)


async def _app(session: Any, user: Any, app_id: str) -> Application:
    return await Repo(session, Application, user.id).get(parse_uuid(app_id))


async def _full(session: Any, user: Any, app: Application) -> dict[str, Any]:
    job = await Repo(session, Job, user.id).get(app.job_id)
    d = svc.app_dict(app, job)
    acts = await Repo(session, ApplicationActivity, user.id).list(
        ApplicationActivity.application_id == app.id, order_by=ApplicationActivity.created_at
    )
    d["activity"] = [
        {
            "id": str(a.id),
            "action": a.action,
            "from": a.from_status,
            "to": a.to_status,
            "actor": a.actor,
            "detail": a.detail,
            "at": a.created_at.isoformat(),
        }
        for a in acts
    ]
    answers = await Repo(session, ScreeningAnswer, user.id).list(
        ScreeningAnswer.application_id == app.id, order_by=ScreeningAnswer.created_at
    )
    d["screening"] = [
        {
            "id": str(a.id),
            "question": a.question,
            "category": a.category,
            "suggested_answer": a.suggested_answer,
            "supporting_fact_ids": a.supporting_fact_ids,
            "answer": a.answer,
            "answered_by_user": a.answered_by_user,
        }
        for a in answers
    ]
    approvals = await Repo(session, ApprovalRecord, user.id).list(
        ApprovalRecord.application_id == app.id, order_by=ApprovalRecord.created_at
    )
    d["approvals"] = [
        {
            "id": str(a.id),
            "payload_hash": a.payload_hash,
            "approved_at": a.created_at.isoformat(),
            "invalidated_at": a.invalidated_at.isoformat() if a.invalidated_at else None,
            "invalidated_reason": a.invalidated_reason,
        }
        for a in approvals
    ]
    d["preflight"] = await svc.preflight(session, app) if app.status in state_machine.PRE_SUBMISSION else None
    payload, digest = await svc.approval_payload(session, app)
    d["approval_payload"], d["approval_payload_hash"] = payload, digest
    reminders = await Repo(session, Reminder, user.id).list(Reminder.application_id == app.id, order_by=Reminder.due_at)
    d["reminders"] = [
        {"id": str(r.id), "due_at": r.due_at.isoformat(), "message": r.message, "done": r.done} for r in reminders
    ]
    return d


@router.get("/applications")
async def list_applications(
    user: CurrentUser,
    session: SessionDep,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    q = select(Application).where(Application.user_id == user.id)
    if status:
        q = q.where(Application.status == status)
    rows, next_cursor = await paginate(session, q, Application, cursor, limit)
    jobs = (
        {j.id: j for j in await Repo(session, Job, user.id).list(Job.id.in_([r.job_id for r in rows]))} if rows else {}
    )
    return {
        "items": [svc.app_dict(a, jobs.get(a.job_id)) for a in rows],
        "next_cursor": next_cursor,
        "columns": {k: list(v) for k, v in state_machine.KANBAN_COLUMNS.items()},
    }


@router.post("/applications")
async def create_application(body: CreateIn, request: Request, user: CurrentUser, session: SessionDep) -> JSONResponse:
    async def run() -> dict[str, Any]:
        app = await svc.create(session, user.id, parse_uuid(body.job_id), body.notes)
        return svc.app_dict(app)

    return await idempotent(request, session, user, "applications:create", body.model_dump(), run)


@router.get("/applications/{app_id}")
async def get_application(app_id: str, user: CurrentUser, session: SessionDep, response: Response) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    response.headers["ETag"] = etag_for(app.version)
    return await _full(session, user, app)


@router.patch("/applications/{app_id}/notes")
async def update_notes(
    app_id: str, body: NotesIn, request: Request, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    check_if_match(request, app.version)
    app.notes, app.version = body.notes, app.version + 1
    return svc.app_dict(app)


@router.post("/applications/{app_id}/prepare", dependencies=[rate_limit("ai")])
async def prepare(app_id: str, request: Request, user: CurrentUser, session: SessionDep) -> JSONResponse:
    app = await _app(session, user, app_id)

    async def run() -> dict[str, Any]:
        out = await agents.preparation.run(
            session, user.id, agents.PreparationInput(application_id=str(app.id), email=user.email)
        )
        return out.model_dump()

    return await idempotent(request, session, user, f"applications:prepare:{app.id}", {"v": app.version}, run)


@router.put("/applications/{app_id}/documents")
async def attach(app_id: str, body: AttachIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.attach_documents(
        session,
        app,
        parse_uuid(body.resume_doc_id) if body.resume_doc_id else None,
        parse_uuid(body.cover_letter_doc_id) if body.cover_letter_doc_id else None,
    )
    return await _full(session, user, app)


@router.post("/applications/{app_id}/ready")
async def mark_ready(app_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.mark_ready(session, app)
    return await _full(session, user, app)


@router.post("/applications/{app_id}/request-approval")
async def request_approval(app_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    return await svc.request_approval(session, app)


@router.post("/applications/{app_id}/approve")
async def approve(
    app_id: str, body: ApproveIn, request: Request, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    rec = await svc.approve(session, app, body.payload_hash)
    audit(
        session,
        user.id,
        "application.approved",
        str(app.id),
        {"approval_id": str(rec.id), "payload_hash": rec.payload_hash},
        request,
    )
    return await _full(session, user, app)


@router.post("/applications/{app_id}/handoff")
async def handoff(app_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    return await svc.open_handoff(session, app)


@router.post("/applications/{app_id}/confirm-submission")
async def confirm(
    app_id: str, body: ConfirmIn, request: Request, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.confirm_submission(session, app, body.confirmed, body.note)
    audit(session, user.id, "application.submission_confirmed", str(app.id), {}, request)
    await tasks.run_inline(session, user.id)
    return await _full(session, user, app)


@router.post("/applications/{app_id}/move")
async def move(app_id: str, body: MoveIn, request: Request, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    check_if_match(request, app.version)
    await agents.tracking.run(session, user.id, agents.TrackingInput(application_id=str(app.id), target=body.status))
    await tasks.run_inline(session, user.id)
    return svc.app_dict(app)


@router.post("/applications/{app_id}/undo")
async def undo(app_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.undo_last_move(session, app)
    return svc.app_dict(app)


@router.post("/applications/{app_id}/screening", status_code=201)
async def add_question(app_id: str, body: QuestionIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.add_question(session, app, body.question)
    return await _full(session, user, app)


@router.put("/applications/{app_id}/screening/{answer_id}")
async def answer_question(
    app_id: str, answer_id: str, body: AnswerIn, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    await svc.answer_question(session, app, parse_uuid(answer_id), body.answer)
    return await _full(session, user, app)


@router.post("/applications/{app_id}/reminders", status_code=201)
async def add_reminder(app_id: str, body: ReminderIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    app = await _app(session, user, app_id)
    r = Repo(session, Reminder, user.id).add(application_id=app.id, due_at=body.due_at, message=body.message)
    await session.flush()
    return {"id": str(r.id), "due_at": r.due_at.isoformat(), "message": r.message, "done": r.done}


@router.get("/reminders")
async def list_reminders(user: CurrentUser, session: SessionDep, include_done: bool = False) -> list[dict[str, Any]]:
    where = [] if include_done else [Reminder.done.is_(False)]
    rows = await Repo(session, Reminder, user.id).list(*where, order_by=Reminder.due_at, limit=200)
    return [
        {
            "id": str(r.id),
            "application_id": str(r.application_id) if r.application_id else None,
            "due_at": r.due_at.isoformat(),
            "message": r.message,
            "done": r.done,
        }
        for r in rows
    ]


@router.post("/reminders/{reminder_id}/done")
async def reminder_done(reminder_id: str, user: CurrentUser, session: SessionDep) -> dict[str, bool]:
    r = await Repo(session, Reminder, user.id).get(parse_uuid(reminder_id))
    r.done = True
    return {"ok": True}


@router.get("/interviews")
async def list_interviews(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await Repo(session, Interview, user.id).list(order_by=Interview.created_at.desc(), limit=100)
    return [
        {
            "id": str(i.id),
            "application_id": str(i.application_id) if i.application_id else None,
            "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
            "kind": i.kind,
            "notes": i.notes,
        }
        for i in rows
    ]
