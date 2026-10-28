from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app import agents
from app.adapters.base import describe
from app.adapters.sources import ADAPTERS, DISABLED_SOURCES, EMAIL_SOURCE
from app.errors import UnprocessableError
from app.models import Application, FailedImport, Job, JobMatch, ScamFeedback
from app.repositories import Repo
from app.routers._idem import idempotent
from app.security.deps import CurrentUser, SessionDep, parse_uuid, rate_limit
from app.services import applications as app_service
from app.services import ingestion, profile_service, tasks
from app.services.email_import import parse_email_upload

router = APIRouter(prefix="/api", tags=["jobs"])

MAX_FILE_BYTES = 5 * 1024 * 1024


def job_summary(job: Job, match: JobMatch | None) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote_policy": job.remote_policy,
        "employment_type": job.employment_type,
        "source": job.source,
        "url": job.url,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "verification_status": job.verification_status,
        "potential_duplicate_of": str(job.potential_duplicate_of) if job.potential_duplicate_of else None,
        "archived": job.archived,
        "is_demo": job.is_demo,
        "created_at": job.created_at.isoformat(),
        "scam_level": (job.scam_report or {}).get("level", "none"),
        "match": None
        if match is None
        else {
            "score": match.score,
            "confidence": match.confidence,
            "eligible": match.eligible,
            "recommended_action": match.recommended_action,
        },
    }


def _cursor(score: float, created: str, jid: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([score, created, jid]).encode()).decode()


@router.get("/jobs")
async def list_jobs(
    user: CurrentUser,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=200),
    min_score: float | None = Query(default=None, ge=0, le=100),
    action: str | None = None,
    source: str | None = None,
    remote: str | None = None,
    include_archived: bool = False,
    sort: Literal["score", "recent"] = "score",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = (
        select(Job, JobMatch)
        .outerjoin(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user.id))
        .where(Job.user_id == user.id)
    )
    if not include_archived:
        stmt = stmt.where(Job.archived.is_(False))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Job.title).like(like),
                func.lower(Job.company).like(like),
                func.lower(Job.location).like(like),
            )
        )
    if min_score is not None:
        stmt = stmt.where(JobMatch.score >= min_score)
    if action:
        stmt = stmt.where(JobMatch.recommended_action == action)
    if source:
        stmt = stmt.where(Job.source == source)
    if remote:
        stmt = stmt.where(Job.remote_policy == remote)
    score_expr = func.coalesce(JobMatch.score, -1.0)
    if cursor:
        try:
            c_score, c_created, c_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            c_created_dt, c_uuid = datetime.fromisoformat(c_created), uuid.UUID(c_id)
        except (ValueError, TypeError) as exc:
            raise UnprocessableError("Invalid cursor", code="invalid_cursor") from exc
        if sort == "score":
            stmt = stmt.where(or_(score_expr < c_score, and_(score_expr == c_score, Job.id < c_uuid)))
        else:
            stmt = stmt.where(or_(Job.created_at < c_created_dt, and_(Job.created_at == c_created_dt, Job.id < c_uuid)))
    order = (score_expr.desc(), Job.id.desc()) if sort == "score" else (Job.created_at.desc(), Job.id.desc())
    rows = (await session.execute(stmt.order_by(*order).limit(limit + 1))).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_job, last_match = rows[-1]
        next_cursor = _cursor(
            last_match.score if last_match else -1.0, last_job.created_at.isoformat(), str(last_job.id)
        )
    return {"items": [job_summary(j, m) for j, m in rows], "next_cursor": next_cursor}


@router.get("/jobs/failed-imports")
async def failed_imports(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    rows = await Repo(session, FailedImport, user.id).list(
        FailedImport.resolved.is_(False), order_by=FailedImport.created_at.desc(), limit=100
    )
    return [
        {
            "id": str(r.id),
            "source": r.source,
            "input_ref": r.input_ref,
            "stage": r.stage,
            "error": r.error,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/jobs/failed-imports/{item_id}/resolve")
async def resolve_failed(item_id: str, user: CurrentUser, session: SessionDep) -> dict[str, bool]:
    row = await Repo(session, FailedImport, user.id).get(parse_uuid(item_id))
    row.resolved = True
    return {"ok": True}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    job = await Repo(session, Job, user.id).get(parse_uuid(job_id))
    match = await Repo(session, JobMatch, user.id).find(JobMatch.job_id == job.id)
    app = await Repo(session, Application, user.id).find(Application.job_id == job.id)
    dup = (
        await Repo(session, Job, user.id).find(Job.id == job.potential_duplicate_of)
        if job.potential_duplicate_of
        else None
    )
    facts = {str(f.id): f.text for f in await profile_service.confirmed_facts(session, user.id)}
    detail = job_summary(job, match)
    detail.update(
        {
            "description_html": job.description_html,
            "description_text": job.description_text,
            "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills,
            "min_years": job.min_years,
            "education_req": job.education_req,
            "sponsorship": job.sponsorship,
            "contact_email": job.contact_email,
            "scam_report": job.scam_report,
            "last_seen_at": job.last_seen_at.isoformat() if job.last_seen_at else None,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "application_id": str(app.id) if app else None,
            "duplicate_of": {"id": str(dup.id), "title": dup.title, "company": dup.company, "source": dup.source}
            if dup
            else None,
            "match_detail": None
            if match is None
            else {
                "breakdown": match.breakdown,
                "explanation": match.explanation,
                "config_snapshot": match.config_snapshot,
                "highlight_facts": [
                    {"id": fid, "text": facts.get(fid, "")}
                    for fid in match.explanation.get("projects_to_highlight", [])
                ],
                "scored_at": match.updated_at.isoformat(),
            },
        }
    )
    return detail


class ImportIn(BaseModel):
    text: str | None = Field(default=None, max_length=100_000)
    url: str | None = Field(default=None, max_length=2000)
    board: str | None = Field(default=None, max_length=80)
    company: str | None = Field(default=None, max_length=80)
    organization: str | None = Field(default=None, max_length=80)


REQUIRED_PARAMS = {
    "manual_paste": "text",
    "manual_url": "url",
    "greenhouse": "board",
    "lever": "company",
    "ashby": "organization",
    "rss": "url",
}


@router.post("/jobs/import/file", dependencies=[rate_limit("import")])
async def import_file(
    request: Request, user: CurrentUser, session: SessionDep, file: UploadFile = File(...)
) -> JSONResponse:
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise UnprocessableError("File exceeds 5 MB", code="upload_rejected")
    name = (file.filename or "").lower()
    fmt = "json" if name.endswith(".json") else "csv" if name.endswith(".csv") else None
    if fmt is None:
        raise UnprocessableError("Upload a .csv or .json file", code="upload_rejected")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnprocessableError("File must be UTF-8 text", code="upload_rejected") from exc
    body = {"sha": hashlib.sha256(data).hexdigest(), "format": fmt}

    async def run() -> dict[str, Any]:
        out = await agents.discovery.run(
            session, user.id, agents.DiscoveryInput(source="file_import", params={"content": content, "format": fmt})
        )
        await tasks.run_inline(session, user.id)
        return out.report

    return await idempotent(request, session, user, "import:file", body, run)


@router.post("/jobs/import/email", dependencies=[rate_limit("import")])
async def import_email(user: CurrentUser, session: SessionDep, file: UploadFile = File(...)) -> dict[str, Any]:
    messages = parse_email_upload(file.filename or "", await file.read())
    report = await ingestion.import_emails(session, user.id, messages)
    await tasks.run_inline(session, user.id)
    return report.as_dict()


@router.post("/jobs/import/{source}", dependencies=[rate_limit("import")])
async def import_jobs(
    source: str, body: ImportIn, request: Request, user: CurrentUser, session: SessionDep
) -> JSONResponse:
    if source not in REQUIRED_PARAMS:
        raise UnprocessableError(
            "Unknown or file-based source; use /jobs/import/file or /jobs/import/email", code="unknown_source"
        )
    params = body.model_dump(exclude_none=True)
    if not params.get(REQUIRED_PARAMS[source]):
        raise UnprocessableError(f"'{REQUIRED_PARAMS[source]}' is required for this source", code="missing_param")

    async def run() -> dict[str, Any]:
        out = await agents.discovery.run(session, user.id, agents.DiscoveryInput(source=source, params=params))
        await tasks.run_inline(session, user.id)
        return out.report

    return await idempotent(request, session, user, f"import:{source}", params, run)


@router.get("/sources")
async def sources(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    enabled = [describe(a, await ingestion.adapter_enabled(session, user.id, a)) for a in ADAPTERS.values()]
    return {"sources": enabled + [EMAIL_SOURCE], "disabled_by_policy": [d.__dict__ for d in DISABLED_SOURCES]}


class SourceToggle(BaseModel):
    enabled: bool


@router.put("/sources/{source_id}")
async def toggle_source(source_id: str, body: SourceToggle, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    if source_id not in ADAPTERS:
        raise UnprocessableError("Unknown source", code="unknown_source")
    s = await profile_service.get_settings_row(session, user.id)
    s.adapter_flags = {**(s.adapter_flags or {}), source_id: body.enabled}
    return {"id": source_id, "enabled": await ingestion.adapter_enabled(session, user.id, ADAPTERS[source_id])}


class BulkIn(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["archive", "unarchive", "save_to_tracker"]


@router.post("/jobs/bulk")
async def bulk(body: BulkIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    repo = Repo(session, Job, user.id)
    done, skipped = 0, 0
    for jid in body.job_ids:
        job = await repo.get(parse_uuid(jid))
        if body.action == "archive":
            job.archived = True
        elif body.action == "unarchive":
            job.archived = False
        else:
            if await Repo(session, Application, user.id).find(Application.job_id == job.id):
                skipped += 1
                continue
            await app_service.create(session, user.id, job.id)
        done += 1
    return {"done": done, "skipped": skipped}


@router.post("/jobs/{job_id}/reverify")
async def reverify(job_id: str, user: CurrentUser, session: SessionDep) -> dict[str, str]:
    job = await Repo(session, Job, user.id).get(parse_uuid(job_id))
    return {"verification_status": await ingestion.reverify(session, user.id, job)}


class ScamFeedbackIn(BaseModel):
    signal_code: str = Field(max_length=64)
    comment: str = Field(default="", max_length=1000)


@router.post("/jobs/{job_id}/scam-feedback", status_code=201)
async def scam_feedback(job_id: str, body: ScamFeedbackIn, user: CurrentUser, session: SessionDep) -> dict[str, bool]:
    job = await Repo(session, Job, user.id).get(parse_uuid(job_id))
    Repo(session, ScamFeedback, user.id).add(job_id=job.id, signal_code=body.signal_code, comment=body.comment)
    report = dict(job.scam_report or {})
    report["signals"] = [
        {**s, "reported_false_positive": True} if s.get("code") == body.signal_code else s
        for s in report.get("signals", [])
    ]
    job.scam_report = report
    return {"ok": True}


@router.post("/matches/rescore")
async def rescore(user: CurrentUser, session: SessionDep) -> dict[str, int]:
    out = await agents.matching.run(session, user.id, agents.MatchingInput())
    return {"scored": out.scored}


class SavedFilter(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    params: dict[str, Any]


@router.get("/saved-filters")
async def get_saved_filters(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    return (await profile_service.get_settings_row(session, user.id)).saved_job_filters or []


@router.put("/saved-filters")
async def put_saved_filters(body: list[SavedFilter], user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    s = await profile_service.get_settings_row(session, user.id)
    s.saved_job_filters = [f.model_dump() for f in body[:20]]
    return s.saved_job_filters
