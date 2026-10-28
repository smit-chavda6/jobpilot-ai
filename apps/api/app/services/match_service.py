"""Persistence wrapper around the matching engine: builds inputs from verified data only."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.service import ai_consented, embed_texts
from app.models import Job, JobEmbedding, JobMatch
from app.repositories import Repo
from app.services import profile_service
from app.services.matching import JobInput, MatchConfig, ProfileInput, score_job


class Explanation(BaseModel):
    """Schema the stored explanation must satisfy (spec §8.3)."""

    fit_reasons: list[str]
    matched_skills: list[str]
    missing_or_uncertain: list[str]
    projects_to_highlight: list[str]
    questions_to_investigate: list[str]
    recommended_action: Literal["apply", "apply_after_tailoring", "research_first", "skip"]


def job_input(job: Job, embedding: list[float] | None) -> JobInput:
    return JobInput(
        title=job.title,
        company=job.company,
        location=job.location,
        remote_policy=job.remote_policy,
        employment_type=job.employment_type,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        min_years=job.min_years,
        education_req=job.education_req,
        required_skills=list(job.required_skills or []),
        preferred_skills=list(job.preferred_skills or []),
        sponsorship=job.sponsorship,
        text=job.description_text,
        embedding=embedding,
    )


async def profile_input(session: AsyncSession, user_id: uuid.UUID) -> tuple[ProfileInput, str]:
    profile = await profile_service.get_profile(session, user_id)
    facts = await profile_service.confirmed_facts(session, user_id)
    skills = set(await profile_service.user_skills(session, user_id))
    fact_skills = {
        str(f.id): profile_service.fact_skills(f)
        for f in facts
        if f.category in ("experience", "project", "achievement")
    }
    corpus = " ".join([profile.headline, " ".join(profile.target_titles or [])] + [f.text for f in facts])
    model, vectors = await embed_texts([corpus or "empty profile"], await ai_consented(session, user_id))
    return ProfileInput(
        skills=skills,
        years_experience=profile.years_experience,
        education_level=profile.education_level,
        target_titles=list(profile.target_titles or []),
        preferred_locations=list(profile.preferred_locations or []),
        remote_preference=profile.remote_preference,
        employment_types=list(profile.employment_types or []),
        min_salary=profile.min_salary,
        needs_sponsorship=profile.needs_sponsorship,
        blocked_companies=list(profile.blocked_companies or []),
        blocked_keywords=list(profile.blocked_keywords or []),
        experience_filter_mode=profile.experience_filter_mode,
        fact_skills=fact_skills,
        embedding=vectors[0] if facts else None,
    ), model


async def ensure_embedding(session: AsyncSession, user_id: uuid.UUID, job: Job, model_hint: str) -> list[float] | None:
    repo = Repo(session, JobEmbedding, user_id)
    emb = await repo.find(JobEmbedding.job_id == job.id)
    if emb is not None and emb.model == model_hint:
        return list(emb.vector)
    model, vectors = await embed_texts(
        [f"{job.title} {job.company}\n{job.description_text[:8000]}"], await ai_consented(session, user_id)
    )
    if emb is None:
        repo.add(job_id=job.id, model=model, dim=len(vectors[0]), vector=vectors[0])
    else:
        emb.model, emb.dim, emb.vector = model, len(vectors[0]), vectors[0]
    return vectors[0] if model == model_hint else None


async def score_jobs(session: AsyncSession, user_id: uuid.UUID, jobs: list[Job] | None = None) -> int:
    """(Re)score the given jobs, or all of the user's active jobs. Idempotent (upserts JobMatch)."""
    if jobs is None:
        jobs = await Repo(session, Job, user_id).list(Job.archived.is_(False))
    if not jobs:
        return 0
    pinput, model = await profile_input(session, user_id)
    config = MatchConfig()
    matches = Repo(session, JobMatch, user_id)
    for job in jobs:
        emb = await ensure_embedding(session, user_id, job, model)
        result = score_job(pinput, job_input(job, emb), config)
        explanation = Explanation.model_validate(result.explanation).model_dump()
        existing = await matches.find(JobMatch.job_id == job.id)
        fields = dict(
            score=result.score,
            confidence=result.confidence,
            eligible=result.eligible,
            recommended_action=result.recommended_action,
            breakdown=result.breakdown,
            explanation=explanation,
            config_snapshot=result.config_snapshot,
        )
        if existing is None:
            matches.add(job_id=job.id, **fields)
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
    await session.flush()
    return len(jobs)
