"""Profile, consent, resume ingestion and ProfileFact lifecycle.

`confirmed_facts()` is the ONLY way downstream features (matching, tailoring, cover letters,
screening answers, interview prep) read the candidate's background.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import service as ai
from app.ai.prompts import untrusted
from app.config import get_settings
from app.errors import UnprocessableError
from app.models import ConsentRecord, ProfileFact, Resume, UserProfile, UserSettings, UserSkill
from app.repositories import Repo
from app.security.crypto import decrypt_field, encrypt_field
from app.services import resume_parser, uploads
from app.services.platform import emit
from app.services.skills import extract_skills, normalize_skill

FACT_CATEGORIES = {"experience", "education", "project", "skill", "certification", "summary", "achievement"}


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> UserProfile:
    profile = await Repo(session, UserProfile, user_id).find()
    if profile is None:
        profile = Repo(session, UserProfile, user_id).add()
        await session.flush()
    return profile


async def get_settings_row(session: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    row = await Repo(session, UserSettings, user_id).find()
    if row is None:
        row = Repo(session, UserSettings, user_id).add()
        await session.flush()
    return row


def profile_dict(p: UserProfile) -> dict[str, Any]:
    return {
        "full_name": p.full_name,
        "headline": p.headline,
        "location": p.location,
        "phone": decrypt_field(p.phone_encrypted) if p.phone_encrypted else "",
        "years_experience": p.years_experience,
        "education_level": p.education_level,
        "target_titles": p.target_titles or [],
        "preferred_locations": p.preferred_locations or [],
        "remote_preference": p.remote_preference,
        "employment_types": p.employment_types or [],
        "min_salary": p.min_salary,
        "needs_sponsorship": p.needs_sponsorship,
        "blocked_companies": p.blocked_companies or [],
        "blocked_keywords": p.blocked_keywords or [],
        "experience_filter_mode": p.experience_filter_mode,
        "onboarding_step": p.onboarding_step,
        "onboarding_completed": p.onboarding_completed,
        "version": p.version,
    }


MATCH_RELEVANT = {
    "years_experience",
    "education_level",
    "target_titles",
    "preferred_locations",
    "remote_preference",
    "employment_types",
    "min_salary",
    "needs_sponsorship",
    "blocked_companies",
    "blocked_keywords",
    "experience_filter_mode",
}


async def update_profile(session: AsyncSession, user_id: uuid.UUID, changes: dict[str, Any]) -> UserProfile:
    p = await get_profile(session, user_id)
    for key, value in changes.items():
        if key == "phone":
            p.phone_encrypted = encrypt_field(value) if value else None
        elif hasattr(p, key) and key not in {"id", "user_id", "version", "created_at", "updated_at"}:
            setattr(p, key, value)
    p.version += 1
    if MATCH_RELEVANT & changes.keys():
        await emit(
            session, user_id, "matches.rescore", {"user_id": str(user_id)}, f"rescore:{user_id}:profile:{p.version}"
        )
    return p


async def record_consent(session: AsyncSession, user_id: uuid.UUID, purpose: str, granted: bool) -> ConsentRecord:
    rec = ConsentRecord(user_id=user_id, purpose=purpose, granted=granted, provider=get_settings().llm_provider)
    session.add(rec)
    return rec


async def consent_state(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    rows = await Repo(session, ConsentRecord, user_id).list(order_by=ConsentRecord.created_at)
    state: dict[str, Any] = {}
    for r in rows:
        state[r.purpose] = {"granted": r.granted, "at": r.created_at.isoformat(), "provider": r.provider}
    return state


# ------------------------------------------------------------------ resumes


class _LLMFact(BaseModel):
    category: str
    text: str = Field(max_length=600)
    attributes: dict[str, str] = Field(default_factory=dict)


class _LLMFacts(BaseModel):
    facts: list[_LLMFact]


async def upload_resume(
    session: AsyncSession, user_id: uuid.UUID, filename: str, mime: str | None, data: bytes
) -> tuple[Resume, list[ProfileFact], dict[str, Any]]:
    upload = uploads.validate_upload(filename, mime, data)
    resumes = Repo(session, Resume, user_id)
    key = uploads.store(upload)
    resume = resumes.add(
        filename=upload.filename,
        storage_key=key,
        mime_type=upload.mime,
        size_bytes=len(upload.data),
        sha256=upload.sha256,
    )
    await session.flush()
    try:
        text = await resume_parser.extract_text(upload.ext, upload.data)
    except UnprocessableError as exc:
        resume.parse_status, resume.parse_error = "failed", exc.message
        return resume, [], {}
    resume.text = text
    parsed = resume_parser.decompose(text)

    def fallback() -> _LLMFacts:
        return _LLMFacts(
            facts=[
                _LLMFact(
                    category=f.category,
                    text=f.text,
                    attributes={k: str(v) for k, v in f.attributes.items() if isinstance(v, str)},
                )
                for f in parsed.facts
            ]
        )

    result = await ai.generate_structured(
        session, user_id, "parse_resume", _LLMFacts, {"resume": untrusted("resume", text)}, fallback
    )
    # Keep the richer heuristic attributes (tools list) when the deterministic path was used.
    source_facts: list[tuple[str, str, dict[str, Any]]] = (
        [(f.category, f.text, f.attributes) for f in parsed.facts]
        if result.generator == "deterministic"
        else [(f.category, f.text, dict(f.attributes)) for f in result.value.facts]
    )
    facts: list[ProfileFact] = []
    seen: set[tuple[str, str]] = set()
    for category, txt, attrs in source_facts:
        category = category if category in FACT_CATEGORIES else "achievement"
        if (category, txt.lower()) in seen:
            continue
        seen.add((category, txt.lower()))
        fact = ProfileFact(
            user_id=user_id,
            resume_id=resume.id,
            category=category,
            text=txt,
            attributes=attrs,
            source="resume",
            status="candidate",
        )
        session.add(fact)
        facts.append(fact)
    resume.parse_status = "parsed"
    suggestions = {
        "contact": {k: v for k, v in parsed.contact.items() if k in ("name",)},
        "estimated_years_experience": parsed.estimated_years_experience,
        "detected_education_level": parsed.detected_education_level,
        "generator": result.generator,
    }
    return resume, facts, suggestions


# ------------------------------------------------------------------ facts


async def confirmed_facts(session: AsyncSession, user_id: uuid.UUID) -> list[ProfileFact]:
    return await Repo(session, ProfileFact, user_id).list(
        ProfileFact.status == "confirmed", order_by=ProfileFact.created_at
    )


def fact_skills(fact: ProfileFact) -> list[str]:
    skills = set(extract_skills(fact.text))
    if fact.attributes.get("skill"):
        skills.add(normalize_skill(str(fact.attributes["skill"])))
    for t in fact.attributes.get("tools", []) or []:
        skills.add(normalize_skill(str(t)))
    return sorted(skills)


async def rebuild_skills(session: AsyncSession, user_id: uuid.UUID) -> None:
    """UserSkill rows are derived exclusively from confirmed facts (verified=True)."""
    repo = Repo(session, UserSkill, user_id)
    await repo.delete_all()
    seen: dict[str, uuid.UUID] = {}
    for fact in await confirmed_facts(session, user_id):
        for skill in fact_skills(fact):
            if skill.lower() not in {s.lower() for s in seen}:
                seen[skill] = fact.id
    for skill, fid in seen.items():
        repo.add(name=skill, verified=True, fact_id=fid)


async def _after_fact_change(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.flush()
    await rebuild_skills(session, user_id)
    stamp = datetime.now(UTC).timestamp()
    await emit(session, user_id, "matches.rescore", {"user_id": str(user_id)}, f"rescore:{user_id}:facts:{stamp}")


async def create_fact(
    session: AsyncSession, user_id: uuid.UUID, category: str, text: str, attributes: dict[str, Any]
) -> ProfileFact:
    if category not in FACT_CATEGORIES:
        raise UnprocessableError("Unknown fact category", code="invalid_category")
    # Facts typed by the user are their own statement, so they are confirmed on creation.
    fact = Repo(session, ProfileFact, user_id).add(
        category=category,
        text=text.strip(),
        attributes=attributes,
        source="manual",
        status="confirmed",
        confirmed_at=datetime.now(UTC),
    )
    await _after_fact_change(session, user_id)
    return fact


async def set_fact_status(
    session: AsyncSession, user_id: uuid.UUID, fact_ids: list[uuid.UUID], status: str
) -> list[ProfileFact]:
    repo = Repo(session, ProfileFact, user_id)
    facts = [await repo.get(fid) for fid in fact_ids]
    for f in facts:
        f.status = status
        f.confirmed_at = datetime.now(UTC) if status == "confirmed" else None
    await _after_fact_change(session, user_id)
    return facts


async def edit_fact(
    session: AsyncSession,
    user_id: uuid.UUID,
    fact_id: uuid.UUID,
    text: str | None,
    attributes: dict[str, Any] | None,
    category: str | None,
) -> ProfileFact:
    fact = await Repo(session, ProfileFact, user_id).get(fact_id)
    if text is not None:
        fact.text = text.strip()
    if attributes is not None:
        fact.attributes = attributes
    if category is not None:
        if category not in FACT_CATEGORIES:
            raise UnprocessableError("Unknown fact category", code="invalid_category")
        fact.category = category
    # Editing a fact is an explicit user statement => confirmed.
    fact.status, fact.confirmed_at = "confirmed", datetime.now(UTC)
    await _after_fact_change(session, user_id)
    return fact


async def delete_fact(session: AsyncSession, user_id: uuid.UUID, fact_id: uuid.UUID) -> None:
    repo = Repo(session, ProfileFact, user_id)
    await repo.delete(await repo.get(fact_id))
    await _after_fact_change(session, user_id)


def fact_dict(f: ProfileFact) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "category": f.category,
        "text": f.text,
        "attributes": f.attributes,
        "source": f.source,
        "status": f.status,
        "resume_id": str(f.resume_id) if f.resume_id else None,
        "confirmed_at": f.confirmed_at.isoformat() if f.confirmed_at else None,
        "created_at": f.created_at.isoformat(),
    }


async def user_skills(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = await Repo(session, UserSkill, user_id).list(UserSkill.verified.is_(True))
    return [r.name for r in rows]


async def resume_list(session: AsyncSession, user_id: uuid.UUID) -> list[Resume]:
    return await Repo(session, Resume, user_id).list(order_by=Resume.created_at.desc())
