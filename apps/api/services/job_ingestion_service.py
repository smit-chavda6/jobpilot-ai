"""Job ingestion pipeline: sanitization, fingerprinting, and idempotent dedup."""

import hashlib
import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.adapters.base import JobDraft
from apps.api.models.job import Job
from apps.api.repositories.job_repository import JobRepository


def normalize_text_token(text: Optional[str]) -> str:
    """Normalizes whitespace, casing, and punctuation for robust fingerprinting."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def compute_job_fingerprint(
    company: str, title: str, location: Optional[str], source_url: Optional[str]
) -> str:
    """
    Computes cryptographic SHA-256 fingerprint for deduplication.
    Job fingerprint: hash of normalized(company) + normalized(title) + normalized(location) + canonicalized URL
    """
    norm_company = normalize_text_token(company)
    norm_title = normalize_text_token(title)
    norm_location = normalize_text_token(location or "remote")
    norm_url = (source_url or "").strip().lower().split("?")[0]  # strip tracking query parameters

    raw_signature = f"{norm_company}|{norm_title}|{norm_location}|{norm_url}"
    return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()


def sanitize_job_description(html_or_text: str) -> str:
    """Sanitizes HTML tags and returns safe plain text copy."""
    soup = BeautifulSoup(html_or_text, "html.parser")
    # Remove script and style tags completely
    for tag in soup(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())


class JobIngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = JobRepository(session)

    async def ingest_job_draft(self, user_id: str, draft: JobDraft) -> Tuple[Job, bool]:
        """
        Idempotently ingests a JobDraft for a specific user.
        Returns: (Job, is_new_created: bool)
        """
        fingerprint = compute_job_fingerprint(
            company=draft.company,
            title=draft.title,
            location=draft.location,
            source_url=draft.source_url,
        )

        # Check existing job by fingerprint for this user
        existing = await self.repo.get_by_fingerprint(user_id, fingerprint)
        if existing:
            # Idempotent re-import: returns existing without creating duplicate
            existing.verification_status = "verified_live"
            await self.session.flush()
            return existing, False

        # Create new Job record
        clean_desc = sanitize_job_description(draft.description)
        new_job = Job(
            user_id=user_id,
            job_fingerprint=fingerprint,
            title=draft.title.strip(),
            company=draft.company.strip(),
            location=draft.location,
            remote_type=draft.remote_type,
            employment_type=draft.employment_type,
            description=clean_desc,
            raw_description=draft.description,
            salary_min=draft.salary_min,
            salary_max=draft.salary_max,
            salary_currency=draft.salary_currency,
            required_skills=draft.required_skills,
            preferred_skills=draft.preferred_skills,
            source_id=draft.source_id,
            source_url=draft.source_url,
            posted_at=draft.posted_at,
            verification_status="verified_live",
        )

        created = await self.repo.create(new_job)
        return created, True
