"""Application workflow (spec §10-11): preflight checks, approval checkpoints bound to a payload hash,
manual hand-off, explicit user confirmation of submission, append-only activity history."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, UnprocessableError
from app.models import (
    Application,
    ApplicationActivity,
    ApprovalRecord,
    GeneratedDocument,
    Interview,
    Job,
    Reminder,
    ScreeningAnswer,
)
from app.repositories import Repo
from app.services import profile_service, state_machine
from app.services.documents import content_hash
from app.services.platform import emit
from app.services.skills import extract_skills

UNDO_WINDOW = timedelta(seconds=60)


def _now() -> datetime:
    return datetime.now(UTC)


async def _log(
    session: AsyncSession,
    app: Application,
    action: str,
    from_s: str | None,
    to_s: str | None,
    actor: str = "user",
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        ApplicationActivity(
            user_id=app.user_id,
            application_id=app.id,
            action=action,
            from_status=from_s,
            to_status=to_s,
            actor=actor,
            detail=detail or {},
        )
    )


async def transition(
    session: AsyncSession,
    app: Application,
    target: str,
    via: str = "manual",
    actor: str = "user",
    detail: dict[str, Any] | None = None,
) -> None:
    try:
        state_machine.check_transition(app.status, target, via)
    except state_machine.TransitionError as exc:
        raise Conflict(
            exc.reason,
            code="invalid_transition",
            details={"from": exc.current, "to": exc.target, "allowed": state_machine.allowed_targets(app.status)},
        ) from exc
    previous = app.status
    app.status = target
    app.last_status_at = _now()
    app.version += 1
    if target == "submitted_confirmed":
        app.submitted_at = app.submitted_at or _now()
        session.add(
            Reminder(
                user_id=app.user_id,
                application_id=app.id,
                due_at=_now() + timedelta(days=7),
                message="Follow up on your application if you have not heard back.",
            )
        )
    if previous in ("submitted_confirmed", "ghosted") and target in ("interviewing", "rejected", "offer"):
        app.first_response_at = app.first_response_at or _now()
    if target == "interviewing":
        session.add(
            Interview(
                user_id=app.user_id,
                application_id=app.id,
                kind="general",
                notes="Created when the application moved to Interviewing.",
            )
        )
    await _log(session, app, "status_changed" if via == "manual" else via, previous, target, actor, detail)
    await emit(
        session,
        app.user_id,
        "notify",
        {
            "user_id": str(app.user_id),
            "kind": "status",
            "message": f"Application moved to {target.replace('_', ' ')}",
            "link": f"/applications/{app.id}",
        },
        f"notify:{app.id}:{app.version}",
    )


async def create(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, notes: str = "") -> Application:
    job = await Repo(session, Job, user_id).get(job_id)
    apps = Repo(session, Application, user_id)
    if await apps.find(Application.job_id == job.id) is not None:
        raise Conflict("You already have an application for this job", code="duplicate_application")
    app = apps.add(job_id=job.id, status="saved", notes=notes, last_status_at=_now(), is_demo=job.is_demo)
    try:
        await session.flush()
    except IntegrityError as exc:  # concurrent double-submit hits UNIQUE(user_id, job_id)
        raise Conflict("You already have an application for this job", code="duplicate_application") from exc
    await _log(session, app, "created", None, "saved")
    return app


async def attach_documents(
    session: AsyncSession, app: Application, resume_doc_id: uuid.UUID | None, cover_doc_id: uuid.UUID | None
) -> None:
    if app.status not in state_machine.PRE_SUBMISSION:
        raise Conflict("Documents cannot be changed after submission", code="locked")
    docs = Repo(session, GeneratedDocument, app.user_id)
    if resume_doc_id is not None:
        d = await docs.get(resume_doc_id)
        if d.kind != "resume":
            raise UnprocessableError("That document is not a resume")
        app.resume_doc_id = d.id
    if cover_doc_id is not None:
        d = await docs.get(cover_doc_id)
        if d.kind != "cover_letter":
            raise UnprocessableError("That document is not a cover letter")
        app.cover_letter_doc_id = d.id
    await _log(
        session,
        app,
        "documents_attached",
        app.status,
        app.status,
        detail={
            "resume_doc_id": str(app.resume_doc_id) if app.resume_doc_id else None,
            "cover_letter_doc_id": str(app.cover_letter_doc_id) if app.cover_letter_doc_id else None,
        },
    )
    await invalidate_if_changed(session, app, "Attached documents changed")
    if app.status == "saved":
        await transition(session, app, "tailoring", actor="system")


async def invalidate_if_changed(session: AsyncSession, app: Application, reason: str) -> None:
    """If what the user approved has changed, approval is void and the application returns to review."""
    approvals = await Repo(session, ApprovalRecord, app.user_id).list(
        ApprovalRecord.application_id == app.id, ApprovalRecord.invalidated_at.is_(None)
    )
    if not approvals:
        if app.status == "awaiting_approval":
            await transition(session, app, "ready_for_review", actor="system", detail={"reason": reason})
        return
    current = (await approval_payload(session, app))[1]
    changed = False
    for a in approvals:
        if a.payload_hash != current:
            a.invalidated_at, a.invalidated_reason = _now(), reason
            changed = True
    if changed and app.status in ("approved", "handoff_opened", "awaiting_user_confirmation", "awaiting_approval"):
        await transition(
            session, app, "ready_for_review", actor="system", detail={"reason": f"Approval invalidated: {reason}"}
        )


async def on_document_changed(session: AsyncSession, user_id: uuid.UUID, doc_id: uuid.UUID) -> None:
    apps = await Repo(session, Application, user_id).list(
        (Application.resume_doc_id == doc_id) | (Application.cover_letter_doc_id == doc_id)
    )
    for app in apps:
        if app.status in state_machine.PRE_SUBMISSION:
            await invalidate_if_changed(session, app, "A linked document was edited")


# ------------------------------------------------------------------ screening questions

SENSITIVE_PATTERNS = re.compile(
    r"(authori[sz]ed to work|work authori[sz]ation|visa|sponsor|citizen|immigration|right to work|"
    r"disabilit|veteran|gender|race|ethnic|sexual orientation|religio|date of birth|\bage\b|pregnan|marital|"
    r"salary|compensation|expected ctc|current ctc|pay expectation|desired pay|"
    r"criminal|convicted|felony|background check|arrest)",
    re.I,
)
EXPERIENCE_Q = re.compile(
    r"(experience (with|in|using)|have you (used|worked)|familiar with|proficien|years of|"
    r"degree|education|certif|skills?)",
    re.I,
)


async def classify_question(session: AsyncSession, user_id: uuid.UUID, question: str) -> dict[str, Any]:
    if SENSITIVE_PATTERNS.search(question):
        return {"category": "sensitive_legal", "suggested_answer": None, "supporting_fact_ids": []}
    if EXPERIENCE_Q.search(question):
        facts = await profile_service.confirmed_facts(session, user_id)
        q_skills = {s.lower() for s in extract_skills(question)}
        q_words = {w for w in re.findall(r"[a-z]{4,}", question.lower())} - {
            "experience",
            "have",
            "with",
            "years",
            "using",
            "your",
            "work",
            "worked",
        }
        relevant = []
        for f in facts:
            f_skills = {s.lower() for s in profile_service.fact_skills(f)}
            if (q_skills and q_skills & f_skills) or (not q_skills and q_words & set(f.text.lower().split())):
                relevant.append(f)
        if relevant:
            top = relevant[:2]
            answer = "Yes. " + " ".join(f.text.rstrip(".") + "." for f in top)
            return {
                "category": "answerable_from_verified_facts",
                "suggested_answer": answer,
                "supporting_fact_ids": [str(f.id) for f in top],
            }
    return {"category": "needs_user_input", "suggested_answer": None, "supporting_fact_ids": []}


async def add_question(session: AsyncSession, app: Application, question: str) -> ScreeningAnswer:
    if app.status not in state_machine.PRE_SUBMISSION:
        raise Conflict("Screening answers are locked after submission", code="locked")
    c = await classify_question(session, app.user_id, question)
    row = Repo(session, ScreeningAnswer, app.user_id).add(
        application_id=app.id,
        question=question.strip()[:1000],
        category=c["category"],
        suggested_answer=c["suggested_answer"],
        supporting_fact_ids=c["supporting_fact_ids"],
    )
    await session.flush()
    await invalidate_if_changed(session, app, "Screening questions changed")
    return row


async def answer_question(
    session: AsyncSession, app: Application, answer_id: uuid.UUID, answer: str
) -> ScreeningAnswer:
    if app.status not in state_machine.PRE_SUBMISSION:
        raise Conflict("Screening answers are locked after submission", code="locked")
    row = await Repo(session, ScreeningAnswer, app.user_id).get(answer_id)
    if row.application_id != app.id:
        raise UnprocessableError("Answer does not belong to this application")
    row.answer, row.answered_by_user = answer.strip()[:4000], True
    await session.flush()
    await invalidate_if_changed(session, app, "A screening answer changed")
    return row


# ------------------------------------------------------------------ approval & submission


async def approval_payload(session: AsyncSession, app: Application) -> tuple[dict[str, Any], str]:
    job = await Repo(session, Job, app.user_id).get(app.job_id)
    docs = Repo(session, GeneratedDocument, app.user_id)
    resume = await docs.get(app.resume_doc_id) if app.resume_doc_id else None
    cover = await docs.get(app.cover_letter_doc_id) if app.cover_letter_doc_id else None
    answers = await Repo(session, ScreeningAnswer, app.user_id).list(
        ScreeningAnswer.application_id == app.id, order_by=ScreeningAnswer.created_at
    )
    payload = {
        "job": {"id": str(job.id), "title": job.title, "company": job.company, "url": job.url},
        "resume": {"id": str(resume.id), "hash": content_hash(resume.content)} if resume else None,
        "cover_letter": {"id": str(cover.id), "hash": content_hash(cover.content)} if cover else None,
        "screening_answers": [{"question": a.question, "answer": a.answer} for a in answers],
        "adapter_level": app.adapter_level,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload, digest


async def preflight(session: AsyncSession, app: Application) -> dict[str, Any]:
    job = await Repo(session, Job, app.user_id).get(app.job_id)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, blocking: bool, message: str) -> None:
        checks.append({"name": name, "ok": ok, "blocking": blocking and not ok, "message": message})

    status = job.verification_status
    add(
        "listing_live",
        status not in ("expired",),
        True,
        {
            "verified_live": "Listing was verified live",
            "unverified": "Listing could not be verified automatically - " "check that it is still open",
            "expired": "Listing appears to have been removed",
            "unavailable": "Listing could not be reached; check it manually",
        }.get(status, status),
    )
    dup_ids = [job.potential_duplicate_of] if job.potential_duplicate_of else []
    dup_ids += [j.id for j in await Repo(session, Job, app.user_id).list(Job.potential_duplicate_of == job.id)]
    dup_apps = await Repo(session, Application, app.user_id).list(Application.job_id.in_(dup_ids)) if dup_ids else []
    add(
        "duplicate_application",
        not dup_apps,
        False,
        "You may already have applied to this role via another listing"
        if dup_apps
        else "No duplicate application found",
    )
    docs = Repo(session, GeneratedDocument, app.user_id)
    resume = await docs.get(app.resume_doc_id) if app.resume_doc_id else None
    add("resume_attached", resume is not None, True, "A resume is attached" if resume else "Attach a resume")
    if resume is not None:
        add(
            "resume_grounded",
            resume.grounded,
            True,
            "Every resume item is supported by your verified facts"
            if resume.grounded
            else "Some resume items failed grounding checks - fix them in Resume Studio",
        )
    if app.cover_letter_doc_id:
        cover = await docs.get(app.cover_letter_doc_id)
        add(
            "cover_letter_grounded",
            cover.grounded,
            True,
            "Cover letter passed grounding checks" if cover.grounded else "Cover letter has unsupported claims",
        )
    answers = await Repo(session, ScreeningAnswer, app.user_id).list(ScreeningAnswer.application_id == app.id)
    unanswered = [a.question for a in answers if not a.answered_by_user or not (a.answer or "").strip()]
    add(
        "screening_answered",
        not unanswered,
        True,
        "All screening questions answered by you"
        if not unanswered
        else f"{len(unanswered)} screening question(s) still need your answer",
    )
    return {"ok": not any(c["blocking"] for c in checks), "checks": checks}


async def mark_ready(session: AsyncSession, app: Application) -> None:
    if app.resume_doc_id is None:
        raise UnprocessableError("Attach a resume before marking the application ready", code="resume_required")
    await transition(session, app, "ready_for_review")


async def request_approval(session: AsyncSession, app: Application) -> dict[str, Any]:
    pf = await preflight(session, app)
    if not pf["ok"]:
        raise Conflict("Pre-flight checks failed", code="preflight_failed", details=pf)
    await transition(session, app, "awaiting_approval")
    payload, digest = await approval_payload(session, app)
    return {"payload": payload, "payload_hash": digest, "preflight": pf}


async def approve(session: AsyncSession, app: Application, payload_hash: str) -> ApprovalRecord:
    if app.status != "awaiting_approval":
        raise Conflict("Request approval first", code="invalid_transition")
    pf = await preflight(session, app)
    if not pf["ok"]:
        raise Conflict("Pre-flight checks failed", code="preflight_failed", details=pf)
    payload, digest = await approval_payload(session, app)
    if payload_hash != digest:
        raise Conflict(
            "What you reviewed has changed since it was shown. Review it again before approving.",
            code="payload_changed",
            details={"current_hash": digest},
        )
    record = Repo(session, ApprovalRecord, app.user_id).add(
        application_id=app.id, action="approve_application_package", payload_hash=digest, payload_summary=payload
    )
    await session.flush()
    await transition(
        session, app, "approved", via="approval", detail={"approval_id": str(record.id), "payload_hash": digest}
    )
    return record


async def _valid_approval(session: AsyncSession, app: Application) -> ApprovalRecord:
    _, digest = await approval_payload(session, app)
    rec = await Repo(session, ApprovalRecord, app.user_id).find(
        ApprovalRecord.application_id == app.id,
        ApprovalRecord.invalidated_at.is_(None),
        ApprovalRecord.payload_hash == digest,
    )
    if rec is None:
        await invalidate_if_changed(session, app, "Payload no longer matches approval")
        raise Conflict(
            "Approval is missing or no longer matches the application. Review and approve again.",
            code="approval_invalid",
        )
    return rec


async def open_handoff(session: AsyncSession, app: Application) -> dict[str, Any]:
    """Manual hand-off: returns the employer's URL for the user to open. Never submits anything."""
    rec = await _valid_approval(session, app)
    job = await Repo(session, Job, app.user_id).get(app.job_id)
    await transition(session, app, "handoff_opened", via="handoff", detail={"approval_id": str(rec.id)})
    await transition(session, app, "awaiting_user_confirmation", via="handoff", actor="system")
    return {
        "url": job.url,
        "instructions": "Complete and submit the employer's form yourself. JobPilot never clicks "
        "the final submit button. Come back and confirm once you have submitted.",
    }


async def confirm_submission(session: AsyncSession, app: Application, confirmed: bool, note: str = "") -> None:
    if not confirmed:
        raise UnprocessableError("Submission must be explicitly confirmed", code="confirmation_required")
    rec = await _valid_approval(session, app)
    await transition(
        session,
        app,
        "submitted_confirmed",
        via="user_confirmation",
        detail={"approval_id": str(rec.id), "note": note[:500], "confirmed_by": "user"},
    )


async def undo_last_move(session: AsyncSession, app: Application) -> None:
    """Revert the most recent manual Kanban move if it happened within the undo window."""
    last = (
        await session.execute(
            select(ApplicationActivity)
            .where(ApplicationActivity.application_id == app.id, ApplicationActivity.user_id == app.user_id)
            .order_by(ApplicationActivity.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        last is None
        or last.action != "status_changed"
        or last.actor != "user"
        or _now() - last.created_at > UNDO_WINDOW
        or last.to_status != app.status
        or last.from_status is None
    ):
        raise Conflict("Nothing to undo", code="undo_unavailable")
    previous = app.status
    app.status, app.version, app.last_status_at = last.from_status, app.version + 1, _now()
    await _log(session, app, "undo", previous, last.from_status, detail={"undid_activity": str(last.id)})


def app_dict(app: Application, job: Job | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": str(app.id),
        "job_id": str(app.job_id),
        "status": app.status,
        "resume_doc_id": str(app.resume_doc_id) if app.resume_doc_id else None,
        "cover_letter_doc_id": str(app.cover_letter_doc_id) if app.cover_letter_doc_id else None,
        "adapter_level": app.adapter_level,
        "notes": app.notes,
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "last_status_at": app.last_status_at.isoformat() if app.last_status_at else None,
        "created_at": app.created_at.isoformat(),
        "version": app.version,
        "is_demo": app.is_demo,
        "allowed_moves": state_machine.allowed_targets(app.status),
    }
    if job is not None:
        d["job"] = {
            "id": str(job.id),
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "location": job.location,
            "source": job.source,
        }
    return d
