"""Settings, privacy (export / hard delete), notifications, AI budget, integrations, dashboard summary."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.ai.service import budget_status
from app.config import get_settings
from app.models import (
    Application,
    EmailMessage,
    Job,
    JobMatch,
    Notification,
    ProfileFact,
    Reminder,
    UserIntegration,
)
from app.repositories import Repo
from app.routers.auth import _clear_session_cookies
from app.security.deps import CurrentUser, SessionDep, parse_uuid, require_recent_reauth
from app.services import privacy, profile_service
from app.services.platform import audit

router = APIRouter(prefix="/api", tags=["account"])


class SettingsIn(BaseModel):
    ai_daily_token_budget: int | None = Field(default=None, ge=0, le=10_000_000)
    notify_reminders: bool | None = None
    notify_triage: bool | None = None
    retention_days: int | None = Field(default=None, ge=7, le=3650)


def _settings_out(s: Any) -> dict[str, Any]:
    return {
        "ai_daily_token_budget": s.ai_daily_token_budget,
        "notify_reminders": s.notify_reminders,
        "notify_triage": s.notify_triage,
        "retention_days": s.retention_days,
        "adapter_flags": s.adapter_flags,
    }


@router.get("/settings")
async def get_user_settings(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    s = await profile_service.get_settings_row(session, user.id)
    cfg = get_settings()
    return {**_settings_out(s), "ai": {"provider": cfg.llm_provider, **await budget_status(session, user.id)}}


@router.patch("/settings")
async def patch_settings(body: SettingsIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    s = await profile_service.get_settings_row(session, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    return _settings_out(s)


@router.post("/privacy/export")
async def export_data(request: Request, user: CurrentUser, session: SessionDep) -> Response:
    require_recent_reauth(user)
    data = await privacy.export_user(session, user)
    audit(session, user.id, "privacy.export", request=request)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="jobpilot-export.zip"', "Cache-Control": "no-store"},
    )


class DeleteIn(BaseModel):
    confirm: Literal["DELETE"]


@router.post("/privacy/delete-account")
async def delete_account(body: DeleteIn, response: Response, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    require_recent_reauth(user)
    report = await privacy.delete_user(session, user)
    _clear_session_cookies(response)
    return report


@router.get("/notifications")
async def notifications(user: CurrentUser, session: SessionDep, unread_only: bool = False) -> list[dict[str, Any]]:
    where = [Notification.read.is_(False)] if unread_only else []
    rows = await Repo(session, Notification, user.id).list(*where, order_by=Notification.created_at.desc(), limit=100)
    return [
        {
            "id": str(n.id),
            "kind": n.kind,
            "message": n.message,
            "link": n.link,
            "read": n.read,
            "created_at": n.created_at.isoformat(),
        }
        for n in rows
    ]


@router.post("/notifications/read-all")
async def read_all(user: CurrentUser, session: SessionDep) -> dict[str, bool]:
    for n in await Repo(session, Notification, user.id).list(Notification.read.is_(False)):
        n.read = True
    return {"ok": True}


@router.get("/integrations")
async def integrations(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    rows = await Repo(session, UserIntegration, user.id).list()
    return {
        "connected": [{"id": str(r.id), "provider": r.provider, "scopes": r.scopes, "status": r.status} for r in rows],
        "available": [
            {
                "provider": "gmail",
                "status": "not_implemented",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                "note": "Gmail OAuth ingestion is not implemented in this build. Export emails as .eml and upload them "
                "in Inbox instead.",
            },
            {
                "provider": "outlook",
                "status": "not_implemented",
                "scopes": ["Mail.Read"],
                "note": "Microsoft Graph ingestion is not implemented in this build. Use .eml upload instead.",
            },
        ],
    }


@router.delete("/integrations/{integration_id}", status_code=204)
async def disconnect(integration_id: str, request: Request, user: CurrentUser, session: SessionDep) -> Response:
    require_recent_reauth(user)
    repo = Repo(session, UserIntegration, user.id)
    row = await repo.get(parse_uuid(integration_id))
    await repo.delete(row)
    audit(session, user.id, "integration.disconnect", row.provider, request=request)
    return Response(status_code=204)


@router.get("/dashboard")
async def dashboard(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    async def count(model: Any, *where: Any) -> int:
        return int(
            (
                await session.execute(select(func.count()).select_from(model).where(model.user_id == user.id, *where))
            ).scalar_one()
        )

    top = (
        await session.execute(
            select(Job, JobMatch)
            .join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == user.id))
            .where(Job.user_id == user.id, Job.archived.is_(False), JobMatch.eligible.is_(True))
            .order_by(JobMatch.score.desc())
            .limit(5)
        )
    ).all()
    reminders = await Repo(session, Reminder, user.id).list(Reminder.done.is_(False), order_by=Reminder.due_at, limit=5)
    status_rows = (
        await session.execute(
            select(Application.status, func.count()).where(Application.user_id == user.id).group_by(Application.status)
        )
    ).all()
    profile = await profile_service.get_profile(session, user.id)
    return {
        "onboarding_completed": profile.onboarding_completed,
        "counts": {
            "jobs": await count(Job, Job.archived.is_(False)),
            "applications": await count(Application),
            "candidate_facts": await count(ProfileFact, ProfileFact.status == "candidate"),
            "confirmed_facts": await count(ProfileFact, ProfileFact.status == "confirmed"),
            "pending_triage": await count(EmailMessage, EmailMessage.review_status == "pending"),
            "unread_notifications": await count(Notification, Notification.read.is_(False)),
        },
        "applications_by_status": {s: int(c) for s, c in status_rows},
        "top_matches": [
            {
                "id": str(j.id),
                "title": j.title,
                "company": j.company,
                "score": m.score,
                "confidence": m.confidence,
                "recommended_action": m.recommended_action,
                "is_demo": j.is_demo,
            }
            for j, m in top
        ],
        "upcoming_reminders": [
            {
                "id": str(r.id),
                "due_at": r.due_at.isoformat(),
                "message": r.message,
                "application_id": str(r.application_id) if r.application_id else None,
            }
            for r in reminders
        ],
    }
