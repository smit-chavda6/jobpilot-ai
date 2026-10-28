from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Request, Response, UploadFile
from pydantic import BaseModel, Field

from app import agents
from app.models import ProfileFact, Resume
from app.repositories import Repo
from app.security.deps import CurrentUser, SessionDep, check_if_match, etag_for, parse_uuid, rate_limit
from app.services import profile_service, tasks
from app.services.platform import audit

router = APIRouter(prefix="/api", tags=["profile"])

EduLevel = Literal["none", "high_school", "associate", "bachelor", "master", "phd"]


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    education_level: EduLevel | None = None
    target_titles: list[str] | None = Field(default=None, max_length=20)
    preferred_locations: list[str] | None = Field(default=None, max_length=20)
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] | None = None
    employment_types: list[Literal["full_time", "part_time", "contract", "internship"]] | None = None
    min_salary: int | None = Field(default=None, ge=0)
    needs_sponsorship: bool | None = None
    blocked_companies: list[str] | None = Field(default=None, max_length=100)
    blocked_keywords: list[str] | None = Field(default=None, max_length=100)
    experience_filter_mode: Literal["soft", "hard"] | None = None
    onboarding_step: int | None = Field(default=None, ge=0, le=10)
    onboarding_completed: bool | None = None


class ConsentIn(BaseModel):
    purpose: Literal["ai_processing", "email_access"]
    granted: bool


class FactIn(BaseModel):
    category: str
    text: str = Field(min_length=2, max_length=600)
    attributes: dict[str, Any] = Field(default_factory=dict)


class FactPatch(BaseModel):
    text: str | None = Field(default=None, min_length=2, max_length=600)
    category: str | None = None
    attributes: dict[str, Any] | None = None


class FactStatusIn(BaseModel):
    fact_ids: list[str] = Field(min_length=1, max_length=500)
    status: Literal["confirmed", "rejected", "candidate"]


@router.get("/profile")
async def get_profile(user: CurrentUser, session: SessionDep, response: Response) -> dict[str, Any]:
    p = await profile_service.get_profile(session, user.id)
    response.headers["ETag"] = etag_for(p.version)
    return profile_service.profile_dict(p)


@router.patch("/profile")
async def patch_profile(
    body: ProfileUpdate, request: Request, response: Response, user: CurrentUser, session: SessionDep
) -> dict[str, Any]:
    p = await profile_service.get_profile(session, user.id)
    check_if_match(request, p.version)
    p = await profile_service.update_profile(session, user.id, body.model_dump(exclude_unset=True))
    await tasks.run_inline(session, user.id)
    response.headers["ETag"] = etag_for(p.version)
    return profile_service.profile_dict(p)


@router.get("/consents")
async def get_consents(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    from app.config import get_settings

    s = get_settings()
    return {
        "consents": await profile_service.consent_state(session, user.id),
        "ai_provider": s.llm_provider,
        "data_sent_to_provider": []
        if s.llm_provider == "mock"
        else [
            "Confirmed profile facts (text)",
            "Job descriptions you import",
            "Resume text during parsing",
            "Email text during triage",
            "Generated document items for grounding checks",
        ],
    }


@router.post("/consents", status_code=201)
async def set_consent(body: ConsentIn, request: Request, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    await profile_service.record_consent(session, user.id, body.purpose, body.granted)
    audit(session, user.id, "consent.set", body.purpose, {"granted": body.granted}, request)
    return await profile_service.consent_state(session, user.id)


# ------------------------------------------------------------------ resumes


@router.post("/resumes", status_code=201, dependencies=[rate_limit("upload")])
async def upload_resume(user: CurrentUser, session: SessionDep, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    out = await agents.resume_parsing.run(
        session,
        user.id,
        agents.ResumeParsingInput(filename=file.filename or "resume", mime=file.content_type, data=data),
    )
    return out.model_dump()


@router.get("/resumes")
async def list_resumes(user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    return [
        {
            "id": str(r.id),
            "filename": r.filename,
            "size_bytes": r.size_bytes,
            "parse_status": r.parse_status,
            "parse_error": r.parse_error,
            "created_at": r.created_at.isoformat(),
        }
        for r in await profile_service.resume_list(session, user.id)
    ]


@router.delete("/resumes/{resume_id}", status_code=204)
async def delete_resume(resume_id: str, user: CurrentUser, session: SessionDep) -> Response:
    from app.services import uploads

    repo = Repo(session, Resume, user.id)
    r = await repo.get(parse_uuid(resume_id))
    uploads.remove(r.storage_key)
    await repo.delete(r)
    return Response(status_code=204)


# ------------------------------------------------------------------ facts


@router.get("/facts")
async def list_facts(user: CurrentUser, session: SessionDep, status: str | None = None) -> list[dict[str, Any]]:
    where = [ProfileFact.status == status] if status else []
    rows = await Repo(session, ProfileFact, user.id).list(*where, order_by=ProfileFact.created_at)
    return [profile_service.fact_dict(f) for f in rows]


@router.post("/facts", status_code=201)
async def create_fact(body: FactIn, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    f = await profile_service.create_fact(session, user.id, body.category, body.text, body.attributes)
    await tasks.run_inline(session, user.id)
    return profile_service.fact_dict(f)


@router.patch("/facts/{fact_id}")
async def edit_fact(fact_id: str, body: FactPatch, user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    f = await profile_service.edit_fact(
        session, user.id, parse_uuid(fact_id), body.text, body.attributes, body.category
    )
    await tasks.run_inline(session, user.id)
    return profile_service.fact_dict(f)


@router.post("/facts/status")
async def set_fact_status(body: FactStatusIn, user: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    facts = await profile_service.set_fact_status(session, user.id, [parse_uuid(i) for i in body.fact_ids], body.status)
    await tasks.run_inline(session, user.id)
    return [profile_service.fact_dict(f) for f in facts]


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: str, user: CurrentUser, session: SessionDep) -> Response:
    await profile_service.delete_fact(session, user.id, parse_uuid(fact_id))
    await tasks.run_inline(session, user.id)
    return Response(status_code=204)


@router.get("/skills")
async def skills(user: CurrentUser, session: SessionDep) -> list[str]:
    return sorted(await profile_service.user_skills(session, user.id))
