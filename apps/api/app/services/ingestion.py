"""Job ingestion pipeline (spec §7.2):
raw -> sanitize -> parse/normalize -> extract skills -> fingerprint -> dedup -> persist -> embed -> match.

Every stage is idempotent: re-importing the same listing updates `last_seen_at` instead of
creating a duplicate (UNIQUE(user_id, fingerprint) backs this up at the DB level). Failures are
recorded in the user-visible FailedImport list (dead letters).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import FetchContext, JobSourceAdapter
from app.adapters.sources import ADAPTERS
from app.config import get_settings
from app.errors import AppError, Forbidden, UnprocessableError
from app.models import FailedImport, Job, UserSettings
from app.repositories import Repo
from app.services import job_parser, scam_signals
from app.services.email_import import ParsedEmail, jobs_from_alert
from app.services.fingerprint import (
    DUPLICATE_THRESHOLD,
    canonicalize_url,
    duplicate_key,
    job_fingerprint,
    trigram_similarity,
)
from app.services.job_parser import JobDraft
from app.services.platform import emit
from app.services.safe_fetch import safe_get

log = logging.getLogger("jobpilot.ingestion")


@dataclass
class ImportReport:
    created: list[dict[str, Any]] = field(default_factory=list)
    updated: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "failed": self.failed,
            "counts": {"created": len(self.created), "updated": len(self.updated), "failed": len(self.failed)},
        }


async def adapter_enabled(session: AsyncSession, user_id: uuid.UUID, adapter: JobSourceAdapter) -> bool:
    if adapter.settings_flag and not getattr(get_settings(), adapter.settings_flag, True):
        return False
    user_settings = await Repo(session, UserSettings, user_id).find()
    if user_settings and user_settings.adapter_flags.get(adapter.id) is False:
        return False
    return True


def _summary(job: Job, potential_dup: bool = False) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company,
        "potential_duplicate": potential_dup or job.potential_duplicate_of is not None,
    }


async def persist_draft(
    session: AsyncSession,
    user_id: uuid.UUID,
    draft: JobDraft,
    source: str,
    report: ImportReport,
    verified_live: bool = False,
) -> Job:
    jobs = Repo(session, Job, user_id)
    fp = job_fingerprint(draft.company, draft.title, draft.location, draft.url)
    now = datetime.now(UTC)
    existing = await jobs.find(Job.fingerprint == fp)
    if existing is not None:
        existing.last_seen_at = now
        if verified_live:
            existing.verification_status = "verified_live"
        report.updated.append(_summary(existing))
        return existing

    # Secondary fuzzy pass: flag (never auto-merge) likely duplicates from other sources.
    key = duplicate_key(draft.company, draft.title)
    potential_dup: uuid.UUID | None = None
    for other in await jobs.list(Job.archived.is_(False), order_by=Job.created_at.desc(), limit=500):
        if trigram_similarity(key, duplicate_key(other.company, other.title)) >= DUPLICATE_THRESHOLD and (
            not draft.location or not other.location or trigram_similarity(draft.location, other.location) >= 0.5
        ):
            potential_dup = other.id
            break

    job = jobs.add(
        source=source,
        source_ref=draft.source_ref,
        url=draft.url,
        canonical_url=canonicalize_url(draft.url) or None,
        title=draft.title,
        company=draft.company,
        location=draft.location,
        remote_policy=draft.remote_policy,
        employment_type=draft.employment_type,
        salary_min=draft.salary_min,
        salary_max=draft.salary_max,
        salary_currency=draft.salary_currency,
        min_years=draft.min_years,
        education_req=draft.education_req,
        sponsorship=draft.sponsorship,
        description_html=draft.description_html,
        description_text=draft.description_text,
        required_skills=draft.required_skills,
        preferred_skills=draft.preferred_skills,
        contact_email=draft.contact_email,
        fingerprint=fp,
        potential_duplicate_of=potential_dup,
        verification_status="verified_live" if verified_live else "unverified",
        last_seen_at=now,
        posted_at=draft.posted_at,
        is_demo=draft.is_demo,
        scam_report=scam_signals.analyze(
            f"{draft.title}\n{draft.description_text}", draft.company, draft.contact_email
        ),
    )
    await session.flush()
    await emit(
        session, user_id, "job.ingested", {"user_id": str(user_id), "job_id": str(job.id)}, f"job.ingested:{job.id}"
    )
    report.created.append(_summary(job, potential_dup is not None))
    return job


def _record_failure(
    session: AsyncSession, user_id: uuid.UUID, source: str, ref: str, stage: str, err: str, report: ImportReport
) -> None:
    session.add(FailedImport(user_id=user_id, source=source, input_ref=ref[:500], stage=stage, error=err[:1000]))
    report.failed.append({"ref": ref[:200], "stage": stage, "error": err[:300]})


async def run_import(
    session: AsyncSession, user_id: uuid.UUID, adapter_id: str, params: dict[str, Any]
) -> ImportReport:
    adapter = ADAPTERS.get(adapter_id)
    if adapter is None:
        raise UnprocessableError("Unknown source", code="unknown_source")
    if not await adapter_enabled(session, user_id, adapter):
        raise Forbidden(f"The '{adapter.name}' source is disabled", code="source_disabled")
    report = ImportReport()
    live = adapter_id in ("greenhouse", "lever", "ashby")
    ref_hint = str(
        params.get("url") or params.get("board") or params.get("company") or params.get("organization") or adapter_id
    )
    try:
        async for raw in adapter.fetch(FetchContext(params)):
            try:
                draft = adapter.normalize(raw)
            except AppError as exc:
                _record_failure(session, user_id, adapter_id, raw.ref or ref_hint, "normalize", exc.message, report)
                continue
            except (KeyError, ValueError, TypeError) as exc:
                _record_failure(
                    session,
                    user_id,
                    adapter_id,
                    raw.ref or ref_hint,
                    "normalize",
                    f"Malformed record: {type(exc).__name__}",
                    report,
                )
                continue
            async with session.begin_nested():
                await persist_draft(session, user_id, draft, adapter_id, report, verified_live=live)
    except AppError as exc:
        _record_failure(session, user_id, adapter_id, ref_hint, "fetch", exc.message, report)
    return report


async def import_emails(session: AsyncSession, user_id: uuid.UUID, messages: list[ParsedEmail]) -> ImportReport:
    report = ImportReport()
    for msg in messages:
        listings = jobs_from_alert(msg)
        if listings:
            for item in listings:
                draft = job_parser.from_text(
                    f"Imported from job-alert email: {msg.subject}",
                    title=item["title"],
                    company=item["company"],
                    url=item["url"],
                )
                async with session.begin_nested():
                    await persist_draft(session, user_id, draft, "email_upload", report)
        elif msg.text.strip():
            draft = job_parser.parse_pasted(msg.text)
            if draft.title == "Untitled role" or len(msg.text) < 80:
                _record_failure(
                    session,
                    user_id,
                    "email_upload",
                    msg.subject or msg.message_id,
                    "normalize",
                    "No job listings were recognised in this email",
                    report,
                )
                continue
            async with session.begin_nested():
                await persist_draft(session, user_id, draft, "email_upload", report)
    return report


async def reverify(session: AsyncSession, user_id: uuid.UUID, job: Job) -> str:
    """Re-check a listing using permitted methods only (single page fetch honouring robots.txt)."""
    if not job.url:
        return job.verification_status
    try:
        await safe_get(job.url, check_robots=True)
        job.verification_status = "verified_live"
        job.last_seen_at = datetime.now(UTC)
    except UnprocessableError as exc:
        status = (exc.details or {}).get("status") if isinstance(exc.details, dict) else None
        job.verification_status = "expired" if status in (404, 410) else "unavailable"
    except Exception:  # network failure: leave a clear, non-alarming state
        job.verification_status = "unavailable"
    return job.verification_status
