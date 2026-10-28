"""Email Triage (spec §12): classify uploaded emails and produce *suggested* tracker updates with
evidence. Suggestions are applied only when the user accepts them in the review queue. Replies are
drafted for copy/paste - never sent."""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import service as ai
from app.ai.prompts import untrusted
from app.errors import Conflict
from app.models import Application, EmailMessage, Job
from app.repositories import Repo
from app.services import applications as app_service
from app.services import scam_signals, state_machine
from app.services.email_import import ParsedEmail
from app.services.fingerprint import normalize_company

Classification = Literal["job_alert", "interview_invite", "assessment", "rejection", "recruiter_reply", "other"]

RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "rejection",
        re.compile(
            r"unfortunately|not (be )?moving forward|decided to (move|proceed) with other|"
            r"not been selected|not selected|regret to inform|position has been filled|"
            r"will not be progressing|pursue other candidates",
            re.I,
        ),
    ),
    (
        "interview_invite",
        re.compile(
            r"\binterview\b|schedule (a|some) time|phone screen|availability for a call|"
            r"calendly\.com|meet with (the|our) team|book a (call|slot)",
            re.I,
        ),
    ),
    (
        "assessment",
        re.compile(
            r"assessment|coding challenge|take[- ]home|hackerrank|codility|codesignal|"
            r"online test|technical exercise",
            re.I,
        ),
    ),
    (
        "job_alert",
        re.compile(
            r"job alert|new jobs|jobs (matching|for you)|recommended jobs|\d+ new (jobs|positions|roles)|"
            r"jobs you may be interested",
            re.I,
        ),
    ),
    (
        "recruiter_reply",
        re.compile(
            r"thank you for (applying|your application|your interest)|received your application|"
            r"application (has been )?received|following up on your application|"
            r"i came across your profile",
            re.I,
        ),
    ),
]
SUGGESTED_STATUS = {"interview_invite": "interviewing", "assessment": "interviewing", "rejection": "rejected"}


class TriageOut(BaseModel):
    classification: Classification
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(max_length=400)


def classify_rules(subject: str, body: str) -> TriageOut:
    text = f"{subject}\n{body}"
    for label, pattern in RULES:
        hits = list(pattern.finditer(text))
        if hits:
            m = hits[0]
            s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
            return TriageOut(
                classification=label,
                confidence=min(0.95, 0.55 + 0.1 * len(hits)),
                evidence=text[s:e].replace("\n", " ").strip(),
            )
    return TriageOut(classification="other", confidence=0.4, evidence=subject[:200])


async def _match_application(session: AsyncSession, user_id: uuid.UUID, parsed: ParsedEmail) -> Application | None:
    apps = await Repo(session, Application, user_id).list(order_by=Application.created_at.desc())
    if not apps:
        return None
    haystack = f"{parsed.subject} {parsed.sender} {parsed.text[:3000]}".lower()
    sender_domain = parsed.sender.split("@")[-1] if "@" in parsed.sender else ""
    jobs = Repo(session, Job, user_id)
    for app in apps:
        job = await jobs.get(app.job_id)
        comp = normalize_company(job.company)
        if comp and (comp in normalize_company(haystack) or comp.replace(" ", "") in sender_domain.replace("-", "")):
            return app
    return None


def draft_reply(classification: str, subject: str, name: str) -> str | None:
    sign = f"\n\nBest regards,\n{name}" if name else "\n\nBest regards,"
    if classification == "interview_invite":
        return (
            f"Subject: Re: {subject}\n\nHello,\n\nThank you for the invitation - I would be glad to interview. "
            f"I am available at the following times: [add your availability]. Please let me know what works best."
            f"{sign}"
        )
    if classification == "assessment":
        return (
            f"Subject: Re: {subject}\n\nHello,\n\nThank you for sending the assessment. I will complete it by "
            f"[date]. Could you confirm any time limit or tools I should use?{sign}"
        )
    if classification == "rejection":
        return (
            f"Subject: Re: {subject}\n\nHello,\n\nThank you for letting me know and for your time during the "
            f"process. I would appreciate being considered for future roles that fit my background.{sign}"
        )
    if classification == "recruiter_reply":
        return f"Subject: Re: {subject}\n\nHello,\n\nThank you for your message. [Write your reply here.]{sign}"
    return None


async def ingest(
    session: AsyncSession, user_id: uuid.UUID, messages: list[ParsedEmail], name: str
) -> list[EmailMessage]:
    repo = Repo(session, EmailMessage, user_id)
    out: list[EmailMessage] = []
    for parsed in messages:
        existing = await repo.find(EmailMessage.message_id == parsed.message_id)
        if existing is not None:
            out.append(existing)
            continue
        rules = classify_rules(parsed.subject, parsed.text)
        result = await ai.generate_structured(
            session,
            user_id,
            "triage_email",
            TriageOut,
            {"email": untrusted("email", f"Subject: {parsed.subject}\nFrom: {parsed.sender}\n\n{parsed.text[:6000]}")},
            fallback=lambda r=rules: r,  # type: ignore[misc]
        )
        tri = result.value
        app = await _match_application(session, user_id, parsed)
        suggestion = SUGGESTED_STATUS.get(tri.classification)
        if app is None or suggestion is None or suggestion not in state_machine.allowed_targets(app.status):
            suggestion = None
        domain_company = ""
        if app is not None:
            domain_company = (await Repo(session, Job, user_id).get(app.job_id)).company
        msg = repo.add(
            message_id=parsed.message_id,
            subject=parsed.subject,
            sender=parsed.sender,
            received_at=parsed.received_at,
            body_text=parsed.text,
            classification=tri.classification,
            confidence=tri.confidence,
            evidence=tri.evidence,
            application_id=app.id if app else None,
            suggested_status=suggestion,
            review_status="pending" if suggestion else "info",
            scam_report=scam_signals.analyze(f"{parsed.subject}\n{parsed.text}", domain_company, parsed.sender),
            draft_reply=draft_reply(tri.classification, parsed.subject, name),
        )
        out.append(msg)
    await session.flush()
    return out


async def accept(session: AsyncSession, user_id: uuid.UUID, msg: EmailMessage) -> Application:
    if msg.review_status != "pending" or not msg.suggested_status or not msg.application_id:
        raise Conflict("This suggestion is no longer pending", code="not_pending")
    app = await Repo(session, Application, user_id).get(msg.application_id)
    await app_service.transition(
        session,
        app,
        msg.suggested_status,
        detail={"source": "email_triage", "message_id": msg.message_id, "evidence": msg.evidence[:300]},
    )
    msg.review_status = "accepted"
    return app


def email_dict(m: EmailMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "message_id": m.message_id,
        "subject": m.subject,
        "sender": m.sender,
        "received_at": m.received_at.isoformat() if m.received_at else None,
        "classification": m.classification,
        "confidence": m.confidence,
        "evidence": m.evidence,
        "snippet": m.body_text[:400],
        "application_id": str(m.application_id) if m.application_id else None,
        "suggested_status": m.suggested_status,
        "review_status": m.review_status,
        "scam_report": m.scam_report,
        "draft_reply": m.draft_reply,
        "created_at": m.created_at.isoformat(),
    }
